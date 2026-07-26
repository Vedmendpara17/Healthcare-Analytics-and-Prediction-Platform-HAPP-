import os
from pathlib import Path
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import HttpResponse, FileResponse, Http404
from django.core.paginator import Paginator
from django.db.models import Sum, Q, Count
from django.utils import timezone

from accounts.decorators import role_required, admin_required
from backups.models import BackupRecord, RecoveryRecord, BackupScheduleConfig, BackupType, BackupStatus
from backups.forms import BackupScheduleConfigForm, RestoreConfirmationForm
from backups.services import create_backup_archive, verify_backup_integrity, restore_backup_archive, purge_expired_backups
from core.models import AuditLog

@admin_required
def admin_backup_dashboard_view(request):
    backups_qs = BackupRecord.objects.select_related('created_by').order_by('-created_at')

    total_backups = backups_qs.count()
    latest_backup = backups_qs.first()
    successful_backups = backups_qs.filter(status=BackupStatus.SUCCESS).count()
    failed_backups = backups_qs.filter(status=BackupStatus.FAILED).count()
    success_rate = round((successful_backups / total_backups * 100), 1) if total_backups > 0 else 100.0

    total_storage_bytes = backups_qs.aggregate(total=Sum('file_size'))['total'] or 0
    if total_storage_bytes < 1024 * 1024:
        storage_usage_str = f"{round(total_storage_bytes / 1024, 1)} KB"
    elif total_storage_bytes < 1024 * 1024 * 1024:
        storage_usage_str = f"{round(total_storage_bytes / (1024 * 1024), 2)} MB"
    else:
        storage_usage_str = f"{round(total_storage_bytes / (1024 * 1024 * 1024), 2)} GB"

    last_recovery = RecoveryRecord.objects.select_related('backup', 'restored_by').order_by('-restored_at').first()
    schedule_config, _ = BackupScheduleConfig.objects.get_or_create(id=1)

    query = request.GET.get('q', '').strip()
    type_filter = request.GET.get('type', '').strip()
    status_filter = request.GET.get('status', '').strip()

    if query:
        backups_qs = backups_qs.filter(
            Q(backup_name__icontains=query) |
            Q(notes__icontains=query) |
            Q(created_by__username__icontains=query)
        )

    if type_filter:
        backups_qs = backups_qs.filter(backup_type=type_filter)

    if status_filter:
        backups_qs = backups_qs.filter(status=status_filter)

    paginator = Paginator(backups_qs, 12)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'total_backups': total_backups,
        'latest_backup': latest_backup,
        'successful_backups': successful_backups,
        'failed_backups': failed_backups,
        'success_rate': success_rate,
        'storage_usage_str': storage_usage_str,
        'last_recovery': last_recovery,
        'schedule_config': schedule_config,
        'page_obj': page_obj,
        'backups': page_obj.object_list,
        'query': query,
        'type_filter': type_filter,
        'status_filter': status_filter,
        'backup_types': BackupType.choices,
        'backup_statuses': BackupStatus.choices,
    }
    return render(request, 'backups/dashboard.html', context)


@admin_required
def create_manual_backup_view(request):
    if request.method == 'POST':
        backup_type = request.POST.get('backup_type', BackupType.FULL)
        notes = request.POST.get('notes', '').strip()

        try:
            record = create_backup_archive(backup_type=backup_type, user=request.user, notes=notes)
            messages.success(request, f"System backup '{record.backup_name}' ({record.get_formatted_file_size()}) generated and encrypted successfully.")
        except Exception as e:
            messages.error(request, f"Failed to generate system backup: {str(e)}")

    return redirect('admin_backup_dashboard')


