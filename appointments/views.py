from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from datetime import datetime, date

from accounts.decorators import patient_required, role_required
from doctors.models import DoctorProfile
from appointments.models import Appointment, Specialization, EmailLog
from appointments.emails import send_appointment_email
from core.models import Notification, AuditLog

@patient_required
def book_appointment_view(request, doctor_id=None):
    doctor = None
    if doctor_id:
        doctor = get_object_or_404(DoctorProfile, id=doctor_id, is_approved=True)

    doctors = DoctorProfile.objects.filter(is_approved=True).select_related('user', 'specialization')
    specializations = Specialization.objects.all()

    if request.method == 'POST':
        selected_doctor_id = request.POST.get('doctor_id')
        booking_date_str = request.POST.get('date')
        time_slot = request.POST.get('time_slot')
        reason = request.POST.get('reason', '').strip()

        if not (selected_doctor_id and booking_date_str and time_slot and reason):
            messages.error(request, "Please fill in all required appointment booking fields.")
        else:
            doc = get_object_or_404(DoctorProfile, id=selected_doctor_id, is_approved=True)
            booking_date = datetime.strptime(booking_date_str, '%Y-%m-%d').date()

            if booking_date < date.today():
                messages.error(request, "Cannot book appointments in the past.")
            else:
                # Check slot availability
                existing = Appointment.objects.filter(
                    doctor=doc,
                    date=booking_date,
                    time_slot=time_slot
                ).exclude(status__in=[Appointment.Status.CANCELLED, Appointment.Status.REJECTED]).exists()

                if existing:
                    messages.error(request, f"Selected time slot ({time_slot}) with Dr. {doc.user.get_full_name()} is already booked. Please choose another slot.")
                else:
                    try:
                        appointment = Appointment.objects.create(
                            patient=request.user,
                            doctor=doc,
                            date=booking_date,
                            time_slot=time_slot,
                            reason=reason,
                            status=Appointment.Status.PENDING
                        )

                        # Notify Doctor via in-app notification
                        Notification.objects.create(
                            user=doc.user,
                            message=f"New appointment request from {request.user.get_full_name()} for {booking_date} ({appointment.get_time_slot_display_text()}).",
                            notif_type="APPOINTMENT"
                        )

                        # Trigger Automated Email to Doctor
                        send_appointment_email(EmailLog.EmailType.NEW_REQUEST, appointment)

                        AuditLog.objects.create(
                            actor=request.user,
                            action="BOOK_APPOINTMENT",
                            details=f"Booked appointment ID #{appointment.id} with Dr. {doc.user.get_full_name()}"
                        )

                        messages.info(request, "Appointment details selected. Please proceed to Payment Summary & Confirmation.")
                        return redirect('checkout', appointment_id=appointment.id)

                    except IntegrityError:
                        messages.error(request, "This time slot was booked just a second ago. Please select another slot.")

    context = {
        'selected_doctor': doctor,
        'doctors': doctors,
        'specializations': specializations,
        'time_slots': Appointment.TIME_SLOT_CHOICES,
        'min_date': date.today().strftime('%Y-%m-%d'),
    }
    return render(request, 'appointments/book_appointment.html', context)


@login_required
def available_slots_api(request):
    doctor_id = request.GET.get('doctor_id')
    date_str = request.GET.get('date')

    if not doctor_id or not date_str:
        return JsonResponse({'slots': []})

    try:
        booking_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        doc = DoctorProfile.objects.get(id=doctor_id)
    except (ValueError, DoctorProfile.DoesNotExist):
        return JsonResponse({'slots': []})

    # Get active booked slots
    booked_slots = list(Appointment.objects.filter(
        doctor=doc,
        date=booking_date
    ).exclude(status__in=[Appointment.Status.CANCELLED, Appointment.Status.REJECTED]).values_list('time_slot', flat=True))

    all_slots = []
    for code, label in Appointment.TIME_SLOT_CHOICES:
        all_slots.append({
            'code': code,
            'label': label,
            'available': code not in booked_slots
        })

    return JsonResponse({'slots': all_slots})


