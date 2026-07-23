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
    recent_records = patient.medical_records.all()[:3]
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
        'recent_records': recent_records,
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
    patient = get_object_or_404(PatientProfile, user=request.user)
    prescriptions = Prescription.objects.filter(appointment__patient=request.user).select_related('appointment__doctor__user', 'appointment__doctor__specialization').order_by('-created_at')
    return render(request, 'patients/prescriptions.html', {'prescriptions': prescriptions})


@patient_required
def medical_records_vault_view(request):
    patient = get_object_or_404(PatientProfile, user=request.user)

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        record_type = request.POST.get('record_type', 'LAB')
        description = request.POST.get('description', '').strip()
        uploaded_file = request.FILES.get('file')

        if title and uploaded_file:
            try:
                record = MedicalRecord.objects.create(
                    patient=patient,
                    title=title,
                    record_type=record_type,
                    description=description,
                    file=uploaded_file
                )
                messages.success(request, f"Document '{record.title}' uploaded successfully to your vault.")
            except Exception as e:
                messages.error(request, f"Upload error: {str(e)}")
            return redirect('medical_records_vault')
        else:
            messages.error(request, "Please provide a document title and select a valid file.")

    records = patient.medical_records.all()
    return render(request, 'patients/medical_records.html', {'patient': patient, 'records': records})


@patient_required
def delete_medical_record_view(request, record_id):
    patient = get_object_or_404(PatientProfile, user=request.user)
    record = get_object_or_404(MedicalRecord, id=record_id, patient=patient)
    record.file.delete(save=False)
    record.delete()
    messages.info(request, "Document removed from your vault.")
    return redirect('medical_records_vault')


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
        patient.allergies = request.POST.get('allergies', patient.allergies)
        patient.chronic_conditions = request.POST.get('chronic_conditions', patient.chronic_conditions)

        if request.FILES.get('profile_photo'):
            patient.profile_photo = request.FILES.get('profile_photo')

        patient.save()
        messages.success(request, "Health profile updated successfully.")
        return redirect('patient_dashboard')

    return render(request, 'patients/edit_profile.html', {'patient': patient})
