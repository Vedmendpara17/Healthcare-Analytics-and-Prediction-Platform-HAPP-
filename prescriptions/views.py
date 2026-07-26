import csv
import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import HttpResponse, Http404
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count
from django.core.paginator import Paginator
from django.utils import timezone

from accounts.decorators import doctor_required, patient_required, admin_required, role_required
from doctors.models import DoctorProfile
from patients.models import PatientProfile
from appointments.models import Appointment
from prescriptions.models import Prescription, PrescriptionMedicine, PrescriptionStatus
from prescriptions.forms import PrescriptionForm, PrescriptionMedicineFormSet
from prescriptions.services import generate_prescription_pdf
from core.models import Notification, AuditLog

@doctor_required
def doctor_prescription_list_view(request):
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    prescriptions_qs = Prescription.objects.filter(doctor=doctor).select_related('patient', 'appointment', 'appointment__doctor')

    # Search & Filter
    query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()

    if query:
        prescriptions_qs = prescriptions_qs.filter(
            Q(prescription_number__icontains=query) |
            Q(patient__first_name__icontains=query) |
            Q(patient__last_name__icontains=query) |
            Q(patient__username__icontains=query) |
            Q(diagnosis__icontains=query)
        )

    if status_filter in [PrescriptionStatus.DRAFT, PrescriptionStatus.FINALIZED]:
        prescriptions_qs = prescriptions_qs.filter(prescription_status=status_filter)

    # Summary Metrics
    today = datetime.date.today()
    total_count = Prescription.objects.filter(doctor=doctor).count()
    todays_count = Prescription.objects.filter(doctor=doctor, created_at__date=today).count()
    draft_count = Prescription.objects.filter(doctor=doctor, prescription_status=PrescriptionStatus.DRAFT).count()
    finalized_count = Prescription.objects.filter(doctor=doctor, prescription_status=PrescriptionStatus.FINALIZED).count()

    paginator = Paginator(prescriptions_qs, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'prescriptions': page_obj,
        'query': query,
        'status_filter': status_filter,
        'total_count': total_count,
        'todays_count': todays_count,
        'draft_count': draft_count,
        'finalized_count': finalized_count,
    }
    return render(request, 'prescriptions/doctor_prescription_list.html', context)


@doctor_required
def create_prescription_view(request, appointment_id=None):
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    selected_appointment = None

    if appointment_id:
        selected_appointment = get_object_or_404(Appointment, id=appointment_id, doctor=doctor)

    # Get completed appointments for this doctor
    completed_appointments = Appointment.objects.filter(
        doctor=doctor
    ).select_related('patient').order_by('-date')

    if request.method == 'POST':
        form = PrescriptionForm(request.POST)
        formset = PrescriptionMedicineFormSet(request.POST)

        app_id = request.POST.get('appointment_id')
        if app_id:
            selected_appointment = get_object_or_404(Appointment, id=app_id, doctor=doctor)

        if not selected_appointment:
            messages.error(request, "Please select a valid appointment to issue an e-Prescription.")
            return redirect('create_prescription')

        patient_user = selected_appointment.patient

        if form.is_valid() and formset.is_valid():
            # Ensure at least one medicine is provided
            valid_medicines = 0
            for med_form in formset:
                if med_form.cleaned_data and not med_form.cleaned_data.get('DELETE', False):
                    if med_form.cleaned_data.get('medicine_name'):
                        valid_medicines += 1

            if valid_medicines == 0:
                messages.error(request, "A prescription must contain at least one prescribed medicine.")
            else:
                prescription = form.save(commit=False)
                prescription.doctor = doctor
                prescription.patient = patient_user
                prescription.appointment = selected_appointment
                prescription.created_by = request.user
                prescription.updated_by = request.user

                if doctor.profile_photo:
                    prescription.doctor_signature = doctor.profile_photo

                prescription.save()
                formset.instance = prescription
                formset.save()

                # Update appointment status to COMPLETED if not already
                if selected_appointment.status != Appointment.Status.COMPLETED:
                    selected_appointment.status = Appointment.Status.COMPLETED
                    selected_appointment.save(update_fields=['status'])

                # Notify Patient
                Notification.objects.create(
                    user=patient_user,
                    message=f"Dr. {doctor.user.get_full_name()} has issued a new e-Prescription (#{prescription.prescription_number}) for your visit.",
                    notif_type="APPOINTMENT"
                )

                # Audit Log
                AuditLog.objects.create(
                    actor=request.user,
                    action="PRESCRIPTION_CREATED",
                    details=f"Created e-Prescription #{prescription.prescription_number} for {patient_user.get_full_name()}"
                )

                messages.success(request, f"e-Prescription #{prescription.prescription_number} issued successfully!")
                return redirect('prescription_detail', prescription_id=prescription.id)
        else:
            messages.error(request, "Please correct the errors in the prescription form below.")

    else:
        initial_data = {}
        if selected_appointment:
            initial_data['appointment'] = selected_appointment.id
            initial_data['symptoms'] = selected_appointment.reason

        form = PrescriptionForm(initial=initial_data)
        formset = PrescriptionMedicineFormSet()

    context = {
        'form': form,
        'formset': formset,
        'selected_appointment': selected_appointment,
        'completed_appointments': completed_appointments,
        'doctor': doctor,
    }
    return render(request, 'prescriptions/create_prescription.html', context)


