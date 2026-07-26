from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Count, Q

from accounts.decorators import doctor_required
from doctors.models import DoctorProfile, DoctorAvailability
from appointments.models import Appointment, Prescription, EmailLog
from appointments.emails import send_appointment_email
from patients.models import PatientProfile
from predictions.models import RiskAssessment
from core.models import Notification, AuditLog

@doctor_required
def doctor_dashboard_view(request):
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    today = timezone.now().date()

    todays_appointments = Appointment.objects.filter(doctor=doctor, date=today).select_related('patient')
    pending_appointments = Appointment.objects.filter(doctor=doctor, status=Appointment.Status.PENDING).select_related('patient')
    
    # Patient risk distribution under this doctor
    patient_ids = Appointment.objects.filter(doctor=doctor).values_list('patient_id', flat=True).distinct()
    doctor_patients = PatientProfile.objects.filter(user_id__in=patient_ids)
    
    recent_assessments = RiskAssessment.objects.filter(doctor=doctor).select_related('patient__user')[:5]

    low_risk = RiskAssessment.objects.filter(doctor=doctor, computed_level='LOW').count()
    med_risk = RiskAssessment.objects.filter(doctor=doctor, computed_level='MEDIUM').count()
    high_risk = RiskAssessment.objects.filter(doctor=doctor, computed_level='HIGH').count()

    context = {
        'doctor': doctor,
        'todays_appointments': todays_appointments,
        'pending_appointments': pending_appointments,
        'doctor_patients_count': doctor_patients.count(),
        'recent_assessments': recent_assessments,
        'low_risk': low_risk,
        'med_risk': med_risk,
        'high_risk': high_risk,
    }
    return render(request, 'doctors/dashboard.html', context)


@doctor_required
def doctor_patient_list_view(request):
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    query = request.GET.get('q', '').strip()

    patient_ids = Appointment.objects.filter(doctor=doctor).values_list('patient_id', flat=True).distinct()
    patients = PatientProfile.objects.filter(user_id__in=patient_ids).select_related('user')

    if query:
        patients = patients.filter(
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(user__phone__icontains=query)
        )

    return render(request, 'doctors/patient_list.html', {'patients': patients, 'query': query})


@doctor_required
def doctor_patient_detail_view(request, patient_id):
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    patient = get_object_or_404(PatientProfile, id=patient_id)
    
    appointments = Appointment.objects.filter(doctor=doctor, patient=patient.user)
    assessments = RiskAssessment.objects.filter(patient=patient).order_by('-created_at')
    records = patient.medical_records.all()

    # Formulate trend data for Chart.js
    trend_labels = [a.created_at.strftime('%b %d') for a in reversed(assessments[:10])]
    trend_scores = [a.computed_score for a in reversed(assessments[:10])]

    return render(request, 'doctors/patient_detail.html', {
        'patient': patient,
        'appointments': appointments,
        'assessments': assessments,
        'records': records,
        'trend_labels': trend_labels,
        'trend_scores': trend_scores,
    })


