from django.contrib import admin
from backups.models import BackupRecord, RecoveryRecord, BackupScheduleConfig

@admin.register(BackupRecord)
class BackupRecordAdmin(admin.ModelAdmin):
    list_display = ('backup_name', 'backup_type', 'created_by', 'created_at', 'file_size', 'status', 'encrypted')
    list_filter = ('backup_type', 'status', 'encrypted', 'created_at')
    search_fields = ('backup_name', 'notes', 'created_by__username')

@admin.register(RecoveryRecord)
class RecoveryRecordAdmin(admin.ModelAdmin):
    list_display = ('backup', 'restored_by', 'restored_at', 'recovery_status', 'recovery_duration')
    list_filter = ('recovery_status', 'restored_at')
    search_fields = ('backup__backup_name', 'restored_by__username', 'notes')

@admin.register(BackupScheduleConfig)
class BackupScheduleConfigAdmin(admin.ModelAdmin):
    list_display = ('frequency', 'backup_time', 'retention_days', 'is_enabled', 'last_run')