@doctor_required
def edit_prescription_view(request, prescription_id):
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    prescription = get_object_or_404(Prescription, id=prescription_id, doctor=doctor)

    if prescription.prescription_status == PrescriptionStatus.FINALIZED:
        messages.error(request, "Finalized prescriptions cannot be edited or modified to preserve clinical audit records.")
        return redirect('prescription_detail', prescription_id=prescription.id)

    if request.method == 'POST':
        form = PrescriptionForm(request.POST, instance=prescription)
        formset = PrescriptionMedicineFormSet(request.POST, instance=prescription)

        if form.is_valid() and formset.is_valid():
            prescription = form.save(commit=False)
            prescription.updated_by = request.user
            prescription.save()
            formset.save()

            AuditLog.objects.create(
                actor=request.user,
                action="PRESCRIPTION_UPDATED",
                details=f"Updated draft e-Prescription #{prescription.prescription_number}"
            )

            messages.success(request, f"e-Prescription #{prescription.prescription_number} updated.")
            return redirect('prescription_detail', prescription_id=prescription.id)
    else:
        form = PrescriptionForm(instance=prescription)
        formset = PrescriptionMedicineFormSet(instance=prescription)

    return render(request, 'prescriptions/edit_prescription.html', {
        'form': form,
        'formset': formset,
        'prescription': prescription
    })


@login_required
def prescription_detail_view(request, prescription_id):
    prescription = get_object_or_404(Prescription.objects.select_related('patient', 'doctor__user', 'doctor__specialization', 'appointment'), id=prescription_id)

    # Permission Gating (IDOR Prevention)
    is_patient_owner = (request.user == prescription.patient)
    is_doctor_author = (request.user == prescription.doctor.user)
    is_admin_user = request.user.is_admin()

    if not (is_patient_owner or is_doctor_author or is_admin_user):
        AuditLog.objects.create(
            actor=request.user,
            action="UNAUTHORIZED_ACCESS_ATTEMPT",
            details=f"Unauthorized view attempt for e-Prescription #{prescription.id}"
        )
        messages.error(request, "Permission denied. You do not have authorization to view this prescription.")
        return redirect('dashboard_redirect')

    AuditLog.objects.create(
        actor=request.user,
        action="PRESCRIPTION_VIEWED",
        details=f"Viewed e-Prescription #{prescription.prescription_number}"
    )

    medicines = prescription.medicines.all()
    patient_profile = getattr(prescription.patient, 'patient_profile', None)

    context = {
        'prescription': prescription,
        'medicines': medicines,
        'patient_profile': patient_profile,
        'can_edit': is_doctor_author and prescription.prescription_status == PrescriptionStatus.DRAFT,
    }
    return render(request, 'prescriptions/prescription_detail.html', context)


@login_required
def download_prescription_pdf_view(request, prescription_id):
    prescription = get_object_or_404(Prescription.objects.select_related('patient', 'doctor__user', 'doctor__specialization', 'appointment'), id=prescription_id)

    # Permission Gating
    if request.user != prescription.patient and request.user != prescription.doctor.user and not request.user.is_admin():
        AuditLog.objects.create(
            actor=request.user,
            action="UNAUTHORIZED_ACCESS_ATTEMPT",
            details=f"Unauthorized PDF download attempt for e-Prescription #{prescription.id}"
        )
        messages.error(request, "Permission denied.")
        return redirect('dashboard_redirect')

    pdf_bytes = generate_prescription_pdf(prescription)

    AuditLog.objects.create(
        actor=request.user,
        action="PRESCRIPTION_DOWNLOADED",
        details=f"Downloaded PDF for e-Prescription #{prescription.prescription_number}"
    )

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Rx_{prescription.prescription_number}.pdf"'
    return response


@login_required
def print_prescription_view(request, prescription_id):
    prescription = get_object_or_404(Prescription.objects.select_related('patient', 'doctor__user', 'doctor__specialization', 'appointment'), id=prescription_id)

    if request.user != prescription.patient and request.user != prescription.doctor.user and not request.user.is_admin():
        messages.error(request, "Permission denied.")
        return redirect('dashboard_redirect')

    AuditLog.objects.create(
        actor=request.user,
        action="PRESCRIPTION_PRINTED",
        details=f"Printed e-Prescription #{prescription.prescription_number}"
    )

    medicines = prescription.medicines.all()
    patient_profile = getattr(prescription.patient, 'patient_profile', None)

    context = {
        'prescription': prescription,
        'medicines': medicines,
        'patient_profile': patient_profile,
        'auto_print': True,
    }
    return render(request, 'prescriptions/print_prescription.html', context)


