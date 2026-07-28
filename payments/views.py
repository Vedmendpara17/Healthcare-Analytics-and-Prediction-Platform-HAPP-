import os
import re
from datetime import datetime, timezone
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, FileResponse, Http404, JsonResponse
from django.db import transaction
from django.db.models import Sum, Count, Q
from django.utils import timezone

from accounts.decorators import patient_required, doctor_required, admin_required, role_required
from appointments.models import Appointment
from core.models import Notification, AuditLog
from payments.models import Payment, Invoice, Refund
from payments.utils import generate_payment_id, generate_transaction_id, generate_invoice_number, generate_refund_id
from payments.pdf_generator import generate_invoice_pdf
from payments.emails import send_payment_success_email, send_doctor_payment_notification, send_refund_email


@patient_required
def checkout_view(request, appointment_id):
    """
    Displays appointment summary, calculated breakdown, and simulated payment methods.
    """
    appointment = get_object_or_404(Appointment, id=appointment_id, patient=request.user)
    
    # Check if payment already exists
    existing_payment = getattr(appointment, 'payment', None)
    if existing_payment and existing_payment.payment_status == Payment.PaymentStatus.PAID:
        messages.info(request, "This appointment has already been paid for.")
        return redirect('payment_success', payment_id=existing_payment.payment_id)

    consultation_fee = appointment.doctor.consultation_fee
    platform_fee = Decimal('5.00')
    tax_rate = Decimal('0.05') # 5% tax
    tax = (consultation_fee + platform_fee) * tax_rate
    discount = Decimal('0.00')
    total_amount = (consultation_fee + platform_fee + tax) - discount

    context = {
        'appointment': appointment,
        'consultation_fee': consultation_fee,
        'platform_fee': platform_fee,
        'tax': round(tax, 2),
        'discount': discount,
        'total_amount': round(total_amount, 2),
    }
    return render(request, 'payments/checkout.html', context)


