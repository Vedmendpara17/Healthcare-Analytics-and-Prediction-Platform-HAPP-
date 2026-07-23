import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import HttpResponse, Http404
from django.contrib.auth.decorators import login_required

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from accounts.decorators import doctor_required, role_required
from doctors.models import DoctorProfile
from patients.models import PatientProfile
from appointments.models import Appointment
from predictions.models import RiskAssessment
from predictions.services import RiskPredictor
from core.models import Notification, AuditLog

@doctor_required
def create_risk_assessment_view(request, patient_id=None):
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    selected_patient = None
    if patient_id:
        selected_patient = get_object_or_404(PatientProfile, id=patient_id)

    # Get patients who have booked appointments with doctor
    patient_ids = Appointment.objects.filter(doctor=doctor).values_list('patient_id', flat=True).distinct()
    patients = PatientProfile.objects.filter(user_id__in=patient_ids).select_related('user')

    if request.method == 'POST':
        p_id = request.POST.get('patient_id')
        if not p_id:
            messages.error(request, "Please select a patient to assess.")
            return redirect('create_risk_assessment')

        patient = get_object_or_404(PatientProfile, id=p_id)
        
        # Read form inputs
        systolic_bp = int(request.POST.get('systolic_bp', 120))
        diastolic_bp = int(request.POST.get('diastolic_bp', 80))
        fasting_sugar = float(request.POST.get('fasting_sugar', 90.0))
        postprandial_sugar = float(request.POST.get('postprandial_sugar', 120.0))
        total_cholesterol = float(request.POST.get('total_cholesterol', 180.0))
        hdl_cholesterol = float(request.POST.get('hdl_cholesterol', 50.0))
        ldl_cholesterol = float(request.POST.get('ldl_cholesterol', 100.0))
        height_cm = float(request.POST.get('height_cm', patient.height_cm))
        weight_kg = float(request.POST.get('weight_kg', patient.weight_kg))
        smoking_status = request.POST.get('smoking_status', 'never')
        alcohol_consumption = request.POST.get('alcohol_consumption', 'none')
        physical_activity = request.POST.get('physical_activity', 'moderate')
        
        family_history_list = request.POST.getlist('family_history')
        chronic_conditions_list = request.POST.getlist('chronic_conditions')
        symptoms_list = request.POST.getlist('symptoms')
        
        doctor_override_level = request.POST.get('doctor_override_level', '').strip()
        doctor_notes = request.POST.get('doctor_notes', '').strip()

        # Build payload for RiskPredictor engine
        input_data = {
            'age': patient.age,
            'gender': patient.gender,
            'systolic_bp': systolic_bp,
            'diastolic_bp': diastolic_bp,
            'fasting_sugar': fasting_sugar,
            'postprandial_sugar': postprandial_sugar,
            'total_cholesterol': total_cholesterol,
            'hdl_cholesterol': hdl_cholesterol,
            'ldl_cholesterol': ldl_cholesterol,
            'height_cm': height_cm,
            'weight_kg': weight_kg,
            'smoking_status': smoking_status,
            'alcohol_consumption': alcohol_consumption,
            'physical_activity': physical_activity,
            'family_history': family_history_list,
            'symptoms': symptoms_list,
        }

        # Run clinical prediction
        prediction_result = RiskPredictor.predict(input_data)

        # Create assessment record
        assessment = RiskAssessment.objects.create(
            patient=patient,
            doctor=doctor,
            age=patient.age,
            gender=patient.gender,
            systolic_bp=systolic_bp,
            diastolic_bp=diastolic_bp,
            fasting_sugar=fasting_sugar,
            postprandial_sugar=postprandial_sugar,
            total_cholesterol=total_cholesterol,
            hdl_cholesterol=hdl_cholesterol,
            ldl_cholesterol=ldl_cholesterol,
            height_cm=height_cm,
            weight_kg=weight_kg,
            bmi=prediction_result['bmi'],
            smoking_status=smoking_status,
            alcohol_consumption=alcohol_consumption,
            physical_activity=physical_activity,
            family_history_text=", ".join(family_history_list),
            chronic_conditions_text=", ".join(chronic_conditions_list),
            symptoms_text=", ".join(symptoms_list),
            computed_score=prediction_result['overall_score'],
            computed_level=prediction_result['overall_level'],
            heart_score=prediction_result['heart_risk_score'],
            diabetes_score=prediction_result['diabetes_risk_score'],
            hypertension_score=prediction_result['hypertension_risk_score'],
            precautions_json=json.dumps(prediction_result['precautions']),
            doctor_override_level=doctor_override_level if doctor_override_level in ['LOW', 'MEDIUM', 'HIGH'] else None,
            doctor_notes=doctor_notes
        )

        # Notify Patient
        Notification.objects.create(
            user=patient.user,
            message=f"Dr. {doctor.user.get_full_name()} has conducted a new Clinical Risk Assessment for you. Risk Level: {assessment.final_level}.",
            notif_type="RISK"
        )

        AuditLog.objects.create(
            actor=request.user,
            action="RISK_ASSESSMENT_CREATED",
            details=f"Created risk assessment for {patient.user.get_full_name()} (Score: {assessment.computed_score}, Level: {assessment.final_level})"
        )

        messages.success(request, f"Risk assessment successfully calculated! Final Risk Level: {assessment.final_level}.")
        return redirect('assessment_detail', assessment_id=assessment.id)

    context = {
        'doctor': doctor,
        'selected_patient': selected_patient,
        'patients': patients,
    }
    return render(request, 'predictions/assessment_form.html', context)