@doctor_required
def update_appointment_status_view(request, appointment_id):
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    appointment = get_object_or_404(Appointment, id=appointment_id, doctor=doctor)

    if request.method == 'POST':
        new_status = request.POST.get('status')
        rejection_reason = request.POST.get('rejection_reason', '').strip()
        new_date_str = request.POST.get('new_date', '').strip()
        new_time_slot = request.POST.get('new_time_slot', '').strip()
        reschedule_note = request.POST.get('reschedule_note', '').strip()

        if new_status == 'RESCHEDULED':
            if new_date_str and new_time_slot:
                try:
                    parsed_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
                    appointment.date = parsed_date
                    appointment.time_slot = new_time_slot
                    appointment.status = Appointment.Status.RESCHEDULED
                    appointment.rejection_reason = reschedule_note
                    appointment.save()

                    Notification.objects.create(
                        user=appointment.patient,
                        message=f"Dr. {doctor.user.get_full_name()} rescheduled your appointment to {appointment.date} ({appointment.get_time_slot_display_text()}).",
                        notif_type="APPOINTMENT"
                    )

                    send_appointment_email(
                        EmailLog.EmailType.RESCHEDULED, 
                        appointment, 
                        extra_context={
                            'new_date': appointment.date.strftime('%B %d, %Y'), 
                            'new_time': appointment.get_time_slot_display_text(), 
                            'reschedule_note': reschedule_note
                        }
                    )
                    messages.success(request, f"Appointment rescheduled to {appointment.date} ({appointment.get_time_slot_display_text()}). Patient notified via email.")
                except ValueError:
                    messages.error(request, "Invalid date format for rescheduling.")
            else:
                messages.error(request, "Please provide a valid new date and time slot to reschedule.")

        elif new_status in [Appointment.Status.APPROVED, Appointment.Status.COMPLETED, Appointment.Status.CANCELLED, Appointment.Status.REJECTED]:
            appointment.status = new_status
            if rejection_reason:
                appointment.rejection_reason = rejection_reason
            appointment.save()

            # Send In-App Notification to Patient
            Notification.objects.create(
                user=appointment.patient,
                message=f"Your appointment with Dr. {doctor.user.get_full_name()} for {appointment.date} ({appointment.get_time_slot_display_text()}) status has been updated to '{new_status}'.",
                notif_type="APPOINTMENT"
            )

            # Trigger Automated Email Notifications
            if new_status == Appointment.Status.APPROVED:
                send_appointment_email(EmailLog.EmailType.APPROVED, appointment)
            elif new_status == Appointment.Status.REJECTED:
                send_appointment_email(EmailLog.EmailType.REJECTED, appointment)
            elif new_status == Appointment.Status.CANCELLED:
                send_appointment_email(EmailLog.EmailType.CANCELLED_BY_DOCTOR, appointment)

            messages.success(request, f"Appointment status updated to '{new_status}' and email notification sent.")

    return redirect('doctor_dashboard')


@doctor_required
def add_prescription_view(request, appointment_id):
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    appointment = get_object_or_404(Appointment, id=appointment_id, doctor=doctor)

    if request.method == 'POST':
        medicines = request.POST.get('medicines_text', '').strip()
        dosage = request.POST.get('dosage_instructions', '').strip()
        attached_file = request.FILES.get('attached_file')

        if medicines:
            Prescription.objects.update_or_create(
                appointment=appointment,
                defaults={
                    'medicines_text': medicines,
                    'dosage_instructions': dosage,
                    'attached_file': attached_file if attached_file else getattr(getattr(appointment, 'prescription', None), 'attached_file', None)
                }
            )
            appointment.status = Appointment.Status.COMPLETED
            appointment.save()

            Notification.objects.create(
                user=appointment.patient,
                message=f"Dr. {doctor.user.get_full_name()} has issued a prescription for your appointment on {appointment.date}.",
                notif_type="APPOINTMENT"
            )

            messages.success(request, "Prescription saved and appointment marked as completed.")
            return redirect('doctor_patient_detail', patient_id=appointment.patient.patient_profile.id)

    prescription = getattr(appointment, 'prescription', None)
    return render(request, 'doctors/add_prescription.html', {'appointment': appointment, 'prescription': prescription})


@doctor_required
def manage_schedule_view(request):
    doctor = get_object_or_404(DoctorProfile, user=request.user)

    if request.method == 'POST':
        weekday = int(request.POST.get('weekday', 0))
        start_time = request.POST.get('start_time')
        end_time = request.POST.get('end_time')

        if start_time and end_time:
            DoctorAvailability.objects.create(
                doctor=doctor,
                weekday=weekday,
                start_time=start_time,
                end_time=end_time
            )
            messages.success(request, "Availability slot added.")
            return redirect('manage_schedule')

    availabilities = DoctorAvailability.objects.filter(doctor=doctor).order_by('weekday', 'start_time')
    return render(request, 'doctors/schedule.html', {'doctor': doctor, 'availabilities': availabilities})


@doctor_required
def delete_availability_view(request, slot_id):
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    slot = get_object_or_404(DoctorAvailability, id=slot_id, doctor=doctor)
    slot.delete()
    messages.info(request, "Availability slot removed.")
    return redirect('manage_schedule')