@patient_required
def process_payment_view(request, appointment_id):
    """
    Validates simulated payment credentials backend-side, creates payment records,
    generates PDF invoice, triggers emails and notifications safely without duplicate creation.
    """
    if request.method != 'POST':
        return redirect('checkout', appointment_id=appointment_id)

    appointment = get_object_or_404(Appointment, id=appointment_id, patient=request.user)
    
    # Prevent duplicate payment handling
    existing_payment = getattr(appointment, 'payment', None)
    if existing_payment and existing_payment.payment_status == Payment.PaymentStatus.PAID:
        messages.info(request, "Payment has already been completed for this appointment.")
        return redirect('payment_success', payment_id=existing_payment.payment_id)

    payment_method = request.POST.get('payment_method')
    simulation_outcome = request.POST.get('simulation_outcome', 'SUCCESS') # SUCCESS or FAILURE
    
    consultation_fee = appointment.doctor.consultation_fee
    platform_fee = Decimal('5.00')
    tax = round((consultation_fee + platform_fee) * Decimal('0.05'), 2)
    discount = Decimal('0.00')
    total_amount = consultation_fee + platform_fee + tax - discount

    masked_ref = ""
    errors = []

    card_type_detected = None
    last_four = None

    # Backend Validation for Simulated Payment Methods
    if payment_method == Payment.PaymentMethod.UPI:
        upi_id = request.POST.get('upi_id', '').strip()
        if not upi_id:
            errors.append("Please enter your UPI ID.")
        elif not re.match(r'^[a-zA-Z0-9._-]+@[a-zA-Z0-9]+$', upi_id):
            errors.append("Invalid UPI ID format. Valid example: rahul123@oksbi or john.doe@okaxis.")
        else:
            masked_ref = upi_id

    elif payment_method in [Payment.PaymentMethod.CREDIT_CARD, Payment.PaymentMethod.DEBIT_CARD]:
        card_holder = request.POST.get('card_holder', '').strip()
        raw_card_num = request.POST.get('card_number', '').replace(' ', '').replace('-', '').strip()
        expiry_str = request.POST.get('expiry_date', '').strip() # MM/YY or separate inputs
        cvv = request.POST.get('cvv', '').strip()

        # 1. Card Holder Name Validation (Letters & spaces only, 3-50 chars)
        if not card_holder:
            errors.append("Card holder name is required.")
        elif not re.match(r'^[a-zA-Z\s]{3,50}$', card_holder):
            errors.append("Enter a valid card holder name.")

        # 2. Card Number Validation (13-19 digits, Luhn check, card type detection)
        if not raw_card_num:
            errors.append("Invalid card number.")
        elif not re.match(r'^\d{13,19}$', raw_card_num):
            errors.append("Invalid card number.")
        else:
            # Luhn Check Function
            def luhn_check(num_str):
                total = 0
                reverse_digits = num_str[::-1]
                for i, digit_char in enumerate(reverse_digits):
                    n = int(digit_char)
                    if i % 2 == 1:
                        n *= 2
                        if n > 9:
                            n -= 9
                    total += n
                return total % 10 == 0

            if not luhn_check(raw_card_num):
                errors.append("Invalid card number.")
            else:
                # Detect Card Type
                if raw_card_num.startswith('4'):
                    card_type_detected = 'Visa'
                elif re.match(r'^(5[1-5]|2[2-7])', raw_card_num):
                    card_type_detected = 'Mastercard'
                elif re.match(r'^(60|65|508|353|356)', raw_card_num):
                    card_type_detected = 'RuPay'
                elif re.match(r'^(34|37)', raw_card_num):
                    card_type_detected = 'American Express'
                else:
                    card_type_detected = 'Credit/Debit Card'

        # 3. Expiry Date Validation (MM/YY)
        if not expiry_str:
            errors.append("Card has expired.")
        else:
            parts = expiry_str.split('/')
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                exp_month = int(parts[0])
                exp_year = int("20" + parts[1]) if len(parts[1]) == 2 else int(parts[1])
                
                if exp_month < 1 or exp_month > 12:
                    errors.append("Card has expired.")
                else:
                    now = timezone.now()
                    current_year = now.year
                    current_month = now.month
                    if exp_year < current_year or (exp_year == current_year and exp_month < current_month):
                        errors.append("Card has expired.")
            else:
                errors.append("Card has expired.")

        # 4. CVV Validation (3 digits for Visa/Mastercard/RuPay, 4 digits for Amex)
        expected_cvv_len = 4 if card_type_detected == 'American Express' else 3
        if not cvv or not cvv.isdigit() or len(cvv) != expected_cvv_len:
            errors.append("Invalid CVV.")

        if not errors:
            last_four = raw_card_num[-4:]
            masked_ref = f"**** **** **** {last_four}"

    elif payment_method == Payment.PaymentMethod.NET_BANKING:
        bank_name = request.POST.get('bank_name', '').strip()
        account_holder = request.POST.get('account_holder', '').strip()
        if not bank_name:
            errors.append("Please select or enter your Bank Name.")
        else:
            masked_ref = f"NetBanking ({bank_name})"

    elif payment_method == Payment.PaymentMethod.CASH:
        masked_ref = "Pay at Hospital Counter"

    else:
        errors.append("Please select a valid payment method.")

    if errors:
        for err in errors:
            messages.error(request, err)
        return redirect('checkout', appointment_id=appointment_id)

    # Process Simulation
    with transaction.atomic():
        pay_id = generate_payment_id()
        txn_id = generate_transaction_id()
        inv_num = generate_invoice_number()

        if payment_method == Payment.PaymentMethod.CASH:
            status = Payment.PaymentStatus.PENDING
            appointment.status = Appointment.Status.APPROVED
            appointment.save(update_fields=['status'])
            
            payment = Payment.objects.create(
                payment_id=pay_id,
                transaction_id=txn_id,
                patient=request.user,
                doctor=appointment.doctor,
                appointment=appointment,
                amount=consultation_fee,
                platform_fee=platform_fee,
                tax=tax,
                discount=discount,
                total_amount=total_amount,
                payment_method=payment_method,
                card_type=card_type_detected,
                last_four_digits=last_four,
                payment_status=status,
                masked_payment_reference=masked_ref,
                invoice_number=inv_num,
                remarks="Pay at hospital selected. Payment pending."
            )
            
            Invoice.objects.create(invoice_number=inv_num, payment=payment)
            
            # Generate PDF Invoice
            generate_invoice_pdf(payment)
            
            AuditLog.objects.create(
                actor=request.user,
                action="PAYMENT_PENDING_CASH",
                details=f"Appointment #{appointment.id} set for Cash Payment at Hospital."
            )
            
            messages.warning(request, "Appointment confirmed! Please pay consultation fee at hospital reception on visit date.")
            return redirect('payment_success', payment_id=payment.payment_id)

        # Online Simulation (SUCCESS / FAILED)
        if simulation_outcome == 'FAILED':
            payment = Payment.objects.create(
                payment_id=pay_id,
                transaction_id=txn_id,
                patient=request.user,
                doctor=appointment.doctor,
                appointment=appointment,
                amount=consultation_fee,
                platform_fee=platform_fee,
                tax=tax,
                discount=discount,
                total_amount=total_amount,
                payment_method=payment_method,
                card_type=card_type_detected,
                last_four_digits=last_four,
                payment_status=Payment.PaymentStatus.FAILED,
                masked_payment_reference=masked_ref,
                invoice_number=inv_num,
                remarks="Payment failed. Please verify your card details."
            )
            
            AuditLog.objects.create(
                actor=request.user,
                action="PAYMENT_FAILED",
                details=f"Payment {pay_id} failed for Appointment #{appointment.id}."
            )
            
            Notification.objects.create(
                user=request.user,
                message=f"Payment for appointment with Dr. {appointment.doctor.user.get_full_name()} failed. Please try again.",
                notif_type="INFO"
            )
            
            return render(request, 'payments/payment_failed.html', {'payment': payment, 'appointment': appointment})

        # Successful Payment
        payment = Payment.objects.create(
            payment_id=pay_id,
            transaction_id=txn_id,
            patient=request.user,
            doctor=appointment.doctor,
            appointment=appointment,
            amount=consultation_fee,
            platform_fee=platform_fee,
            tax=tax,
            discount=discount,
            total_amount=total_amount,
            payment_method=payment_method,
            card_type=card_type_detected,
            last_four_digits=last_four,
            payment_status=Payment.PaymentStatus.PAID,
            masked_payment_reference=masked_ref,
            invoice_number=inv_num,
            payment_date=timezone.now(),
            remarks="Payment processed successfully via simulator."
        )

        # Update Appointment status to APPROVED / CONFIRMED
        appointment.status = Appointment.Status.APPROVED
        appointment.save(update_fields=['status'])

        # Create Invoice Record & PDF
        invoice_obj = Invoice.objects.create(invoice_number=inv_num, payment=payment)
        generate_invoice_pdf(payment)

        # In-App Notifications
        Notification.objects.create(
            user=request.user,
            message=f"Payment Successful! ₹{payment.total_amount:.2f} paid for Appointment #{appointment.id} with Dr. {appointment.doctor.user.get_full_name()}.",
            notif_type="APPOINTMENT",
            link=f"/payments/success/{payment.payment_id}/"
        )

        Notification.objects.create(
            user=appointment.doctor.user,
            message=f"New Paid Appointment confirmed with {request.user.get_full_name()} on {appointment.date}.",
            notif_type="APPOINTMENT"
        )

        # Send Emails via SMTP
        send_payment_success_email(payment)
        send_doctor_payment_notification(payment)

        # Audit Log
        AuditLog.objects.create(
            actor=request.user,
            action="PAYMENT_SUCCESSFUL",
            details=f"Paid ₹{payment.total_amount:.2f} (Txn: {payment.transaction_id}) for Appointment #{appointment.id}."
        )

        messages.success(request, f"Payment Successful! Invoice {payment.invoice_number} generated.")
        return redirect('payment_success', payment_id=payment.payment_id)


