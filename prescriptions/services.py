import io
from django.conf import settings
from django.utils import timezone

from reportlab.lib.pagesizes import letter
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.barcode.qr import QrCodeWidget

def generate_prescription_pdf(prescription):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'HospitalTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#0f766e')
    )
    subtitle_style = ParagraphStyle(
        'HospitalSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor('#64748b')
    )
    section_heading = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#0f766e'),
        spaceAfter=6
    )
    normal_text = ParagraphStyle(
        'NormalText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor('#1e293b')
    )
    bold_text = ParagraphStyle(
        'BoldText',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor('#0f172a')
    )
    table_header = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        textColor=colors.white
    )
    table_cell = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#334155')
    )

    elements = []

    # 1. Header with Hospital Info & QR Code
    qr_widget = QrCodeWidget(f"PRESCRIPTION:{prescription.prescription_number}|PATIENT:{prescription.patient.id}|DOCTOR:{prescription.doctor.id}")
    qr_bounds = qr_widget.getBounds()
    qr_width = qr_bounds[2] - qr_bounds[0]
    qr_height = qr_bounds[3] - qr_bounds[1]
    qr_drawing = Drawing(60, 60, transform=[60.0 / qr_width, 0, 0, 60.0 / qr_height, 0, 0])
    qr_drawing.add(qr_widget)

    hospital_info = [
        Paragraph("HEALTHCARE ANALYTICS & PREDICTION PLATFORM", title_style),
        Paragraph("Central Multispecialty Hospital & Medical Research Center", subtitle_style),
        Paragraph("123 Healthcare Boulevard, Medical District • Contact: +1 (800) 555-HAPP • Emergency: 24/7", subtitle_style)
    ]

    header_table_data = [[hospital_info, qr_drawing]]
    header_table = Table(header_table_data, colWidths=[470, 70])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 10))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#0f766e'), spaceAfter=12))

    # 2. Metadata Box (Rx Number & Date)
    rx_meta_data = [
        [
            Paragraph(f"<b>Prescription No:</b> {prescription.prescription_number}", normal_text),
            Paragraph(f"<b>Date:</b> {prescription.created_at.strftime('%B %d, %Y')}", normal_text),
            Paragraph(f"<b>Status:</b> {prescription.get_prescription_status_display()}", normal_text)
        ]
    ]
    rx_meta_table = Table(rx_meta_data, colWidths=[200, 170, 170])
    rx_meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f0fdf4')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#bbf7d0')),
        ('PADDING', (0,0), (-1,-1), 6),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    elements.append(rx_meta_table)
    elements.append(Spacer(1, 12))

    # 3. Doctor & Patient Info Grid
    doc_info = [
        Paragraph(f"<b>Doctor Name:</b> Dr. {prescription.doctor.user.get_full_name() or prescription.doctor.user.username}", normal_text),
        Paragraph(f"<b>Specialization:</b> {prescription.doctor.specialization.name if prescription.doctor.specialization else 'General Practice'}", normal_text),
        Paragraph(f"<b>License No:</b> {prescription.doctor.license_number}", normal_text),
        Paragraph(f"<b>Hospital/Clinic:</b> {prescription.doctor.hospital_name}", normal_text),
    ]

    patient_profile = getattr(prescription.patient, 'patient_profile', None)
    patient_info = [
        Paragraph(f"<b>Patient Name:</b> {prescription.patient.get_full_name() or prescription.patient.username}", normal_text),
        Paragraph(f"<b>Patient ID:</b> #{prescription.patient.id}", normal_text),
        Paragraph(f"<b>Age / Gender:</b> {patient_profile.age if patient_profile else 'N/A'} Yrs / {patient_profile.gender if patient_profile else 'N/A'}", normal_text),
        Paragraph(f"<b>Contact:</b> {prescription.patient.phone or 'N/A'}", normal_text),
    ]

    info_table_data = [
        [Paragraph("<b>ATTENDING PHYSICIAN DETAILS</b>", bold_text), Paragraph("<b>PATIENT DEMOGRAPHICS</b>", bold_text)],
        [doc_info, patient_info]
    ]
    info_table = Table(info_table_data, colWidths=[270, 270])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,0), colors.HexColor('#f1f5f9')),
        ('BACKGROUND', (1,0), (1,0), colors.HexColor('#f1f5f9')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
        ('PADDING', (0,0), (-1,-1), 6),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 14))

    # 4. Clinical Impression / Diagnosis & Symptoms
    elements.append(Paragraph("Clinical Impressions & Diagnosis", section_heading))
    diag_data = [
        [Paragraph("<b>Diagnosis:</b>", bold_text), Paragraph(prescription.diagnosis, normal_text)],
    ]
    if prescription.symptoms:
        diag_data.append([Paragraph("<b>Symptoms:</b>", bold_text), Paragraph(prescription.symptoms, normal_text)])
    if prescription.clinical_notes:
        diag_data.append([Paragraph("<b>Clinical Notes:</b>", bold_text), Paragraph(prescription.clinical_notes, normal_text)])

    diag_table = Table(diag_data, colWidths=[100, 440])
    diag_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#e2e8f0')),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(diag_table)
    elements.append(Spacer(1, 14))

    # 5. Prescribed Medicines Table
    elements.append(Paragraph("Rx - Prescribed Medications", section_heading))

    med_table_data = [[
        Paragraph("Medicine & Type", table_header),
        Paragraph("Strength", table_header),
        Paragraph("Dosage", table_header),
        Paragraph("Timing (M-A-N)", table_header),
        Paragraph("Duration", table_header),
        Paragraph("Meal Instruction", table_header),
        Paragraph("Qty", table_header)
    ]]

    medicines = prescription.medicines.all()
    if medicines.exists():
        for m in medicines:
            m_timing = f"{'1' if m.morning else '0'}-{'1' if m.afternoon else '0'}-{'1' if m.night else '0'}"
            med_table_data.append([
                Paragraph(f"<b>{m.medicine_name}</b><br/><font color='#64748b'>{m.medicine_type}</font>", table_cell),
                Paragraph(m.strength, table_cell),
                Paragraph(m.dosage, table_cell),
                Paragraph(f"<b>{m_timing}</b><br/><font color='#64748b'>{m.frequency}</font>", table_cell),
                Paragraph(m.duration, table_cell),
                Paragraph(m.meal_instruction, table_cell),
                Paragraph(str(m.quantity), table_cell)
            ])
    else:
        med_table_data.append([
            Paragraph("No medications added.", table_cell), "", "", "", "", "", ""
        ])

    med_table = Table(med_table_data, colWidths=[120, 60, 65, 95, 60, 90, 50])
    med_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0f766e')),
        ('ALIGN', (0,0), (-1,0), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')]),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(med_table)
    elements.append(Spacer(1, 14))

    # 6. Follow-Up & Physician Signature Footer
    footer_left = []
    if prescription.follow_up_date:
        footer_left.append(Paragraph(f"<b>Follow-Up Consultation Date:</b> <font color='#0f766e'><b>{prescription.follow_up_date.strftime('%B %d, %Y')}</b></font>", normal_text))
    footer_left.append(Paragraph("<i>Please bring this e-Prescription during your follow-up visit.</i>", subtitle_style))

    footer_right = [
        Paragraph("<b>Digitally Authorized By:</b>", normal_text),
        Spacer(1, 15),
        Paragraph(f"Dr. {prescription.doctor.user.get_full_name() or prescription.doctor.user.username}", bold_text),
        Paragraph(f"Reg No: {prescription.doctor.license_number}", subtitle_style),
        Paragraph("Electronically Signed & Validated", subtitle_style)
    ]

    footer_table_data = [[footer_left, footer_right]]
    footer_table = Table(footer_table_data, colWidths=[320, 220])
    footer_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
    ]))
    elements.append(KeepTogether([footer_table]))

    elements.append(Spacer(1, 15))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cbd5e1'), spaceAfter=8))
    elements.append(Paragraph("This is an official computer-generated Electronic Medical Prescription issued via HAPP Platform. Verified for authenticity.", ParagraphStyle('FooterNotice', parent=styles['Normal'], fontName='Helvetica-Oblique', fontSize=8, alignment=1, textColor=colors.HexColor('#94a3b8'))))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()
