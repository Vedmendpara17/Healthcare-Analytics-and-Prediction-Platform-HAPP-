from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator

phone_validator = RegexValidator(
    regex=r'^[6-9]\d{9}$',
    message="Phone number must be a valid 10-digit number starting with 6, 7, 8, or 9."
)

class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Admin'
        DOCTOR = 'doctor', 'Doctor'
        PATIENT = 'patient', 'Patient'

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.PATIENT,
        help_text="User system access role"
    )
    phone = models.CharField(
        max_length=10,
        validators=[phone_validator],
        blank=True,
        null=True,
        help_text="10-digit mobile number"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def is_admin(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    def is_doctor(self):
        return self.role == self.Role.DOCTOR

    def is_patient(self):
        return self.role == self.Role.PATIENT

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"
