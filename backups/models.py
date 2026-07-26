import datetime
from django.db import models
from django.conf import settings

class BackupType(models.TextChoices):
    FULL = 'FULL', 'Full Backup'
    INCREMENTAL = 'INCREMENTAL', 'Incremental Backup'
    DIFFERENTIAL = 'DIFFERENTIAL', 'Differential Backup'

class BackupStatus(models.TextChoices):
    SUCCESS = 'SUCCESS', 'Success'
    FAILED = 'FAILED', 'Failed'
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'

class BackupScheduleFrequency(models.TextChoices):
    DAILY = 'DAILY', 'Every Day'
    WEEKLY = 'WEEKLY', 'Every Week'
    MONTHLY = 'MONTHLY', 'Every Month'

class BackupRecord(models.Model):
    backup_name = models.CharField(max_length=255, unique=True, help_text="Timestamped backup archive filename")
    backup_type = models.CharField(max_length=20, choices=BackupType.choices, default=BackupType.FULL)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_backups')
    created_at = models.DateTimeField(auto_now_add=True)
    file_size = models.BigIntegerField(default=0, help_text="Backup size in bytes")
    storage_path = models.CharField(max_length=500, help_text="Absolute or relative storage path")
    encrypted = models.BooleanField(default=True, help_text="Whether backup archive is AES-256 encrypted")
    checksum = models.CharField(max_length=64, blank=True, null=True, help_text="SHA-256 archive checksum")
    status = models.CharField(max_length=20, choices=BackupStatus.choices, default=BackupStatus.SUCCESS)
    backup_duration = models.FloatField(default=0.0, help_text="Backup creation duration in seconds")
    notes = models.TextField(blank=True, null=True, help_text="Notes or log output")

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.backup_name} ({self.get_backup_type_display()} - {self.get_status_display()})"

    def get_formatted_file_size(self):
        bytes_val = self.file_size or 0
        if bytes_val < 1024:
            return f"{bytes_val} B"
        elif bytes_val < 1024 * 1024:
            return f"{round(bytes_val / 1024, 1)} KB"
        elif bytes_val < 1024 * 1024 * 1024:
            return f"{round(bytes_val / (1024 * 1024), 2)} MB"
        else:
            return f"{round(bytes_val / (1024 * 1024 * 1024), 2)} GB"


class RecoveryRecord(models.Model):
    backup = models.ForeignKey(BackupRecord, on_delete=models.CASCADE, related_name='recoveries')
    restored_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='executed_recoveries')
    restored_at = models.DateTimeField(auto_now_add=True)
    recovery_status = models.CharField(max_length=20, choices=BackupStatus.choices, default=BackupStatus.SUCCESS)
    recovery_duration = models.FloatField(default=0.0, help_text="Recovery duration in seconds")
    notes = models.TextField(blank=True, null=True, help_text="Restoration log output")

    class Meta:
        ordering = ['-restored_at']

    def __str__(self):
        return f"Restore of {self.backup.backup_name} by {self.restored_by} on {self.restored_at.strftime('%Y-%m-%d %H:%M')}"


class BackupScheduleConfig(models.Model):
    frequency = models.CharField(max_length=20, choices=BackupScheduleFrequency.choices, default=BackupScheduleFrequency.DAILY)
    backup_time = models.TimeField(default=datetime.time(2, 0))
    retention_days = models.IntegerField(default=30, help_text="Days to keep backups before automated cleanup")
    is_enabled = models.BooleanField(default=True, help_text="Whether automated daily backups are active")
    last_run = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Schedule: {self.get_frequency_display()} at {self.backup_time} (Retention: {self.retention_days} days)"
