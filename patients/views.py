from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q

from accounts.decorators import patient_required
from patients.models import PatientProfile, MedicalRecord
from doctors.models import DoctorProfile
from appointments.models import Appointment, Specialization, Prescription
from predictions.models import RiskAssessment
from core.models import Notification, Review

@patient_required
def patient_dashboard_view(request):
    patient = get_object_or_404(PatientProfile, user=request.user)
    today = timezone.now().date()

    upcoming_appointments = Appointment.objects.filter(
        patient=request.user,
        date__gte=today,
        status__in=[Appointment.Status.PENDING, Appointment.Status.APPROVED]
    ).select_related('doctor__user', 'doctor__specialization')[:3]

    latest_assessment = RiskAssessment.objects.filter(patient=patient).first()
    recent_prescriptions = Prescription.objects.filter(appointment__patient=request.user).order_by('-created_at')[:3]

    # Health tips based on risk level
    health_tips = []
    if latest_assessment:
        level = latest_assessment.final_level
        if level == 'HIGH':
            health_tips = [
                "Schedule a follow-up consultation with your attending physician.",
                "Maintain a daily blood pressure and fasting blood glucose log.",
                "Adhere strictly to prescribed medications and restrict daily sodium intake."
            ]
        elif level == 'MEDIUM':
            health_tips = [
                "Aim for 30 minutes of moderate aerobic exercise 5 days a week.",
                "Reduce processed sugars and increase dietary fiber from vegetables and whole grains.",
                "Monitor blood pressure and body weight weekly."
            ]
        else:
            health_tips = [
                "Great job! Continue your healthy balanced diet and active lifestyle.",
                "Stay well hydrated by drinking 8-10 glasses of water daily.",
                "Schedule your routine annual wellness health checkup."
            ]
    else:
        health_tips = [
            "Complete your initial clinical risk assessment during your next doctor consultation.",
            "Keep your medical profile and emergency contact details up to date."
        ]

    context = {
        'patient': patient,
        'upcoming_appointments': upcoming_appointments,
        'latest_assessment': latest_assessment,
        'recent_prescriptions': recent_prescriptions,
        'health_tips': health_tips,
    }
    return render(request, 'patients/dashboard.html', context)


@patient_required
def doctor_directory_view(request):
    query = request.GET.get('q', '').strip()
    spec_id = request.GET.get('specialization', '')

    doctors = DoctorProfile.objects.filter(is_approved=True).select_related('user', 'specialization')
    specializations = Specialization.objects.all()

    if query:
        doctors = doctors.filter(
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(hospital_name__icontains=query) |
            Q(qualification__icontains=query)
        )

    if spec_id and spec_id.isdigit():
        doctors = doctors.filter(specialization_id=int(spec_id))

    return render(request, 'patients/doctor_directory.html', {
        'doctors': doctors,
        'specializations': specializations,
        'query': query,
        'selected_spec': spec_id
    })


@patient_required
def patient_risk_history_view(request):
    patient = get_object_or_404(PatientProfile, user=request.user)
    assessments = RiskAssessment.objects.filter(patient=patient).select_related('doctor__user').order_by('-created_at')

    # Data for Chart.js
    trend_labels = [a.created_at.strftime('%b %d, %Y') for a in reversed(assessments)]
    trend_scores = [a.computed_score for a in reversed(assessments)]

    return render(request, 'patients/risk_history.html', {
        'patient': patient,
        'assessments': assessments,
        'trend_labels': trend_labels,
        'trend_scores': trend_scores,
    })


@patient_required
def patient_prescriptions_view(request):
    return redirect('patient_prescription_list')


@patient_required
def edit_patient_profile_view(request):
    patient = get_object_or_404(PatientProfile, user=request.user)

    if request.method == 'POST':
        patient.gender = request.POST.get('gender', patient.gender)
        patient.blood_group = request.POST.get('blood_group', patient.blood_group)
        patient.height_cm = float(request.POST.get('height_cm', patient.height_cm))
        patient.weight_kg = float(request.POST.get('weight_kg', patient.weight_kg))
        patient.address = request.POST.get('address', patient.address)
        patient.emergency_contact_name = request.POST.get('emergency_contact_name', patient.emergency_contact_name)
        patient.emergency_contact_phone = request.POST.get('emergency_contact_phone', patient.emergency_contact_phone)
        patient.chronic_conditions = request.POST.get('chronic_conditions', patient.chronic_conditions)

        if request.FILES.get('profile_photo'):
            patient.profile_photo = request.FILES.get('profile_photo')

        patient.save()
        messages.success(request, "Health profile updated successfully.")
        return redirect('patient_dashboard')

    return render(request, 'patients/edit_profile.html', {'patient': patient})