@patient_required
def patient_prescription_list_view(request):
    prescriptions_qs = Prescription.objects.filter(patient=request.user).select_related('doctor__user', 'doctor__specialization', 'appointment').order_by('-created_at')

    query = request.GET.get('q', '').strip()
    if query:
        prescriptions_qs = prescriptions_qs.filter(
            Q(prescription_number__icontains=query) |
            Q(doctor__user__first_name__icontains=query) |
            Q(doctor__user__last_name__icontains=query) |
            Q(diagnosis__icontains=query)
        )

    paginator = Paginator(prescriptions_qs, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'prescriptions/patient_prescription_list.html', {
        'prescriptions': page_obj,
        'query': query
    })


@admin_required
def admin_prescriptions_analytics_view(request):
    prescriptions_qs = Prescription.objects.select_related('patient', 'doctor__user', 'doctor__specialization', 'appointment').order_by('-created_at')

    # Filter params
    doc_id = request.GET.get('doctor_id')
    patient_id = request.GET.get('patient_id')
    diagnosis_q = request.GET.get('diagnosis')
    status_q = request.GET.get('status')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    if doc_id:
        prescriptions_qs = prescriptions_qs.filter(doctor_id=doc_id)
    if patient_id:
        prescriptions_qs = prescriptions_qs.filter(patient_id=patient_id)
    if diagnosis_q:
        prescriptions_qs = prescriptions_qs.filter(diagnosis__icontains=diagnosis_q)
    if status_q:
        prescriptions_qs = prescriptions_qs.filter(prescription_status=status_q)
    if date_from:
        prescriptions_qs = prescriptions_qs.filter(created_at__date__gte=date_from)
    if date_to:
        prescriptions_qs = prescriptions_qs.filter(created_at__date__lte=date_to)

    # Analytics Summaries
    today = datetime.date.today()
    this_month_start = today.replace(day=1)

    total_prescriptions = Prescription.objects.count()
    todays_prescriptions = Prescription.objects.filter(created_at__date=today).count()
    monthly_prescriptions = Prescription.objects.filter(created_at__date__gte=this_month_start).count()
    follow_ups_upcoming = Prescription.objects.filter(follow_up_date__gte=today).count()

    # Chart Data: Most prescribed medicines
    top_medicines = PrescriptionMedicine.objects.values('medicine_name').annotate(total=Count('id')).order_by('-total')[:5]
    top_med_names = [m['medicine_name'] for m in top_medicines]
    top_med_counts = [m['total'] for m in top_medicines]

    # Chart Data: Doctor-wise prescription counts
    doc_counts = Prescription.objects.values('doctor__user__first_name', 'doctor__user__last_name').annotate(total=Count('id')).order_by('-total')[:5]
    doc_names = [f"Dr. {d['doctor__user__first_name']} {d['doctor__user__last_name']}" for d in doc_counts]
    doc_totals = [d['total'] for d in doc_counts]

    paginator = Paginator(prescriptions_qs, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    doctors = DoctorProfile.objects.filter(is_approved=True).select_related('user')
    patients = PatientProfile.objects.select_related('user')

    context = {
        'prescriptions': page_obj,
        'total_prescriptions': total_prescriptions,
        'todays_prescriptions': todays_prescriptions,
        'monthly_prescriptions': monthly_prescriptions,
        'follow_ups_upcoming': follow_ups_upcoming,
        'top_med_names_json': top_med_names,
        'top_med_counts_json': top_med_counts,
        'doc_names_json': doc_names,
        'doc_totals_json': doc_totals,
        'doctors': doctors,
        'patients': patients,
    }
    return render(request, 'prescriptions/admin_prescriptions_analytics.html', context)


@admin_required
def export_prescriptions_csv_view(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="Prescriptions_Export_{datetime.date.today()}.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Prescription No', 'Date', 'Patient ID', 'Patient Name', 'Doctor Name',
        'Specialization', 'Diagnosis', 'Medicines Count', 'Follow-up Date', 'Status'
    ])

    prescriptions = Prescription.objects.select_related('patient', 'doctor__user', 'doctor__specialization').annotate(med_count=Count('medicines')).order_by('-created_at')

    for p in prescriptions:
        writer.writerow([
            p.prescription_number,
            p.created_at.strftime('%Y-%m-%d %H:%M'),
            p.patient.id,
            p.patient.get_full_name(),
            f"Dr. {p.doctor.user.get_full_name()}",
            p.doctor.specialization.name if p.doctor.specialization else 'N/A',
            p.diagnosis,
            p.med_count,
            p.follow_up_date.strftime('%Y-%m-%d') if p.follow_up_date else 'N/A',
            p.prescription_status
        ])

    AuditLog.objects.create(
        actor=request.user,
        action="EXPORT_PRESCRIPTIONS_CSV",
        details=f"Exported prescription records CSV report"
    )

    return response
