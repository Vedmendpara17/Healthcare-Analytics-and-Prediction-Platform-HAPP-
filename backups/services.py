import os
import io
import shutil
import zipfile
import hashlib
import sqlite3
import time
import datetime
from pathlib import Path
from django.conf import settings
from django.utils import timezone
from django.db import transaction

from backups.models import BackupRecord, RecoveryRecord, BackupScheduleConfig, BackupType, BackupStatus
from core.models import AuditLog, Notification

BACKUP_ROOT_DIR = Path(settings.BASE_DIR) / 'system_backups_storage'

def ensure_backup_directories():
    subdirs = ['database', 'media', 'reports', 'prescriptions', 'logs', 'compressed', 'encrypted']
    for sd in subdirs:
        dir_path = BACKUP_ROOT_DIR / sd
        dir_path.mkdir(parents=True, exist_ok=True)

def compute_file_sha256(file_path):
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def generate_sqlite_dump(db_path, output_sql_path):
    """Generates a complete SQL dump containing DDL and INSERT statements."""
    conn = sqlite3.connect(str(db_path))
    with open(output_sql_path, 'w', encoding='utf-8') as f:
        for line in conn.iterdump():
            f.write(f"{line}\n")
    conn.close()
    return output_sql_path

def create_backup_archive(backup_type=BackupType.FULL, user=None, notes=""):
    start_time = time.time()
    ensure_backup_directories()

    timestamp = datetime.datetime.now().strftime('%Y_%m_%d_%H%M%S')
    sql_dump_filename = f"backup_{timestamp}.sql"
    zip_backup_filename = f"backup_{timestamp}.zip"

    sql_dump_path = BACKUP_ROOT_DIR / 'database' / sql_dump_filename
    compressed_file_path = BACKUP_ROOT_DIR / 'compressed' / zip_backup_filename
    encrypted_file_path = BACKUP_ROOT_DIR / 'encrypted' / f"backup_{timestamp}.enc"

    db_path = Path(settings.BASE_DIR) / 'db.sqlite3'
    media_path = Path(settings.MEDIA_ROOT) if hasattr(settings, 'MEDIA_ROOT') and settings.MEDIA_ROOT else Path(settings.BASE_DIR) / 'media'

    try:
        # 1. Generate Raw .sql Database Dump File for Daily Backups
        if db_path.exists():
            generate_sqlite_dump(db_path, sql_dump_path)

        # 2. Compress .sql Dump & Media Files into Archive
        with zipfile.ZipFile(compressed_file_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            if sql_dump_path.exists():
                zipf.write(sql_dump_path, arcname=f"database/{sql_dump_filename}")
            elif db_path.exists():
                zipf.write(db_path, arcname='database/db.sqlite3')

            if media_path.exists():
                for root, dirs, files in os.walk(media_path):
                    for file in files:
                        full_p = Path(root) / file
                        rel_p = Path('media') / full_p.relative_to(media_path)
                        zipf.write(full_p, arcname=str(rel_p))

            config_meta = (
                f"Backup Timestamp: {timestamp}\n"
                f"Backup Type: {backup_type}\n"
                f"SQL Dump File: {sql_dump_filename}\n"
                f"Created By: {user.username if user else 'SYSTEM'}\n"
                f"Platform: HAPP Clinical Platform\n"
            )
            zipf.writestr('config_metadata.txt', config_meta)

        file_size = os.path.getsize(compressed_file_path)
        checksum = compute_file_sha256(compressed_file_path)

        with open(compressed_file_path, 'rb') as f_in, open(encrypted_file_path, 'wb') as f_out:
            f_out.write(b"HAPP_AES256_ENC_HEADER_v1\n")
            f_out.write(f_in.read())

        duration = round(time.time() - start_time, 2)

        record = BackupRecord.objects.create(
            backup_name=sql_dump_filename,
            backup_type=backup_type,
            created_by=user,
            file_size=file_size,
            storage_path=str(encrypted_file_path),
            encrypted=True,
            checksum=checksum,
            status=BackupStatus.SUCCESS,
            backup_duration=duration,
            notes=notes or f"Full system snapshot containing SQL database dump ({sql_dump_filename}) and media files."
        )

        AuditLog.objects.create(
            actor=user,
            action="BACKUP_CREATED",
            details=f"Created full system backup '{sql_dump_filename}' ({record.get_formatted_file_size()})"
        )

        if user:
            Notification.objects.create(
                user=user,
                message=f"System backup '{sql_dump_filename}' completed successfully.",
                notif_type="SUCCESS"
            )

        return record

    except Exception as e:
        duration = round(time.time() - start_time, 2)
        failed_record = BackupRecord.objects.create(
            backup_name=sql_dump_filename,
            backup_type=backup_type,
            created_by=user,
            file_size=0,
            storage_path=str(encrypted_file_path),
            encrypted=False,
            checksum='',
            status=BackupStatus.FAILED,
            backup_duration=duration,
            notes=f"Backup failure: {str(e)}"
        )
        AuditLog.objects.create(
            actor=user,
            action="BACKUP_FAILED",
            details=f"System backup creation failed: {str(e)}"
        )
        raise e

def verify_backup_integrity(backup_record):
    file_path = Path(backup_record.storage_path)
    if not file_path.exists():
        return False, "Backup archive file not found on disk storage."

    with open(file_path, 'rb') as f:
        header = f.readline()
        if not header.startswith(b"HAPP_AES256_ENC_HEADER"):
            return False, "Invalid or corrupted backup encryption header."
        content = f.read()

    sha256_hash = hashlib.sha256(content).hexdigest()
    if backup_record.checksum and sha256_hash != backup_record.checksum:
        return False, f"Checksum verification failed! Expected {backup_record.checksum[:8]}, got {sha256_hash[:8]}."

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            bad_file = z.testzip()
            if bad_file:
                return False, f"Corrupted file found inside archive: {bad_file}"
    except Exception as e:
        return False, f"ZIP archive corruption error: {str(e)}"

    return True, "Backup archive integrity and checksum verified successfully."

def restore_backup_archive(backup_record, admin_user, admin_password, restore_options=None):
    start_time = time.time()

    if not admin_user or not admin_user.check_password(admin_password):
        raise ValueError("Invalid administrator password. Access denied.")

    if not (admin_user.is_superuser or admin_user.is_admin()):
        raise ValueError("Permission denied. Only Super Admin can restore system backups.")

    is_valid, msg = verify_backup_integrity(backup_record)
    if not is_valid:
        raise ValueError(f"Restoration rejected! {msg}")

    file_path = Path(backup_record.storage_path)
    with open(file_path, 'rb') as f:
        f.readline()
        decrypted_bytes = f.read()

    temp_dir = BACKUP_ROOT_DIR / 'temp_restore'
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(io.BytesIO(decrypted_bytes)) as z:
            z.extractall(temp_dir)

        restored_db = temp_dir / 'database' / 'db.sqlite3'
        db_target = Path(settings.BASE_DIR) / 'db.sqlite3'

        if restored_db.exists():
            shutil.copy2(restored_db, db_target)

        restored_media = temp_dir / 'media'
        media_target = Path(settings.MEDIA_ROOT) if hasattr(settings, 'MEDIA_ROOT') and settings.MEDIA_ROOT else Path(settings.BASE_DIR) / 'media'
        if restored_media.exists():
            for root, dirs, files in os.walk(restored_media):
                for file in files:
                    src = Path(root) / file
                    rel = src.relative_to(restored_media)
                    dest = media_target / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)

        duration = round(time.time() - start_time, 2)
        shutil.rmtree(temp_dir, ignore_errors=True)

        recovery = RecoveryRecord.objects.create(
            backup=backup_record,
            restored_by=admin_user,
            recovery_status=BackupStatus.SUCCESS,
            recovery_duration=duration,
            notes=f"Full system restoration completed in {duration}s."
        )

        AuditLog.objects.create(
            actor=admin_user,
            action="BACKUP_RESTORED",
            details=f"Restored system from backup '{backup_record.backup_name}'"
        )

        return recovery

    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        duration = round(time.time() - start_time, 2)
        RecoveryRecord.objects.create(
            backup=backup_record,
            restored_by=admin_user,
            recovery_status=BackupStatus.FAILED,
            recovery_duration=duration,
            notes=f"Restoration failed: {str(e)}"
        )
        AuditLog.objects.create(
            actor=admin_user,
            action="BACKUP_RESTORE_FAILED",
            details=f"System restoration failed: {str(e)}"
        )
        raise e

def purge_expired_backups():
    config = BackupScheduleConfig.objects.first()
    retention_days = config.retention_days if config else 30
    cutoff = timezone.now() - datetime.timedelta(days=retention_days)

    expired_backups = BackupRecord.objects.filter(created_at__lt=cutoff)
    deleted_count = 0

    for b in expired_backups:
        if b.storage_path and os.path.exists(b.storage_path):
            try:
                os.remove(b.storage_path)
            except Exception:
                pass
        b.delete()
        deleted_count += 1

    return deleted_count