# --- Medical Report Management Views ---
import os
from django.http import FileResponse, HttpResponseForbidden
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from .models import MedicalReport
from .forms import MedicalReportForm
from core.models import AuditLog

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


@login_required
@patient_required
def medical_reports_list_view(request):
    patient = get_object_or_404(PatientProfile, user=request.user)

    if request.method == 'POST':
        form = MedicalReportForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            report = form.save(commit=False)
            report.patient = patient
            report.uploaded_by = request.user
            report.created_ip = get_client_ip(request)

            file_obj = request.FILES.get('file')
            if file_obj:
                report.file_size = file_obj.size
                report.file_type = getattr(file_obj, 'content_type', '') or file_obj.name.split('.')[-1].lower()

            # Assign doctor if appointment selected or if patient has active doctor
            if report.appointment and hasattr(report.appointment, 'doctor'):
                report.doctor = report.appointment.doctor
            else:
                # Find most recent active doctor for patient
                recent_appt = Appointment.objects.filter(patient=request.user).order_by('-date').first()
                if recent_appt:
                    report.doctor = recent_appt.doctor

            report.save()

            AuditLog.objects.create(
                actor=request.user,
                action="UPLOAD_MEDICAL_REPORT",
                details=f"Uploaded report '{report.report_name}' ({report.report_category})",
                ip_address=get_client_ip(request)
            )

            # Notifications
            Notification.objects.create(
                user=request.user,
                message=f"Your medical report '{report.report_name}' was uploaded successfully.",
                notif_type="INFO"
            )

            if report.doctor and hasattr(report.doctor, 'user'):
                Notification.objects.create(
                    user=report.doctor.user,
                    message=f"Patient {patient.user.get_full_name() or patient.user.username} uploaded a new medical report: '{report.report_name}'.",
                    notif_type="INFO",
                    link="/doctors/reports/"
                )

            messages.success(request, f"Medical report '{report.report_name}' uploaded successfully!")
            return redirect('patient_medical_reports')
        else:
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)
    else:
        form = MedicalReportForm(user=request.user)

    search_query = request.GET.get('q', '').strip()
    category_filter = request.GET.get('category', '').strip()
    sort_order = request.GET.get('sort', 'newest')

    reports_qs = MedicalReport.objects.filter(patient=patient, is_deleted=False).select_related('doctor', 'doctor__user', 'appointment')

    if search_query:
        reports_qs = reports_qs.filter(
            Q(report_name__icontains=search_query) | Q(description__icontains=search_query)
        )

    if category_filter:
        reports_qs = reports_qs.filter(report_category=category_filter)

    if sort_order == 'oldest':
        reports_qs = reports_qs.order_by('uploaded_at')
    else:
        reports_qs = reports_qs.order_by('-uploaded_at')

    paginator = Paginator(reports_qs, 9) # 9 items per page for card layout
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    total_reports = MedicalReport.objects.filter(patient=patient, is_deleted=False).count()
    reviewed_count = MedicalReport.objects.filter(patient=patient, is_deleted=False, review_status='REVIEWED').count()
    pending_count = MedicalReport.objects.filter(patient=patient, is_deleted=False, review_status='PENDING').count()

    context = {
        'patient': patient,
        'form': form,
        'page_obj': page_obj,
        'reports': page_obj.object_list,
        'categories': MedicalReport.REPORT_CATEGORIES,
        'total_reports': total_reports,
        'reviewed_count': reviewed_count,
        'pending_count': pending_count,
        'search_query': search_query,
        'selected_category': category_filter,
        'selected_sort': sort_order,
    }
    return render(request, 'patients/medical_reports.html', context)


from django.views.decorators.clickjacking import xframe_options_sameorigin

