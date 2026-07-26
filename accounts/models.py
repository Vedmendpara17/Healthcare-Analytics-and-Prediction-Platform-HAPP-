from datetime import timedelta
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.utils import timezone

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
    # Login protection & auditing fields
    failed_login_attempts = models.IntegerField(default=0)
    account_locked_until = models.DateTimeField(null=True, blank=True)
    last_failed_login = models.DateTimeField(null=True, blank=True)
    last_successful_login = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    last_login_user_agent = models.TextField(null=True, blank=True)

    # 2FA & Email Verification OTP fields
    email_verified = models.BooleanField(default=False)
    email_verification_otp = models.CharField(max_length=6, blank=True, null=True)
    email_verification_expiry = models.DateTimeField(blank=True, null=True)
    login_otp = models.CharField(max_length=6, blank=True, null=True)
    login_otp_expiry = models.DateTimeField(blank=True, null=True)
    password_reset_otp = models.CharField(max_length=6, blank=True, null=True)
    password_reset_otp_expiry = models.DateTimeField(blank=True, null=True)
    otp_attempts = models.IntegerField(default=0)
    resend_count = models.IntegerField(default=0)
    last_resend_time = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def is_admin(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    def is_doctor(self):
        return self.role == self.Role.DOCTOR

    def is_patient(self):
        return self.role == self.Role.PATIENT

    def is_account_locked(self):
        if self.account_locked_until:
            if timezone.now() < self.account_locked_until:
                return True
        return False

    def record_failed_login(self, ip=None, user_agent=None):
        now = timezone.now()
        # Do not modify attempt counter or reset timer if already locked and lock hasn't expired
        if self.account_locked_until and now < self.account_locked_until:
            return True

        if self.account_locked_until and now >= self.account_locked_until:
            self.failed_login_attempts = 0
            self.account_locked_until = None

        self.failed_login_attempts += 1
        self.last_failed_login = now
        if ip:
            self.last_login_ip = ip
        if user_agent:
            self.last_login_user_agent = user_agent

        if self.failed_login_attempts >= 4:
            self.account_locked_until = now + timedelta(minutes=15)

        self.save(update_fields=[
            'failed_login_attempts',
            'account_locked_until',
            'last_failed_login',
            'last_login_ip',
            'last_login_user_agent'
        ])
        return self.is_account_locked()

    def record_successful_login(self, ip=None, user_agent=None):
        now = timezone.now()
        self.failed_login_attempts = 0
        self.account_locked_until = None
        self.last_successful_login = now
        if ip:
            self.last_login_ip = ip
        if user_agent:
            self.last_login_user_agent = user_agent

        self.save(update_fields=[
            'failed_login_attempts',
            'account_locked_until',
            'last_successful_login',
            'last_login_ip',
            'last_login_user_agent'
        ])

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"
