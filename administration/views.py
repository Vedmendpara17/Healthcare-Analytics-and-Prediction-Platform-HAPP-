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
    today = timezone.now().date()
    now_time = timezone.now().time().strftime('%H:%M')

    appointments = Appointment.objects.select_related('patient', 'doctor__user', 'doctor__specialization').all()

    if status_filter == 'expired':
        appointments = appointments.filter(
            Q(date__lt=today) | Q(date=today, time_slot__lt=now_time)
        ).exclude(status__in=['COMPLETED', 'CANCELLED', 'REJECTED'])
    elif status_filter != 'all':
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


# --- Admin Medical Reports & Analytics Views ---
from django.db.models import Sum
from django.core.paginator import Paginator
from patients.models import MedicalReport

@admin_required
def admin_medical_reports_view(request):
    today = timezone.now().date()
    first_of_month = today.replace(day=1)

    all_reports = MedicalReport.objects.filter(is_deleted=False)

    total_reports = all_reports.count()
    uploaded_today = all_reports.filter(uploaded_at__date=today).count()
    uploaded_this_month = all_reports.filter(uploaded_at__date__gte=first_of_month).count()

    total_bytes = all_reports.aggregate(total=Sum('file_size'))['total'] or 0
    if total_bytes < 1024 * 1024:
        storage_usage_str = f"{round(total_bytes / 1024, 1)} KB"
    elif total_bytes < 1024 * 1024 * 1024:
        storage_usage_str = f"{round(total_bytes / (1024 * 1024), 2)} MB"
    else:
        storage_usage_str = f"{round(total_bytes / (1024 * 1024 * 1024), 2)} GB"

    # Category breakdown for Chart.js
    category_counts = list(
        all_reports.values('report_category')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    category_labels = [item['report_category'] for item in category_counts]
    category_data = [item['count'] for item in category_counts]

    import json
    category_labels_json = json.dumps(category_labels)
    category_data_json = json.dumps(category_data)

    # Top Uploaders
    top_uploaders = list(
        all_reports.values('patient__id', 'patient__user__first_name', 'patient__user__last_name', 'patient__user__username')
        .annotate(count=Count('id'), total_size=Sum('file_size'))
        .order_by('-count')[:5]
    )

    # Search and Filter
    query = request.GET.get('q', '').strip()
    category_filter = request.GET.get('category', '').strip()
    patient_filter = request.GET.get('patient_id', '').strip()
    doctor_filter = request.GET.get('doctor_id', '').strip()
    status_filter = request.GET.get('status', '').strip()

    reports_qs = all_reports.select_related('patient', 'patient__user', 'doctor', 'doctor__user', 'appointment')

    if query:
        reports_qs = reports_qs.filter(
            Q(report_name__icontains=query) |
            Q(patient__user__first_name__icontains=query) |
            Q(patient__user__last_name__icontains=query) |
            Q(doctor__user__first_name__icontains=query) |
            Q(doctor__user__last_name__icontains=query)
        )

    if category_filter:
        reports_qs = reports_qs.filter(report_category=category_filter)

    if patient_filter:
        reports_qs = reports_qs.filter(patient_id=patient_filter)

    if doctor_filter:
        reports_qs = reports_qs.filter(doctor_id=doctor_filter)

    if status_filter:
        reports_qs = reports_qs.filter(review_status=status_filter)

    reports_qs = reports_qs.order_by('-uploaded_at')

    paginator = Paginator(reports_qs, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    patients_list = PatientProfile.objects.select_related('user').all()
    doctors_list = DoctorProfile.objects.select_related('user').all()

    context = {
        'total_reports': total_reports,
        'uploaded_today': uploaded_today,
        'uploaded_this_month': uploaded_this_month,
        'storage_usage_str': storage_usage_str,
        'category_labels_json': category_labels_json,
        'category_data_json': category_data_json,
        'top_uploaders': top_uploaders,
        'page_obj': page_obj,
        'reports': page_obj.object_list,
        'categories': MedicalReport.REPORT_CATEGORIES,
        'patients_list': patients_list,
        'doctors_list': doctors_list,
        'search_query': query,
        'selected_category': category_filter,
        'selected_patient': patient_filter,
        'selected_doctor': doctor_filter,
        'selected_status': status_filter,
    }
    return render(request, 'administration/medical_reports.html', context)


@admin_required
def admin_delete_medical_report_view(request, report_id):
    report = get_object_or_404(MedicalReport, id=report_id)
    report_name = report.report_name
    report.is_deleted = True
    report.save(update_fields=['is_deleted'])

    AuditLog.objects.create(
        actor=request.user,
        action="ADMIN_DELETE_MEDICAL_REPORT",
        details=f"Admin removed report '{report_name}' (ID {report.id})",
        ip_address=request.META.get('REMOTE_ADDR')
    )

    messages.success(request, f"Report '{report_name}' has been deleted from system registry.")
    return redirect('admin_medical_reports')


@admin_required
def admin_security_dashboard_view(request):
    logs_qs = AuditLog.objects.select_related('actor').order_by('-timestamp')

    total_logs = AuditLog.objects.count()
    successful_logins = AuditLog.objects.filter(action__in=['LOGIN_SUCCESS', 'USER_LOGIN']).count()
    failed_logins = AuditLog.objects.filter(action='FAILED_LOGIN').count()
    otp_generated_count = AuditLog.objects.filter(action='OTP_GENERATED').count()
    otp_failed_count = AuditLog.objects.filter(action='OTP_FAILED').count()
    password_reset_count = AuditLog.objects.filter(action__in=['PASSWORD_RESET', 'PASSWORD_RESET_REQUEST']).count()
    locked_accounts_count = User.objects.filter(account_locked_until__isnull=False).count()

    query = request.GET.get('q', '').strip()
    action_filter = request.GET.get('action', '').strip()

    if query:
        logs_qs = logs_qs.filter(
            Q(actor__username__icontains=query) |
            Q(actor__first_name__icontains=query) |
            Q(actor__last_name__icontains=query) |
            Q(details__icontains=query) |
            Q(ip_address__icontains=query)
        )

    if action_filter:
        logs_qs = logs_qs.filter(action=action_filter)

    paginator = Paginator(logs_qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'total_logs': total_logs,
        'successful_logins': successful_logins,
        'failed_logins': failed_logins,
        'otp_generated_count': otp_generated_count,
        'otp_failed_count': otp_failed_count,
        'password_reset_count': password_reset_count,
        'locked_accounts_count': locked_accounts_count,
        'page_obj': page_obj,
        'logs': page_obj.object_list,
        'query': query,
        'action_filter': action_filter
    }
    return render(request, 'administration/security_dashboard.html', context)