@patient_required
def patient_appointments_list_view(request):
    appointments = list(Appointment.objects.filter(patient=request.user).select_related('doctor__user', 'doctor__specialization').order_by('-date'))
    
    total_count = len(appointments)
    upcoming_count = sum(1 for a in appointments if not a.is_past and a.status not in ['CANCELLED', 'REJECTED'])
    rescheduled_count = sum(1 for a in appointments if a.status == 'RESCHEDULED')
    cancelled_count = sum(1 for a in appointments if a.status in ['CANCELLED', 'REJECTED'])

    context = {
        'appointments': appointments,
        'total_count': total_count,
        'upcoming_count': upcoming_count,
        'rescheduled_count': rescheduled_count,
        'cancelled_count': cancelled_count,
    }
    return render(request, 'appointments/patient_appointments.html', context)


@login_required
def cancel_appointment_view(request, appointment_id):
    appointment = get_object_or_404(Appointment, id=appointment_id)
    
    # Gating: must be patient owner, attending doctor, or admin
    if request.user != appointment.patient and request.user != appointment.doctor.user and not request.user.is_admin():
        messages.error(request, "Permission denied.")
        return redirect('dashboard_redirect')

    if appointment.status in [Appointment.Status.COMPLETED, Appointment.Status.CANCELLED]:
        messages.warning(request, f"Appointment is already {appointment.get_status_display().lower()}.")
    else:
        is_patient_cancelling = (request.user == appointment.patient)
        appointment.status = Appointment.Status.CANCELLED
        appointment.save()

        # Send in-app notification to counterpart
        target_user = appointment.doctor.user if is_patient_cancelling else appointment.patient
        Notification.objects.create(
            user=target_user,
            message=f"Appointment on {appointment.date} ({appointment.get_time_slot_display_text()}) was cancelled by {request.user.get_full_name()}.",
            notif_type="APPOINTMENT"
        )

        # Trigger automated Email Notification
        if is_patient_cancelling:
            send_appointment_email(EmailLog.EmailType.CANCELLED_BY_PATIENT, appointment)
        else:
            send_appointment_email(EmailLog.EmailType.CANCELLED_BY_DOCTOR, appointment)

        messages.info(request, "Appointment cancelled successfully.")

    return redirect('dashboard_redirect')


@login_required
def calendar_events_api(request):
    user = request.user
    events = []

    if user.is_doctor():
        doctor = get_object_or_404(DoctorProfile, user=user)
        appointments = Appointment.objects.filter(doctor=doctor).select_related('patient')
        for app in appointments:
            events.append({
                'id': app.id,
                'title': f"{app.patient.get_full_name()} ({app.get_status_display()})",
                'start': f"{app.date}T{app.time_slot}:00",
                'status': app.status,
                'color': '#22C55E' if app.status == 'APPROVED' else ('#EF4444' if app.status in ['CANCELLED', 'REJECTED'] else '#F59E0B')
            })
    elif user.is_patient():
        appointments = Appointment.objects.filter(patient=user).select_related('doctor__user')
        for app in appointments:
            events.append({
                'id': app.id,
                'title': f"Dr. {app.doctor.user.get_full_name()} ({app.get_status_display()})",
                'start': f"{app.date}T{app.time_slot}:00",
                'status': app.status,
                'color': '#22C55E' if app.status == 'APPROVED' else ('#EF4444' if app.status in ['CANCELLED', 'REJECTED'] else '#F59E0B')
            })

    return JsonResponse(events, safe=False)


