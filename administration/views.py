import csv
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import HttpResponse
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta

from accounts.decorators import admin_required
from accounts.models import User
from doctors.models import DoctorProfile
from patients.models import PatientProfile
from appointments.models import Appointment, Specialization, EmailLog
from predictions.models import RiskAssessment
from core.models import AuditLog, Notification, Review

@admin_required
def admin_dashboard_view(request):
    total_doctors = DoctorProfile.objects.count()
    pending_doctors_count = DoctorProfile.objects.filter(is_approved=False).count()
    total_patients = PatientProfile.objects.count()
    total_appointments = Appointment.objects.count()

    today = timezone.now().date()
    start_of_week = today - timedelta(days=today.weekday())
    appointments_this_week = Appointment.objects.filter(date__gte=start_of_week).count()

    # Risk level distribution
    low_risk = RiskAssessment.objects.filter(computed_level='LOW').count()
    med_risk = RiskAssessment.objects.filter(computed_level='MEDIUM').count()
    high_risk = RiskAssessment.objects.filter(computed_level='HIGH').count()

    recent_appointments = Appointment.objects.select_related('patient', 'doctor__user').order_by('-created_at')[:5]
    pending_doctors = DoctorProfile.objects.filter(is_approved=False).select_related('user', 'specialization')[:5]
    recent_logs = AuditLog.objects.select_related('actor').order_by('-timestamp')[:8]
    recent_email_logs = EmailLog.objects.select_related('appointment').order_by('-sent_at')[:8]

    context = {
        'total_doctors': total_doctors,
        'pending_doctors_count': pending_doctors_count,
        'total_patients': total_patients,
        'total_appointments': total_appointments,
        'appointments_this_week': appointments_this_week,
        'low_risk': low_risk,
        'med_risk': med_risk,
        'high_risk': high_risk,
        'recent_appointments': recent_appointments,
        'pending_doctors': pending_doctors,
        'recent_logs': recent_logs,
        'recent_email_logs': recent_email_logs,
    }
    return render(request, 'administration/dashboard.html', context)


@admin_required
def manage_doctors_view(request):
    query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', 'all')

    doctors = DoctorProfile.objects.select_related('user', 'specialization').all()

    if query:
        doctors = doctors.filter(
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(license_number__icontains=query) |
            Q(hospital_name__icontains=query)
        )

    if status_filter == 'pending':
        doctors = doctors.filter(is_approved=False)
    elif status_filter == 'approved':
        doctors = doctors.filter(is_approved=True)

    return render(request, 'administration/manage_doctors.html', {
        'doctors': doctors,
        'query': query,
        'status_filter': status_filter
    })


@admin_required
def approve_doctor_view(request, doctor_id):
    doctor = get_object_or_404(DoctorProfile, id=doctor_id)
    doctor.is_approved = True
    doctor.save()

    # Notify doctor in-app
    Notification.objects.create(
        user=doctor.user,
        message="Congratulations! Your doctor profile has been verified and approved by the administrator. You can now log in.",
        notif_type="ANNOUNCEMENT"
    )

    # Send Email Notification to Doctor
    try:
        from django.core.mail import send_mail
        from django.conf import settings
        send_mail(
            subject="Doctor Account Approved - Healthcare Analytics System",
            message=f"Dear Dr. {doctor.user.get_full_name()},\n\nYour Medical License ({doctor.license_number}) has been verified and your account has been APPROVED by system administration.\n\nYou can now log in at http://127.0.0.1:8000/accounts/login/ and access your doctor dashboard.\n\nThank you,\nHealthcare Analytics System",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[doctor.user.email],
            fail_silently=True
        )
    except Exception:
        pass

    AuditLog.objects.create(
        actor=request.user,
        action="APPROVE_DOCTOR",
        details=f"Approved doctor account: Dr. {doctor.user.get_full_name()} ({doctor.license_number})"
    )

    messages.success(request, f"Doctor account Dr. {doctor.user.get_full_name()} has been approved and notified!")
    return redirect('manage_doctors')


@admin_required
def toggle_doctor_status_view(request, doctor_id):
    doctor = get_object_or_404(DoctorProfile, id=doctor_id)
    doctor.is_approved = not doctor.is_approved
    doctor.save()
    status_str = "Approved" if doctor.is_approved else "Deactivated"
    messages.info(request, f"Doctor account Dr. {doctor.user.get_full_name()} status changed to {status_str}.")
    return redirect('manage_doctors')