@doctor_required
def edit_doctor_profile_view(request):
    doctor = get_object_or_404(DoctorProfile, user=request.user)

    if request.method == 'POST':
        qual = request.POST.get('qualification')
        if qual is not None:
            doctor.qualification = qual.strip()
        
        try:
            doctor.experience_years = int(request.POST.get('experience_years', doctor.experience_years))
        except (ValueError, TypeError):
            pass

        hosp = request.POST.get('hospital_name')
        if hosp is not None:
            doctor.hospital_name = hosp.strip()
        
        try:
            doctor.consultation_fee = float(request.POST.get('consultation_fee', doctor.consultation_fee))
        except (ValueError, TypeError):
            pass

        bio = request.POST.get('bio')
        if bio is not None:
            doctor.bio = bio.strip()
        
        if request.FILES.get('profile_photo'):
            photo = request.FILES.get('profile_photo')
            try:
                from doctors.models import validate_image_file
                validate_image_file(photo)
                doctor.profile_photo = photo
            except ValidationError as ve:
                messages.error(request, str(ve.message if hasattr(ve, 'message') else ve))
                return render(request, 'doctors/edit_profile.html', {'doctor': doctor})

        doctor.save()
        messages.success(request, "Doctor profile and photo updated successfully.")
        return redirect('edit_doctor_profile')

    return render(request, 'doctors/edit_profile.html', {'doctor': doctor})


# --- Doctor Medical Reports Workspace Views ---
from django.core.paginator import Paginator
from patients.models import MedicalReport

@doctor_required
def doctor_medical_reports_view(request):
    doctor = get_object_or_404(DoctorProfile, user=request.user)

    # Get patients assigned to this doctor through appointments
    assigned_patient_user_ids = Appointment.objects.filter(doctor=doctor).values_list('patient_id', flat=True).distinct()
    assigned_patients = PatientProfile.objects.filter(user_id__in=assigned_patient_user_ids).select_related('user')

    reports_qs = MedicalReport.objects.filter(
        Q(doctor=doctor) | Q(patient__user_id__in=assigned_patient_user_ids),
        is_deleted=False
    ).select_related('patient', 'patient__user', 'appointment').distinct()

    search_query = request.GET.get('q', '').strip()
    category_filter = request.GET.get('category', '').strip()
    status_filter = request.GET.get('status', '').strip()
    patient_filter = request.GET.get('patient_id', '').strip()

    if search_query:
        reports_qs = reports_qs.filter(
            Q(report_name__icontains=search_query) |
            Q(patient__user__first_name__icontains=search_query) |
            Q(patient__user__last_name__icontains=search_query)
        )

    if category_filter:
        reports_qs = reports_qs.filter(report_category=category_filter)

    if status_filter:
        reports_qs = reports_qs.filter(review_status=status_filter)

    if patient_filter:
        reports_qs = reports_qs.filter(patient_id=patient_filter)

    reports_qs = reports_qs.order_by('-uploaded_at')

    paginator = Paginator(reports_qs, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    total_count = reports_qs.count()
    pending_count = MedicalReport.objects.filter(
        Q(doctor=doctor) | Q(patient__user_id__in=assigned_patient_user_ids),
        is_deleted=False, review_status='PENDING'
    ).distinct().count()

    context = {
        'doctor': doctor,
        'page_obj': page_obj,
        'reports': page_obj.object_list,
        'assigned_patients': assigned_patients,
        'categories': MedicalReport.REPORT_CATEGORIES,
        'statuses': MedicalReport.STATUS_CHOICES,
        'total_count': total_count,
        'pending_count': pending_count,
        'search_query': search_query,
        'selected_category': category_filter,
        'selected_status': status_filter,
        'selected_patient': patient_filter,
    }
    return render(request, 'doctors/medical_reports.html', context)


@doctor_required
def doctor_review_report_view(request, report_id):
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    assigned_patient_user_ids = Appointment.objects.filter(doctor=doctor).values_list('patient_id', flat=True).distinct()

    report = get_object_or_404(
        MedicalReport,
        Q(doctor=doctor) | Q(patient__user_id__in=assigned_patient_user_ids),
        id=report_id,
        is_deleted=False
    )

    if request.method == 'POST':
        status = request.POST.get('review_status', 'REVIEWED')
        notes = request.POST.get('doctor_notes', '').strip()

        report.review_status = status
        report.doctor_notes = notes
        report.doctor = doctor
        report.save()

        AuditLog.objects.create(
            actor=request.user,
            action="REVIEW_MEDICAL_REPORT",
            details=f"Doctor Dr. {doctor.user.get_full_name()} updated status to '{status}' for report '{report.report_name}'",
            ip_address=request.META.get('REMOTE_ADDR')
        )

        # Notify Patient
        Notification.objects.create(
            user=report.patient.user,
            message=f"Dr. {doctor.user.get_full_name() or doctor.user.username} reviewed your medical report '{report.report_name}'. Notes: {notes[:60]}...",
            notif_type="INFO",
            link="/patients/reports/"
        )

        messages.success(request, f"Review notes updated for report '{report.report_name}'.")

    return redirect('doctor_medical_reports')