@login_required
@xframe_options_sameorigin
def preview_medical_report_view(request, report_id):
    report = get_object_or_404(MedicalReport, id=report_id, is_deleted=False)

    # IDOR Authorization Check
    authorized = False
    if request.user.is_patient():
        if hasattr(request.user, 'patient_profile') and report.patient == request.user.patient_profile:
            authorized = True
    elif request.user.is_doctor():
        if hasattr(request.user, 'doctor_profile'):
            doc = request.user.doctor_profile
            if report.doctor == doc or Appointment.objects.filter(doctor=doc, patient=report.patient.user).exists():
                authorized = True
    elif request.user.is_admin():
        authorized = True

    if not authorized:
        AuditLog.objects.create(
            actor=request.user,
            action="UNAUTHORIZED_REPORT_ACCESS_ATTEMPT",
            details=f"Unauthorized preview attempt on report ID {report_id}",
            ip_address=get_client_ip(request)
        )
        return HttpResponseForbidden("Access Denied: You do not have authorization to view this medical report.")

    report.last_accessed = timezone.now()
    report.save(update_fields=['last_accessed'])

    AuditLog.objects.create(
        actor=request.user,
        action="PREVIEW_MEDICAL_REPORT",
        details=f"Previewed report '{report.report_name}' (ID {report.id})",
        ip_address=get_client_ip(request)
    )

    if not os.path.exists(report.file.path):
        messages.error(request, "Report file not found on disk.")
        return redirect('dashboard_redirect')

    content_type = report.file_type
    filename_lower = report.file.name.lower()
    if filename_lower.endswith('.pdf'):
        content_type = 'application/pdf'
    elif filename_lower.endswith('.png'):
        content_type = 'image/png'
    elif filename_lower.endswith(('.jpg', '.jpeg')):
        content_type = 'image/jpeg'

    response = FileResponse(open(report.file.path, 'rb'), content_type=content_type or 'application/pdf')
    response['Content-Disposition'] = f'inline; filename="{os.path.basename(report.file.name)}"'
    return response


@login_required
def download_medical_report_view(request, report_id):
    report = get_object_or_404(MedicalReport, id=report_id, is_deleted=False)

    # IDOR Authorization Check
    authorized = False
    if request.user.is_patient():
        if hasattr(request.user, 'patient_profile') and report.patient == request.user.patient_profile:
            authorized = True
    elif request.user.is_doctor():
        if hasattr(request.user, 'doctor_profile'):
            doc = request.user.doctor_profile
            if report.doctor == doc or Appointment.objects.filter(doctor=doc, patient=report.patient.user).exists():
                authorized = True
    elif request.user.is_admin():
        authorized = True

    if not authorized:
        AuditLog.objects.create(
            actor=request.user,
            action="UNAUTHORIZED_REPORT_DOWNLOAD_ATTEMPT",
            details=f"Unauthorized download attempt on report ID {report_id}",
            ip_address=get_client_ip(request)
        )
        return HttpResponseForbidden("Access Denied: You do not have authorization to download this medical report.")

    report.last_accessed = timezone.now()
    report.save(update_fields=['last_accessed'])

    AuditLog.objects.create(
        actor=request.user,
        action="DOWNLOAD_MEDICAL_REPORT",
        details=f"Downloaded report '{report.report_name}' (ID {report.id})",
        ip_address=get_client_ip(request)
    )

    if not os.path.exists(report.file.path):
        messages.error(request, "Report file not found on disk.")
        return redirect('dashboard_redirect')

    ext = os.path.splitext(report.file.name)[1]
    filename = f"{report.report_name}{ext}"
    response = FileResponse(open(report.file.path, 'rb'), as_attachment=True, filename=filename)
    return response


@login_required
@patient_required
def delete_patient_medical_report_view(request, report_id):
    patient = get_object_or_404(PatientProfile, user=request.user)
    report = get_object_or_404(MedicalReport, id=report_id, patient=patient, is_deleted=False)

    report.is_deleted = True
    report.save(update_fields=['is_deleted'])

    AuditLog.objects.create(
        actor=request.user,
        action="DELETE_MEDICAL_REPORT",
        details=f"Soft deleted report '{report.report_name}' (ID {report.id})",
        ip_address=get_client_ip(request)
    )

    messages.info(request, f"Medical report '{report.report_name}' has been deleted.")
    return redirect('patient_medical_reports')