@admin_required
def manage_patients_view(request):
    query = request.GET.get('q', '').strip()
    patients = PatientProfile.objects.select_related('user').all()

    if query:
        patients = patients.filter(
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(user__email__icontains=query) |
            Q(user__phone__icontains=query)
        )

    return render(request, 'administration/manage_patients.html', {
        'patients': patients,
        'query': query
    })


@admin_required
def view_patient_detail_view(request, patient_id):
    patient = get_object_or_404(PatientProfile, id=patient_id)
    appointments = Appointment.objects.filter(patient=patient.user).select_related('doctor__user')
    assessments = RiskAssessment.objects.filter(patient=patient).order_by('-created_at')
    records = patient.medical_records.all()

    return render(request, 'administration/patient_detail.html', {
        'patient': patient,
        'appointments': appointments,
        'assessments': assessments,
        'records': records
    })


@admin_required
def manage_appointments_view(request):
    status_filter = request.GET.get('status', 'all')
    appointments = Appointment.objects.select_related('patient', 'doctor__user', 'doctor__specialization').all()

    if status_filter != 'all':
        appointments = appointments.filter(status=status_filter.upper())

    return render(request, 'administration/manage_appointments.html', {
        'appointments': appointments,
        'status_filter': status_filter
    })


@admin_required
def manage_specializations_view(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        icon = request.POST.get('icon', 'bi-heart-pulse').strip()
        if name:
            Specialization.objects.get_or_create(
                name=name,
                defaults={'description': description, 'icon': icon}
            )
            messages.success(request, f"Specialization '{name}' created successfully.")
            return redirect('manage_specializations')

    specs = Specialization.objects.annotate(doctor_count=Count('doctors')).all()
    return render(request, 'administration/manage_specializations.html', {'specializations': specs})


@admin_required
def admin_analytics_view(request):
    risk_by_level = {
        'LOW': RiskAssessment.objects.filter(computed_level='LOW').count(),
        'MEDIUM': RiskAssessment.objects.filter(computed_level='MEDIUM').count(),
        'HIGH': RiskAssessment.objects.filter(computed_level='HIGH').count(),
    }
    
    assessments = RiskAssessment.objects.all()
    under_30 = 0
    age_30_50 = 0
    over_50 = 0

    for a in assessments:
        if a.age < 30:
            under_30 += 1
        elif a.age <= 50:
            age_30_50 += 1
        else:
            over_50 += 1

    return render(request, 'administration/analytics.html', {
        'risk_by_level': risk_by_level,
        'under_30': under_30,
        'age_30_50': age_30_50,
        'over_50': over_50,
        'total_assessments': assessments.count()
    })



@admin_required
def export_appointments_csv_view(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="system_appointments_report.csv"'

    writer = csv.writer(response)
    writer.writerow(['ID', 'Patient Name', 'Doctor Name', 'Specialization', 'Date', 'Slot', 'Status', 'Reason'])

    appointments = Appointment.objects.select_related('patient', 'doctor__user', 'doctor__specialization').all()
    for app in appointments:
        writer.writerow([
            app.id,
            app.patient.get_full_name(),
            f"Dr. {app.doctor.user.get_full_name()}",
            app.doctor.specialization.name if app.doctor.specialization else 'N/A',
            app.date,
            app.get_time_slot_display_text(),
            app.status,
            app.reason
        ])

    return response


@admin_required
def broadcast_announcement_view(request):
    if request.method == 'POST':
        target = request.POST.get('target', 'all')
        message = request.POST.get('message', '').strip()

        if message:
            users = User.objects.all()
            if target == 'doctors':
                users = users.filter(role=User.Role.DOCTOR)
            elif target == 'patients':
                users = users.filter(role=User.Role.PATIENT)

            count = 0
            for u in users:
                Notification.objects.create(
                    user=u,
                    message=f"[Announcement] {message}",
                    notif_type="ANNOUNCEMENT"
                )
                count += 1

            messages.success(request, f"Broadcast sent successfully to {count} users!")
            return redirect('admin_dashboard')

    return render(request, 'administration/broadcast.html')
