import os
from django.core.mail import EmailMessage
from django.conf import settings
from appointments.models import EmailLog
import logging

logger = logging.getLogger(__name__)

def send_payment_success_email(payment):
    """
    Sends payment confirmation and invoice email to the patient with PDF attachment.
    """
    try:
        subject = f"Payment Successful - Appointment Confirmed (Invoice: {payment.invoice_number})"
        patient = payment.patient
        patient_name = patient.get_full_name() or patient.username
        
        body = f"""Dear {patient_name},

Thank you for your payment. Your appointment has been successfully confirmed.

Appointment Details:
----------------------------------------
Doctor: Dr. {payment.doctor.user.get_full_name()} ({payment.doctor.specialization.name if payment.doctor.specialization else 'General'})
Department / Hospital: {payment.doctor.hospital_name or 'HAPP Central Hospital'}
Appointment Date: {payment.appointment.date.strftime('%B %d, %Y')}
Appointment Time: {payment.appointment.get_time_slot_display_text()}

Payment Summary:
----------------------------------------
Amount Paid: ₹{payment.total_amount:.2f}
Payment Method: {payment.get_payment_method_display()}
Transaction ID: {payment.transaction_id}
Payment ID: {payment.payment_id}
Invoice Number: {payment.invoice_number}

Please find your official PDF Invoice attached to this email.

Best regards,
Healthcare Analytics & Prediction Platform (HAPP) Team
"""
        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[patient.email],
        )
        
        # Attach PDF Invoice if present
        if payment.invoice_pdf and os.path.exists(payment.invoice_pdf.path):
            email.attach_file(payment.invoice_pdf.path)
            
        email.send(fail_silently=False)
        
        # Log email
        EmailLog.objects.create(
            appointment=payment.appointment,
            recipient_email=patient.email,
            recipient_type=EmailLog.RecipientType.PATIENT,
            email_type='PAYMENT_SUCCESS',
            subject=subject,
            status=EmailLog.DeliveryStatus.SENT
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send payment success email to {payment.patient.email}: {e}")
        EmailLog.objects.create(
            appointment=payment.appointment,
            recipient_email=payment.patient.email,
            recipient_type=EmailLog.RecipientType.PATIENT,
            email_type='PAYMENT_SUCCESS',
            subject=f"Payment Successful - Appointment Confirmed ({payment.invoice_number})",
            status=EmailLog.DeliveryStatus.FAILED,
            error_message=str(e)
        )
        return False


def send_doctor_payment_notification(payment):
    """
    Sends email notification to the assigned doctor. Sensitive payment info (card/UPI) is omitted.
    """
    try:
        doctor_user = payment.doctor.user
        subject = f"New Paid Appointment - {payment.patient.get_full_name() or payment.patient.username}"
        
        body = f"""Dear Dr. {doctor_user.get_full_name()},

You have a new paid appointment confirmed on HAPP platform.

Patient Name: {payment.patient.get_full_name() or payment.patient.username}
Appointment Date: {payment.appointment.date.strftime('%B %d, %Y')}
Appointment Time: {payment.appointment.get_time_slot_display_text()}
Appointment Number: APT-{payment.appointment.id:06d}
Payment Status: {payment.payment_status}
Consultation Fee: ₹{payment.amount:.2f}

You can view the full appointment details in your Doctor Dashboard.

Best regards,
Healthcare Analytics Platform System
"""
        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[doctor_user.email],
        )
        email.send(fail_silently=False)
        
        EmailLog.objects.create(
            appointment=payment.appointment,
            recipient_email=doctor_user.email,
            recipient_type=EmailLog.RecipientType.DOCTOR,
            email_type='NEW_PAID_APPOINTMENT',
            subject=subject,
            status=EmailLog.DeliveryStatus.SENT
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send doctor payment notification email: {e}")
        EmailLog.objects.create(
            appointment=payment.appointment,
            recipient_email=payment.doctor.user.email,
            recipient_type=EmailLog.RecipientType.DOCTOR,
            email_type='NEW_PAID_APPOINTMENT',
            subject=f"New Paid Appointment - {payment.patient.get_full_name()}",
            status=EmailLog.DeliveryStatus.FAILED,
            error_message=str(e)
        )
        return False


def send_refund_email(refund):
    """
    Sends refund confirmation email to the patient.
    """
    try:
        payment = refund.payment
        patient = payment.patient
        subject = f"Refund {refund.refund_status.title()} - Invoice #{payment.invoice_number}"
        
        body = f"""Dear {patient.get_full_name() or patient.username},

Your refund request regarding Appointment #{payment.appointment.id} has been {refund.refund_status.lower()}.

Refund Details:
----------------------------------------
Refund ID: {refund.refund_id}
Invoice Number: {payment.invoice_number}
Refund Amount: ₹{refund.refund_amount:.2f}
Reason: {refund.refund_reason}
Status: {refund.get_refund_status_display()}

If you have any questions, please contact our hospital billing department.

Best regards,
Healthcare Analytics & Prediction Platform Team
"""
        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[patient.email],
        )
        email.send(fail_silently=False)
        return True
    except Exception as e:
        logger.error(f"Failed to send refund email: {e}")
        return False
