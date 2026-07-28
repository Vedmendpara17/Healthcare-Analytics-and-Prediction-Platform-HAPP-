import os
from django.conf import settings
from django.core.files.base import ContentFile
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.graphics.barcode import qr

def generate_invoice_pdf(payment):
    """
    Generates a professional PDF invoice for a given Payment instance using ReportLab
    and saves it to the media/invoices directory and assigns it to payment.invoice_pdf.
    """
    invoices_dir = os.path.join(settings.MEDIA_ROOT, 'invoices')
    os.makedirs(invoices_dir, exist_ok=True)
    
    filename = f"{payment.invoice_number}.pdf"
    file_path = os.path.join(invoices_dir, filename)
    
    doc = SimpleDocTemplate(
        file_path,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )
    
    styles = getSampleStyleSheet()
    
    # Custom Styles
    brand_color = colors.HexColor("#0f766e")
    dark_neutral = colors.HexColor("#0f172a")
    text_muted = colors.HexColor("#64748b")
    bg_light = colors.HexColor("#f8fafc")
    
    title_style = ParagraphStyle(
        'InvoiceTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=28,
        textColor=brand_color,
        spaceAfter=4
    )
    
    subtitle_style = ParagraphStyle(
        'InvoiceSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=text_muted
    )
    
    section_title = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=brand_color,
        spaceBefore=12,
        spaceAfter=6
    )
    
    normal_style = ParagraphStyle(
        'InvoiceNormal',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=dark_neutral
    )

    bold_style = ParagraphStyle(
        'InvoiceBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=13,
        textColor=dark_neutral
    )

    story = []
    
    # Header Table (Hospital Info & Invoice Title)
    header_data = [
        [
            Paragraph("<b>HEALTHCARE ANALYTICS PLATFORM</b><br/><font color='#64748b' size=8>Medical Center & Digital Health Solutions<br/>123 Health Ave, Suite 400, Medical District<br/>Phone: +91 (800) 555-HAPP | Email: billing@happ.med</font>", normal_style),
            Paragraph(f"<font color='#0f766e' size=18><b>INVOICE</b></font><br/><b>Invoice #:</b> {payment.invoice_number}<br/><b>Date:</b> {payment.payment_date.strftime('%b %d, %Y %I:%M %p') if payment.payment_date else payment.created_at.strftime('%b %d, %Y')}<br/><b>Status:</b> <font color='#16a34a'><b>{payment.payment_status}</b></font>", normal_style)
        ]
    ]
    
    header_table = Table(header_data, colWidths=[320, 220])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0"), spaceAfter=8))
    
    # Patient & Doctor Info Table
    info_data = [
        [
            Paragraph("<b>PATIENT DETAILS</b>", section_title),
            Paragraph("<b>APPOINTMENT & DOCTOR DETAILS</b>", section_title)
        ],
        [
            Paragraph(f"<b>Name:</b> {payment.patient.get_full_name() or payment.patient.username}<br/>"
                      f"<b>Patient ID:</b> PAT-{payment.patient.id:05d}<br/>"
                      f"<b>Email:</b> {payment.patient.email}<br/>"
                      f"<b>Payment Method:</b> {payment.get_payment_method_display()}<br/>"
                      f"<b>Reference:</b> {payment.masked_payment_reference or 'N/A'}", normal_style),
            Paragraph(f"<b>Doctor:</b> Dr. {payment.doctor.user.get_full_name()}<br/>"
                      f"<b>Specialization:</b> {payment.doctor.specialization.name if payment.doctor.specialization else 'General'}<br/>"
                      f"<b>Department:</b> {payment.doctor.hospital_name or 'HAPP Central Hospital'}<br/>"
                      f"<b>Appt Number:</b> APT-{payment.appointment.id:06d}<br/>"
                      f"<b>Appt Date & Time:</b> {payment.appointment.date.strftime('%b %d, %Y')} ({payment.appointment.get_time_slot_display_text()})", normal_style)
        ]
    ]
    
    info_table = Table(info_data, colWidths=[270, 270])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BACKGROUND', (0,0), (-1,-1), bg_light),
        ('PADDING', (0,0), (-1,-1), 8),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 10))
    
    # Payment Summary Breakdown Table
    items_data = [
        [Paragraph("<b>Description</b>", bold_style), Paragraph("<b>Qty</b>", bold_style), Paragraph("<b>Unit Fee</b>", bold_style), Paragraph("<b>Amount (₹)</b>", bold_style)],
        [Paragraph(f"Medical Consultation Fee (Dr. {payment.doctor.user.get_full_name()})", normal_style), "1", f"₹{payment.amount:.2f}", f"₹{payment.amount:.2f}"],
        [Paragraph("Platform & Processing Fee", normal_style), "1", f"₹{payment.platform_fee:.2f}", f"₹{payment.platform_fee:.2f}"],
        [Paragraph("Government / Hospital Tax", normal_style), "1", f"₹{payment.tax:.2f}", f"₹{payment.tax:.2f}"],
        [Paragraph("Discount Applied", normal_style), "1", f"-₹{payment.discount:.2f}", f"-₹{payment.discount:.2f}"],
    ]
    
    summary_table = Table(items_data, colWidths=[280, 50, 100, 110])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#f1f5f9")),
        ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 8))
    
    # Total Amount Table
    total_data = [
        ["", Paragraph("<b>Total Amount Paid:</b>", ParagraphStyle('RightTotal', parent=bold_style, alignment=2)), Paragraph(f"<b>₹{payment.total_amount:.2f}</b>", ParagraphStyle('RightTotalVal', parent=title_style, fontSize=13, textColor=brand_color, alignment=2))]
    ]
    total_table = Table(total_data, colWidths=[280, 150, 110])
    total_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(total_table)
    story.append(Spacer(1, 10))
    
    # QR Code & IDs Section
    qr_code = qr.QrCodeWidget(f"HAPP-INVOICE:{payment.invoice_number}|TXN:{payment.transaction_id}|AMT:INR{payment.total_amount}")
    bounds = qr_code.getBounds()
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    d = Drawing(50, 50, transform=[50.0/width, 0, 0, 50.0/height, 0, 0])
    d.add(qr_code)
    
    ids_data = [
        [
            d,
            Paragraph(f"<b>Payment ID:</b> {payment.payment_id}<br/>"
                      f"<b>Transaction ID:</b> {payment.transaction_id}<br/>"
                      f"<i>Scan QR code for digital validation of hospital payment record.</i>", normal_style)
        ]
    ]
    ids_table = Table(ids_data, colWidths=[60, 480])
    ids_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 2),
    ]))
    story.append(ids_table)
    story.append(Spacer(1, 10))
    
    # Footer & Thank you message
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0"), spaceAfter=6))
    footer_text = Paragraph("<font color='#0f766e'><b>Thank you for choosing Healthcare Analytics & Prediction Platform!</b></font><br/>"
                            "<font color='#64748b' size=8>This is an electronically generated simulated invoice for educational & demonstration purposes. No real financial currency was exchanged.</font>",
                            ParagraphStyle('Footer', parent=normal_style, alignment=1))
    story.append(footer_text)
    
    doc.build(story)
    
    # Save reference to payment
    relative_path = f"invoices/{filename}"
    payment.invoice_pdf = relative_path
    payment.save(update_fields=['invoice_pdf'])
    
    return file_path
