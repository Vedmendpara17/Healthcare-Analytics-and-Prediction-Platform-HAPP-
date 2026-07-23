from django.db import models
from django.conf import settings

class Notification(models.Model):
    NOTIF_TYPES = [
        ('INFO', 'Information'),
        ('APPOINTMENT', 'Appointment Alert'),
        ('RISK', 'Risk Assessment'),
        ('ANNOUNCEMENT', 'System Announcement'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    message = models.TextField()
    notif_type = models.CharField(max_length=20, choices=NOTIF_TYPES, default='INFO')
    is_read = models.BooleanField(default=False)
    link = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification for {self.user.username}: {self.message[:30]}"

class Review(models.Model):
    doctor = models.ForeignKey('doctors.DoctorProfile', on_delete=models.CASCADE, related_name='reviews')
    patient = models.ForeignKey('patients.PatientProfile', on_delete=models.CASCADE, related_name='reviews_given')
    rating = models.PositiveSmallIntegerField(default=5, help_text="Rating between 1 and 5 stars")
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Review by {self.patient} for {self.doctor}: {self.rating}/5"

class AuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=150)
    details = models.TextField(blank=True, null=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M')}] {self.actor or 'System'}: {self.action}"
