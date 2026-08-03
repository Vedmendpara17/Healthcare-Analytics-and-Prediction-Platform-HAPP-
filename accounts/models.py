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
    failed_attempts = models.IntegerField(default=0)
    account_locked = models.BooleanField(default=False)
    lock_until = models.DateTimeField(null=True, blank=True)
    failed_login_attempts = models.IntegerField(default=0)
    account_locked_until = models.DateTimeField(null=True, blank=True)
    last_failed_login = models.DateTimeField(null=True, blank=True)
    last_successful_login = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    last_login_user_agent = models.TextField(null=True, blank=True)



    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def is_admin(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    def is_doctor(self):
        return self.role == self.Role.DOCTOR

    def is_patient(self):
        return self.role == self.Role.PATIENT

    def is_account_locked(self):
        target_time = self.account_locked_until or self.lock_until
        if self.account_locked or target_time:
            if target_time and timezone.now() < target_time:
                return True
            elif target_time and timezone.now() >= target_time:
                self.unlock_account()
                return False
        return False

    def get_remaining_lock_seconds(self):
        target_time = self.account_locked_until or self.lock_until
        if target_time and timezone.now() < target_time:
            delta = target_time - timezone.now()
            return int(delta.total_seconds())
        return 0

    def get_remaining_lock_display(self):
        secs = self.get_remaining_lock_seconds()
        if secs <= 0:
            return ""
        mins = secs // 60
        rem_secs = secs % 60
        return f"{mins} minutes {rem_secs} seconds"

    def unlock_account(self):
        self.failed_attempts = 0
        self.failed_login_attempts = 0
        self.account_locked = False
        self.lock_until = None
        self.account_locked_until = None
        self.save(update_fields=['failed_attempts', 'failed_login_attempts', 'account_locked', 'lock_until', 'account_locked_until'])

    def record_failed_login(self, ip=None, user_agent=None):
        now = timezone.now()
        target_time = self.account_locked_until or self.lock_until

        if target_time and now < target_time:
            return True, 0

        if target_time and now >= target_time:
            self.failed_attempts = 0
            self.failed_login_attempts = 0
            self.account_locked = False
            self.lock_until = None
            self.account_locked_until = None

        self.failed_login_attempts += 1
        self.failed_attempts = self.failed_login_attempts
        self.last_failed_login = now
        if ip:
            self.last_login_ip = ip
        if user_agent:
            self.last_login_user_agent = user_agent

        # On the 5th failed attempt -> lock for 15 minutes
        if self.failed_login_attempts >= 5:
            self.account_locked = True
            self.account_locked_until = now + timedelta(minutes=15)
            self.lock_until = self.account_locked_until

        self.save(update_fields=[
            'failed_attempts',
            'failed_login_attempts',
            'account_locked',
            'lock_until',
            'account_locked_until',
            'last_failed_login',
            'last_login_ip',
            'last_login_user_agent'
        ])

        is_locked_now = self.is_account_locked()
        remaining_attempts = max(0, 4 - self.failed_login_attempts + 1) if not is_locked_now else 0
        return is_locked_now, remaining_attempts

    def record_successful_login(self, ip=None, user_agent=None):
        now = timezone.now()
        self.failed_attempts = 0
        self.failed_login_attempts = 0
        self.account_locked = False
        self.lock_until = None
        self.account_locked_until = None
        self.last_successful_login = now
        self.last_login = now
        if ip:
            self.last_login_ip = ip
        if user_agent:
            self.last_login_user_agent = user_agent

        self.save(update_fields=[
            'failed_attempts',
            'failed_login_attempts',
            'account_locked',
            'lock_until',
            'account_locked_until',
            'last_successful_login',
            'last_login',
            'last_login_ip',
            'last_login_user_agent'
        ])

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"