@admin_required
def download_backup_view(request, backup_id):
    record = get_object_or_404(BackupRecord, id=backup_id)
    file_path = Path(record.storage_path)

    if not file_path.exists():
        messages.error(request, f"Backup file '{record.backup_name}' was not found on storage disk.")
        return redirect('admin_backup_dashboard')

    AuditLog.objects.create(
        actor=request.user,
        action="BACKUP_DOWNLOADED",
        details=f"Downloaded backup SQL dump file '{record.backup_name}' ({record.get_formatted_file_size()})",
        ip_address=request.META.get('REMOTE_ADDR')
    )

    sql_filename = record.backup_name
    if not sql_filename.endswith('.sql'):
        sql_filename = sql_filename.replace('.zip', '.sql')
        if not sql_filename.endswith('.sql'):
            sql_filename += '.sql'

    try:
        with open(file_path, 'rb') as f:
            header = f.readline()
            payload_bytes = f.read()

        import io, zipfile
        with zipfile.ZipFile(io.BytesIO(payload_bytes)) as z:
            sql_files = [item for item in z.namelist() if item.endswith('.sql')]
            if sql_files:
                sql_data = z.read(sql_files[0])
            else:
                sql_data = payload_bytes
    except Exception:
        with open(file_path, 'rb') as f:
            sql_data = f.read()

    response = HttpResponse(sql_data, content_type='application/sql')
    response['Content-Disposition'] = f'attachment; filename="{sql_filename}"'
    return response


@admin_required
def verify_backup_view(request, backup_id):
    record = get_object_or_404(BackupRecord, id=backup_id)
    is_valid, msg = verify_backup_integrity(record)

    AuditLog.objects.create(
        actor=request.user,
        action="BACKUP_VERIFIED",
        details=f"Verified backup '{record.backup_name}' integrity: {msg}",
        ip_address=request.META.get('REMOTE_ADDR')
    )

    if is_valid:
        messages.success(request, f"Backup '{record.backup_name}' integrity verified successfully! Checksum & AES-256 validity confirmed.")
    else:
        messages.error(request, f"Backup verification failed! {msg}")

    return redirect('admin_backup_dashboard')


@admin_required
def restore_backup_view(request, backup_id):
    record = get_object_or_404(BackupRecord, id=backup_id)

    if not (request.user.is_superuser or request.user.is_admin()):
        messages.error(request, "Permission Denied: Only Super Administrators can restore system backups.")
        return redirect('admin_backup_dashboard')

    if request.method == 'POST':
        form = RestoreConfirmationForm(request.POST)
        if form.is_valid():
            admin_password = form.cleaned_data['admin_password']
            try:
                recovery = restore_backup_archive(
                    backup_record=record,
                    admin_user=request.user,
                    admin_password=admin_password
                )
                messages.success(request, f"System restored successfully from backup '{record.backup_name}' in {recovery.recovery_duration} seconds.")
                return redirect('admin_backup_dashboard')
            except Exception as e:
                messages.error(request, f"Restoration failed: {str(e)}")
    else:
        form = RestoreConfirmationForm()

    context = {
        'backup': record,
        'form': form
    }
    return render(request, 'backups/restore_confirm.html', context)


@admin_required
def delete_backup_view(request, backup_id):
    record = get_object_or_404(BackupRecord, id=backup_id)
    backup_name = record.backup_name
    file_path = Path(record.storage_path)

    if file_path.exists():
        try:
            os.remove(file_path)
        except Exception:
            pass

    record.delete()

    AuditLog.objects.create(
        actor=request.user,
        action="BACKUP_DELETED",
        details=f"Deleted backup archive '{backup_name}'",
        ip_address=request.META.get('REMOTE_ADDR')
    )

    messages.success(request, f"Backup archive '{backup_name}' has been deleted from system storage.")
    return redirect('admin_backup_dashboard')


@admin_required
def backup_settings_view(request):
    schedule_config, _ = BackupScheduleConfig.objects.get_or_create(id=1)

    if request.method == 'POST':
        form = BackupScheduleConfigForm(request.POST, instance=schedule_config)
        if form.is_valid():
            form.save()
            messages.success(request, "Backup schedule and retention settings updated successfully.")
            return redirect('admin_backup_dashboard')
    else:
        form = BackupScheduleConfigForm(instance=schedule_config)

    return render(request, 'backups/settings.html', {'form': form, 'config': schedule_config})
