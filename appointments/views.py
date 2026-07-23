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

                        messages.success(request, "Appointment request submitted successfully! Pending doctor approval.")
                        return redirect('patient_appointments_list')

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
    appointments = Appointment.objects.filter(patient=request.user).select_related('doctor__user', 'doctor__specialization').order_by('-date')
    return render(request, 'appointments/patient_appointments.html', {'appointments': appointments})


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