@patient_required
def payment_success_view(request, payment_id):
    """
    Displays payment confirmation summary page (idempotent for refresh).
    """
    payment = get_object_or_404(Payment, payment_id=payment_id, patient=request.user)
    return render(request, 'payments/payment_success.html', {'payment': payment})


@patient_required
def patient_payments_list_view(request):
    """
    Patient Payments Dashboard list with date/doctor/status filtering.
    """
    payments = Payment.objects.filter(patient=request.user).select_related('doctor__user', 'doctor__specialization', 'appointment')

    # Filtering
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '').strip()
    date_filter = request.GET.get('date', '').strip()

    if search_query:
        payments = payments.filter(
            Q(doctor__user__first_name__icontains=search_query) |
            Q(doctor__user__last_name__icontains=search_query) |
            Q(invoice_number__icontains=search_query) |
            Q(transaction_id__icontains=search_query)
        )

    if status_filter:
        payments = payments.filter(payment_status=status_filter)

    if date_filter:
        payments = payments.filter(created_at__date=date_filter)

    context = {
        'payments': payments,
        'search_query': search_query,
        'status_filter': status_filter,
        'date_filter': date_filter,
        'status_choices': Payment.PaymentStatus.choices,
    }
    return render(request, 'payments/patient_payments.html', context)