@patient_required
def reschedule_appointment_view(request, appointment_id):
    appointment = get_object_or_404(Appointment, id=appointment_id, patient=request.user)

    if appointment.status in [Appointment.Status.COMPLETED, Appointment.Status.CANCELLED, Appointment.Status.REJECTED]:
        messages.error(request, f"Cannot reschedule an appointment that is already {appointment.get_status_display().lower()}.")
        return redirect('patient_appointments_list')

    if request.method == 'POST':
        new_date_str = request.POST.get('date')
        new_time_slot = request.POST.get('time_slot')
        reason = request.POST.get('reason', '').strip()

        if not new_date_str or not new_time_slot:
            messages.error(request, "Please select both a date and a time slot to reschedule.")
        else:
            try:
                new_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
            except ValueError:
                messages.error(request, "Invalid date format.")
                return redirect('reschedule_appointment', appointment_id=appointment.id)

            if new_date < date.today():
                messages.error(request, "Cannot reschedule to a past date.")
                return redirect('reschedule_appointment', appointment_id=appointment.id)

            if new_date == date.today():
                try:
                    hour, minute = map(int, new_time_slot.split(':'))
                    slot_time = datetime.strptime(f"{hour}:{minute}", "%H:%M").time()
                    if datetime.now().time() > slot_time:
                        messages.error(request, "Selected time slot has already passed for today. Please pick a future slot.")
                        return redirect('reschedule_appointment', appointment_id=appointment.id)
                except Exception:
                    pass

            # Prevent duplicate appointment for the same patient on same date and slot
            duplicate_patient_app = Appointment.objects.filter(
                patient=request.user,
                date=new_date,
                time_slot=new_time_slot
            ).exclude(id=appointment.id).exclude(status__in=[Appointment.Status.CANCELLED, Appointment.Status.REJECTED]).exists()

            if duplicate_patient_app:
                messages.error(request, "You already have another active appointment scheduled at this exact date and time.")
                return redirect('reschedule_appointment', appointment_id=appointment.id)

            # Check doctor slot conflict
            doctor_slot_taken = Appointment.objects.filter(
                doctor=appointment.doctor,
                date=new_date,
                time_slot=new_time_slot
            ).exclude(id=appointment.id).exclude(status__in=[Appointment.Status.CANCELLED, Appointment.Status.REJECTED]).exists()

            if doctor_slot_taken:
                messages.error(request, f"The selected time slot ({new_time_slot}) with Dr. {appointment.doctor.user.get_full_name()} is already booked. Please choose another slot.")
                return redirect('reschedule_appointment', appointment_id=appointment.id)

            # Update Appointment
            previous_date_time = f"{appointment.date.strftime('%B %d, %Y')} ({appointment.get_time_slot_display_text()})"
            appointment.date = new_date
            appointment.time_slot = new_time_slot
            appointment.status = Appointment.Status.RESCHEDULED
            appointment.save()

            # Send In-App Notification to Doctor
            Notification.objects.create(
                user=appointment.doctor.user,
                message=f"Patient {request.user.get_full_name()} rescheduled Appointment #{appointment.id} to {new_date.strftime('%B %d, %Y')} ({appointment.get_time_slot_display_text()}).",
                notif_type="APPOINTMENT"
            )

            # Send Email Notification to Doctor & Patient
            send_appointment_email(EmailLog.EmailType.RESCHEDULED_DOCTOR, appointment, extra_context={
                'previous_date_time': previous_date_time,
                'reschedule_reason': reason
            })
            send_appointment_email(EmailLog.EmailType.RESCHEDULED, appointment, extra_context={
                'previous_date_time': previous_date_time,
                'reschedule_reason': reason
            })

            AuditLog.objects.create(
                actor=request.user,
                action="RESCHEDULE_APPOINTMENT",
                details=f"Rescheduled appointment #{appointment.id} to {new_date} ({new_time_slot})"
            )

            messages.success(request, f"Appointment successfully rescheduled to {new_date.strftime('%B %d, %Y')} ({appointment.get_time_slot_display_text()})!")
            return redirect('patient_appointments_list')

    context = {
        'appointment': appointment,
        'doctor': appointment.doctor,
        'min_date': date.today().strftime('%Y-%m-%d'),
        'time_slots': Appointment.TIME_SLOT_CHOICES,
    }
    return render(request, 'appointments/reschedule_appointment.html', context)
