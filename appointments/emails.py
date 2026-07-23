import logging
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings

from .models import EmailLog

logger = logging.getLogger(__name__)

def send_appointment_email(email_type, appointment, extra_context=None):
    """
    Centralized service to build, dispatch, and log appointment emails.
    Catches delivery exceptions and records every attempt in email_logs table.
    """
    if not appointment:
        logger.error("send_appointment_email called without valid appointment object.")
        return False

    extra_context = extra_context or {}
    patient = appointment.patient
    doctor = appointment.doctor
    doctor_user = doctor.user
    patient_profile = getattr(patient, 'patient_profile', None)

    # 1. Determine recipient, recipient type, subject, and template
    config_map = {
        EmailLog.EmailType.NEW_REQUEST: {
            'recipient_email': doctor_user.email,
            'recipient_type': EmailLog.RecipientType.DOCTOR,
            'subject': f"[Action Required] New Appointment Request #{appointment.id} from {patient.get_full_name()}",
            'template': 'emails/new_appointment_request_doctor.html',
        },
        EmailLog.EmailType.APPROVED: {
            'recipient_email': patient.email,
            'recipient_type': EmailLog.RecipientType.PATIENT,
            'subject': f"[Confirmed] Appointment #{appointment.id} with Dr. {doctor_user.get_full_name()}",
            'template': 'emails/appointment_approved_patient.html',
        },
        EmailLog.EmailType.REJECTED: {
            'recipient_email': patient.email,
            'recipient_type': EmailLog.RecipientType.PATIENT,
            'subject': f"[Update] Appointment Request #{appointment.id} Status",
            'template': 'emails/appointment_rejected_patient.html',
        },
        EmailLog.EmailType.RESCHEDULED: {
            'recipient_email': patient.email,
            'recipient_type': EmailLog.RecipientType.PATIENT,
            'subject': f"[Rescheduled] Appointment #{appointment.id} with Dr. {doctor_user.get_full_name()}",
            'template': 'emails/appointment_rescheduled_patient.html',
        },
        EmailLog.EmailType.REMINDER: {
            'recipient_email': patient.email,
            'recipient_type': EmailLog.RecipientType.PATIENT,
            'subject': f"[Reminder] Upcoming Appointment #{appointment.id} on {appointment.date.strftime('%b %d, %Y')}",
            'template': 'emails/appointment_reminder_patient.html',
        },
        EmailLog.EmailType.CANCELLED_BY_PATIENT: {
            'recipient_email': doctor_user.email,
            'recipient_type': EmailLog.RecipientType.DOCTOR,
            'subject': f"[Cancelled] Appointment #{appointment.id} by Patient {patient.get_full_name()}",
            'template': 'emails/appointment_cancelled_doctor.html',
        },
        EmailLog.EmailType.CANCELLED_BY_DOCTOR: {
            'recipient_email': patient.email,
            'recipient_type': EmailLog.RecipientType.PATIENT,
            'subject': f"[Cancelled] Appointment #{appointment.id} Notice",
            'template': 'emails/appointment_cancelled_patient.html',
        },
    }

    email_cfg = config_map.get(email_type)
    if not email_cfg:
        logger.error(f"Unknown email_type '{email_type}' passed to send_appointment_email.")
        return False

    recipient_email = email_cfg['recipient_email']
    recipient_type = email_cfg['recipient_type']
    subject = email_cfg['subject']
    template_name = email_cfg['template']

    if not recipient_email:
        logger.warning(f"Cannot send email_type '{email_type}': Recipient email is empty.")
        EmailLog.objects.create(
            appointment=appointment,
            recipient_email="N/A",
            recipient_type=recipient_type,
            email_type=email_type,
            subject=subject,
            status=EmailLog.DeliveryStatus.FAILED,
            error_message="Recipient email address was empty or missing."
        )
        return False

    # 2. Build context
    context = {
        'appointment_id': appointment.id,
        'patient_name': patient.get_full_name() or patient.username,
        'patient_id': patient_profile.id if patient_profile else patient.id,
        'patient_email': patient.email,
        'patient_phone': getattr(patient, 'phone', 'N/A'),
        'doctor_name': doctor_user.get_full_name() or doctor_user.username,
        'department': getattr(doctor.specialization, 'name', 'General Medicine'),
        'hospital_name': doctor.hospital_name or 'Medical Center',
        'hospital_address': f"{doctor.hospital_name or 'City Hospital'}, Healthcare Blvd, Wing B",
        'appointment_date': appointment.date.strftime('%B %d, %Y'),
        'appointment_time': appointment.get_time_slot_display_text(),
        'reason': appointment.reason,
        'rejection_reason': appointment.rejection_reason or '',
        'cancellation_reason': appointment.rejection_reason or '',
        'dashboard_url': 'http://127.0.0.1:8000/doctors/dashboard/',
        'booking_url': 'http://127.0.0.1:8000/appointments/book/',
    }
    context.update(extra_context)

    # 3. Render HTML and text
    try:
        html_content = render_to_string(template_name, context)
        text_content = strip_tags(html_content)

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient_email]
        )
        msg.attach_alternative(html_content, "text/html")
        
        msg.send(fail_silently=False)

        # 4. Log success
        EmailLog.objects.create(
            appointment=appointment,
            recipient_email=recipient_email,
            recipient_type=recipient_type,
            email_type=email_type,
            subject=subject,
            status=EmailLog.DeliveryStatus.SENT,
            error_message=None
        )
        logger.info(f"Successfully sent {email_type} email to {recipient_email} for Appointment #{appointment.id}")
        return True

    except Exception as exc:
        error_msg = str(exc)
        logger.exception(f"Failed to send {email_type} email to {recipient_email}: {error_msg}")
        EmailLog.objects.create(
            appointment=appointment,
            recipient_email=recipient_email,
            recipient_type=recipient_type,
            email_type=email_type,
            subject=subject,
            status=EmailLog.DeliveryStatus.FAILED,
            error_message=error_msg
        )
        return False