@login_required
def download_invoice_view(request, invoice_number):
    """
    Secure file download view for invoices (patient owner, doctor, or admin only).
    """
    payment = get_object_or_404(Payment, invoice_number=invoice_number)

    # Permission check
    is_patient = payment.patient == request.user
    is_doctor = payment.doctor.user == request.user
    is_admin = request.user.role == 'ADMIN' or request.user.is_staff

    if not (is_patient or is_doctor or is_admin):
        AuditLog.objects.create(
            actor=request.user,
            action="UNAUTHORIZED_INVOICE_ACCESS",
            details=f"Attempted to access invoice {invoice_number} without permission."
        )
        raise Http404("Invoice not found or permission denied.")

    if not payment.invoice_pdf or not os.path.exists(payment.invoice_pdf.path):
        # Regenerate on the fly if missing
        generate_invoice_pdf(payment)

    AuditLog.objects.create(
        actor=request.user,
        action="INVOICE_DOWNLOADED",
        details=f"Downloaded invoice PDF {invoice_number}."
    )

    response = FileResponse(open(payment.invoice_pdf.path, 'rb'), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{payment.invoice_number}.pdf"'
    return response


@admin_required
def admin_payment_analytics_view(request):
    """
    Admin Dashboard for Payment Analytics & Revenue breakdown.
    """
    payments = Payment.objects.all().select_related('patient', 'doctor__user', 'doctor__specialization')
    
    total_revenue = payments.filter(payment_status=Payment.PaymentStatus.PAID).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00')
    
    today = timezone.now().date()
    today_revenue = payments.filter(payment_status=Payment.PaymentStatus.PAID, created_at__date=today).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00')
    
    # Counts
    total_txns = payments.count()
    successful_count = payments.filter(payment_status=Payment.PaymentStatus.PAID).count()
    pending_count = payments.filter(payment_status=Payment.PaymentStatus.PENDING).count()
    failed_count = payments.filter(payment_status=Payment.PaymentStatus.FAILED).count()
    refunded_count = payments.filter(payment_status=Payment.PaymentStatus.REFUNDED).count()

    # Revenue by Doctor
    revenue_by_doctor = payments.filter(payment_status=Payment.PaymentStatus.PAID).values(
        'doctor__user__first_name', 'doctor__user__last_name'
    ).annotate(total=Sum('total_amount'), count=Count('id')).order_by('-total')[:10]

    # Revenue by Payment Method
    revenue_by_method = payments.filter(payment_status=Payment.PaymentStatus.PAID).values(
        'payment_method'
    ).annotate(total=Sum('total_amount'), count=Count('id')).order_by('-total')

    # Refunds list
    refunds = Refund.objects.all().select_related('payment__patient', 'processed_by')

    context = {
        'total_revenue': total_revenue,
        'today_revenue': today_revenue,
        'total_txns': total_txns,
        'successful_count': successful_count,
        'pending_count': pending_count,
        'failed_count': failed_count,
        'refunded_count': refunded_count,
        'revenue_by_doctor': revenue_by_doctor,
        'revenue_by_method': revenue_by_method,
        'payments': payments[:50],
        'refunds': refunds,
    }
    return render(request, 'payments/admin_analytics.html', context)


@admin_required
def process_refund_view(request, payment_id):
    """
    Admin simulation to trigger full/partial refund on paid transaction.
    """
    payment = get_object_or_404(Payment, payment_id=payment_id)

    if request.method == 'POST':
        refund_type = request.POST.get('refund_type', 'FULL') # FULL or PARTIAL
        refund_reason = request.POST.get('refund_reason', '').strip()
        custom_amount_str = request.POST.get('refund_amount', '').strip()

        if payment.payment_status != Payment.PaymentStatus.PAID:
            messages.error(request, "Only PAID transactions can be refunded.")
            return redirect('admin_payment_analytics')

        if refund_type == 'FULL':
            refund_amount = payment.total_amount
        else:
            try:
                refund_amount = Decimal(custom_amount_str)
                if refund_amount <= 0 or refund_amount > payment.total_amount:
                    messages.error(request, "Invalid partial refund amount.")
                    return redirect('admin_payment_analytics')
            except Exception:
                messages.error(request, "Please specify a valid numeric refund amount.")
                return redirect('admin_payment_analytics')

        with transaction.atomic():
            refund = Refund.objects.create(
                refund_id=generate_refund_id(),
                payment=payment,
                refund_amount=refund_amount,
                refund_reason=refund_reason or "Admin initiated simulation refund.",
                refund_status=Refund.RefundStatus.COMPLETED,
                processed_by=request.user,
                processed_at=timezone.now()
            )

            payment.payment_status = Payment.PaymentStatus.REFUNDED
            payment.remarks = f"Refunded ₹{refund_amount:.2f} on {timezone.now().strftime('%Y-%m-%d')}"
            payment.save(update_fields=['payment_status', 'remarks'])

            # Send Email & In-App Notification
            send_refund_email(refund)

            Notification.objects.create(
                user=payment.patient,
                message=f"Refund Approved! ₹{refund_amount:.2f} refunded for Invoice #{payment.invoice_number}.",
                notif_type="INFO"
            )

            AuditLog.objects.create(
                actor=request.user,
                action="REFUND_PROCESSED",
                details=f"Processed ₹{refund_amount:.2f} refund for Payment ID {payment.payment_id}."
            )

            messages.success(request, f"Refund {refund.refund_id} completed successfully!")
            return redirect('admin_payment_analytics')

    return redirect('admin_payment_analytics')