@login_required
def assessment_detail_view(request, assessment_id):
    assessment = get_object_or_404(RiskAssessment, id=assessment_id)
    
    # Gating permission check
    if request.user.is_patient() and assessment.patient.user != request.user:
        messages.error(request, "Permission denied.")
        return redirect('patient_dashboard')

    precautions = json.loads(assessment.precautions_json) if assessment.precautions_json else []

    context = {
        'assessment': assessment,
        'precautions': precautions,
    }
    return render(request, 'predictions/assessment_detail.html', context)


@login_required
def export_assessment_pdf_view(request, assessment_id):
    assessment = get_object_or_404(RiskAssessment, id=assessment_id)
    
    # Security check
    if request.user.is_patient() and assessment.patient.user != request.user:
        raise Http404("Assessment report not found.")

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Clinical_Health_Report_{assessment.id}.pdf"'

    doc = SimpleDocTemplate(response, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=20, textColor=colors.HexColor('#0F766E'), spaceAfter=10)
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#64748B'), spaceAfter=15)
    section_style = ParagraphStyle('SectionStyle', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor('#1E293B'), spaceBefore=10, spaceAfter=8)
    body_style = ParagraphStyle('BodyStyle', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#334155'), spaceAfter=4)
    alert_style = ParagraphStyle('AlertStyle', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#DC2626'), spaceBefore=10)

    story = []

    story.append(Paragraph("Healthcare Analytics & Prediction System", title_style))
    story.append(Paragraph(f"Official Clinical Decision-Support Health Assessment Report | Date: {assessment.created_at.strftime('%B %d, %Y')}", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#0F766E'), spaceAfter=15))

    # Patient & Doctor Info Table
    info_data = [
        [
            Paragraph(f"<b>Patient Name:</b> {assessment.patient.user.get_full_name()}", body_style),
            Paragraph(f"<b>Attending Doctor:</b> Dr. {assessment.doctor.user.get_full_name() if assessment.doctor else 'N/A'}", body_style)
        ],
        [
            Paragraph(f"<b>Age / Gender:</b> {assessment.age} yrs / {assessment.gender}", body_style),
            Paragraph(f"<b>Specialization:</b> {assessment.doctor.specialization.name if assessment.doctor and assessment.doctor.specialization else 'General Medicine'}", body_style)
        ],
        [
            Paragraph(f"<b>Height / Weight:</b> {assessment.height_cm} cm / {assessment.weight_kg} kg", body_style),
            Paragraph(f"<b>Calculated BMI:</b> {assessment.bmi}", body_style)
        ]
    ]
    info_table = Table(info_data, colWidths=[270, 270])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8FAFC')),
        ('PADDING', (0,0), (-1,-1), 6),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 15))

    # Risk Summary Box
    level_color = '#22C55E' if assessment.final_level == 'LOW' else ('#F59E0B' if assessment.final_level == 'MEDIUM' else '#EF4444')
    story.append(Paragraph("Clinical Risk Prediction Summary", section_style))
    
    summary_data = [
        [
            Paragraph(f"<b>Overall Risk Score:</b> {assessment.computed_score} / 100", body_style),
            Paragraph(f"<b>Final Risk Level:</b> <font color='{level_color}'><b>{assessment.final_level}</b></font>", body_style)
        ],
        [
            Paragraph(f"<b>Cardiovascular Risk:</b> {assessment.heart_score} / 100", body_style),
            Paragraph(f"<b>Diabetes Risk:</b> {assessment.diabetes_score} / 100", body_style)
        ],
        [
            Paragraph(f"<b>Hypertension Risk:</b> {assessment.hypertension_score} / 100", body_style),
            Paragraph(f"<b>Doctor Override:</b> {assessment.doctor_override_level or 'None'}", body_style)
        ]
    ]
    summary_table = Table(summary_data, colWidths=[270, 270])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F1F5F9')),
        ('PADDING', (0,0), (-1,-1), 8),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#CBD5E1')),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 15))

    # Biomarkers Table
    story.append(Paragraph("Vitals & Lab Biomarkers Evaluated", section_style))
    bio_data = [
        ["Biomarker", "Measured Value", "Reference Range"],
        ["Blood Pressure", f"{assessment.systolic_bp} / {assessment.diastolic_bp} mmHg", "Systolic < 120, Diastolic < 80"],
        ["Fasting Blood Sugar", f"{assessment.fasting_sugar} mg/dL", "70 - 99 mg/dL"],
        ["Postprandial Sugar", f"{assessment.postprandial_sugar} mg/dL", "< 140 mg/dL"],
        ["Total Cholesterol", f"{assessment.total_cholesterol} mg/dL", "< 200 mg/dL"],
        ["HDL / LDL", f"{assessment.hdl_cholesterol} / {assessment.ldl_cholesterol} mg/dL", "HDL > 40, LDL < 100"],
        ["Smoking / Alcohol", f"{assessment.smoking_status.title()} / {assessment.alcohol_consumption.title()}", "Non-smoker / None"],
    ]
    bio_table = Table(bio_data, colWidths=[180, 180, 180])
    bio_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0F766E')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('PADDING', (0,0), (-1,-1), 6),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
    ]))
    story.append(bio_table)
    story.append(Spacer(1, 15))

    # Clinical Precautions & Notes
    story.append(Paragraph("Automated Clinical Action Plan & Precautions", section_style))
    precautions = json.loads(assessment.precautions_json) if assessment.precautions_json else []
    for p in precautions:
        story.append(Paragraph(f"• {p}", body_style))

    if assessment.doctor_notes:
        story.append(Spacer(1, 10))
        story.append(Paragraph("Attending Doctor's Clinical Notes", section_style))
        story.append(Paragraph(assessment.doctor_notes, body_style))

    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#94A3B8'), spaceAfter=10))
    story.append(Paragraph("<b>Clinical Disclaimer:</b> This report is generated by an automated clinical decision-support algorithm. It represents an estimated risk profile and does not constitute a formal diagnostic claim. Final diagnosis and treatment decisions rest solely with the attending physician.", alert_style))

    doc.build(story)
    return response
