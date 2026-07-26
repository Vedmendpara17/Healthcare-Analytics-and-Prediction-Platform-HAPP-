from django.db import models
from django.conf import settings

class Specialization(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    icon = models.CharField(max_length=50, default='bi-heart-pulse', help_text="Bootstrap icon class e.g. bi-heart-pulse")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Appointment(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending Approval'
        APPROVED = 'APPROVED', 'Approved'
        RESCHEDULED = 'RESCHEDULED', 'Rescheduled'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'
        REJECTED = 'REJECTED', 'Rejected'

    TIME_SLOT_CHOICES = [
        ('09:00', '09:00 AM - 09:30 AM'),
        ('09:30', '09:30 AM - 10:00 AM'),
        ('10:00', '10:00 AM - 10:30 AM'),
        ('10:30', '10:30 AM - 11:00 AM'),
        ('11:00', '11:00 AM - 11:30 AM'),
        ('11:30', '11:30 AM - 12:00 PM'),
        ('14:00', '02:00 PM - 02:30 PM'),
        ('14:30', '02:30 PM - 03:00 PM'),
        ('15:00', '03:00 PM - 03:30 PM'),
        ('15:30', '03:30 PM - 04:00 PM'),
        ('16:00', '04:00 PM - 04:30 PM'),
        ('16:30', '04:30 PM - 05:00 PM'),
    ]

    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='patient_appointments')
    doctor = models.ForeignKey('doctors.DoctorProfile', on_delete=models.CASCADE, related_name='doctor_appointments')
    date = models.DateField()
    time_slot = models.CharField(max_length=10, choices=TIME_SLOT_CHOICES)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reason = models.TextField(help_text="Primary reason or symptom for appointment")
    rejection_reason = models.TextField(blank=True, null=True, help_text="Reason provided if rejected/cancelled/rescheduled")
    reminder_24h_sent = models.BooleanField(default=False)
    reminder_3h_sent = models.BooleanField(default=False)
    reminder_1h_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', 'time_slot']
        constraints = [
            models.UniqueConstraint(
                fields=['doctor', 'date', 'time_slot'],
                condition=~models.Q(status__in=['CANCELLED', 'REJECTED']),
                name='unique_active_doctor_slot'
            )
        ]

    @property
    def is_past(self):
        import datetime
        if not self.date:
            return False
        today = datetime.date.today()
        if self.date < today:
            return True
        elif self.date == today:
            try:
                hour, minute = map(int, self.time_slot.split(':'))
                slot_time = datetime.time(hour, minute)
                return datetime.datetime.now().time() > slot_time
            except Exception:
                return False
        return False

    @property
    def is_expired(self):
        return self.is_past and self.status not in [self.Status.COMPLETED, self.Status.CANCELLED, self.Status.REJECTED]

    @property
    def display_status(self):
        if self.status in ['CANCELLED', 'REJECTED', 'COMPLETED']:
            return self.get_status_display()
        if self.is_expired:
            return 'Expired'
        return self.get_status_display()

    def get_time_slot_display_text(self):
        dict_slots = dict(self.TIME_SLOT_CHOICES)
        return dict_slots.get(self.time_slot, self.time_slot)

    def __str__(self):
        return f"Appointment: {self.patient.get_full_name()} with Dr. {self.doctor.user.get_full_name()} on {self.date} ({self.time_slot})"


class Prescription(models.Model):
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name='prescription')
    medicines_text = models.TextField(help_text="Prescribed medicines list with dosage")
    dosage_instructions = models.TextField(blank=True, null=True, help_text="Special instructions, dietary advice")
    attached_file = models.FileField(upload_to='prescriptions/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Prescription for {self.appointment.patient.get_full_name()} ({self.appointment.date})"


class EmailLog(models.Model):
    class RecipientType(models.TextChoices):
        DOCTOR = 'DOCTOR', 'Doctor'
        PATIENT = 'PATIENT', 'Patient'

    class EmailType(models.TextChoices):
        NEW_REQUEST = 'NEW_REQUEST', 'New Appointment Request'
        APPROVED = 'APPROVED', 'Appointment Approved'
        REJECTED = 'REJECTED', 'Appointment Rejected'
        RESCHEDULED = 'RESCHEDULED', 'Appointment Rescheduled'
        RESCHEDULED_DOCTOR = 'RESCHEDULED_DOCTOR', 'Rescheduled Doctor Notice'
        REMINDER = 'REMINDER', 'Appointment Reminder'
        REMINDER_3H = 'REMINDER_3H', '3-Hour Appointment Reminder'
        CANCELLED_BY_PATIENT = 'CANCELLED_BY_PATIENT', 'Cancelled by Patient'
        CANCELLED_BY_DOCTOR = 'CANCELLED_BY_DOCTOR', 'Cancelled by Doctor'

    class DeliveryStatus(models.TextChoices):
        SENT = 'SENT', 'Sent'
        FAILED = 'FAILED', 'Failed'

    appointment = models.ForeignKey(Appointment, on_delete=models.SET_NULL, null=True, blank=True, related_name='email_logs')
    recipient_email = models.EmailField()
    recipient_type = models.CharField(max_length=10, choices=RecipientType.choices)
    email_type = models.CharField(max_length=30, choices=EmailType.choices)
    subject = models.CharField(max_length=255)
    status = models.CharField(max_length=10, choices=DeliveryStatus.choices)
    error_message = models.TextField(blank=True, null=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'email_logs'
        ordering = ['-sent_at']

    def __str__(self):
        return f"[{self.status}] {self.email_type} -> {self.recipient_email} ({self.sent_at.strftime('%Y-%m-%d %H:%M')})"


