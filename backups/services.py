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

import pyzipper
from django.core.mail import EmailMessage

BACKUP_PASSWORD = b"Admin@1234"

def send_backup_email_to_admin(backup_record, zip_file_path):
    """
    Sends the password-protected SQL backup archive strictly to registered Super Admin / Admin users via SMTP.
    Guarantees that Patient, Doctor, Staff, or other non-admin users never receive backup files.
    """
    from accounts.models import User
    from django.db import models as db_models
    admin_emails = list(User.objects.filter(
        db_models.Q(role=User.Role.ADMIN) | db_models.Q(is_superuser=True),
        is_active=True
    ).exclude(email='').values_list('email', flat=True).distinct())

    if not admin_emails:
        return False

    subject = f"Automated SQL Database Backup: {backup_record.backup_name}"
    now_str = timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC')

    body = f"""Dear Administrator,

Your scheduled system database backup has been generated successfully.

Backup Information:
----------------------------------------
Backup File Name: {backup_record.backup_name}
Created At: {backup_record.created_at.strftime('%Y-%m-%d %H:%M:%S UTC') if backup_record.created_at else now_str}
File Size: {backup_record.get_formatted_file_size()}
Backup Type: {backup_record.get_backup_type_display()}
SHA-256 Checksum: {backup_record.checksum}
Status: {backup_record.get_status_display()}

SECURITY & ENCRYPTION DETAILS:
----------------------------------------
• Encryption Standard: WinZip AES-256 Strong Password Protection (PBKDF2 HMAC-SHA1 key derivation)
• Encryption Tool/Library: pyzipper (Python ZipFile extension with PyCryptodome AES-256 engine)
• Protection Target: Password prompt required upon extraction/opening by WinZip, 7-Zip, or Python scripts.

IMPORTANT SECURITY NOTICE:
This password-protected archive is strictly confidential and restricted to system Administrators only.
Do NOT forward or share this file with Patient, Doctor, or non-admin roles.

Regards,
Healthcare Analytics & Prediction Platform (HAPP) Administration
"""

    try:
        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL if hasattr(settings, 'DEFAULT_FROM_EMAIL') else 'noreply@happ.com',
            to=admin_emails
        )

        if os.path.exists(zip_file_path):
            filename = os.path.basename(zip_file_path)
            with open(zip_file_path, 'rb') as f:
                email.attach(filename, f.read(), 'application/zip')

        email.send(fail_silently=False)

        AuditLog.objects.create(
            actor=backup_record.created_by,
            action="BACKUP_EMAIL_SENT",
            details=f"Sent password-protected backup archive '{backup_record.backup_name}' to Admin email(s): {', '.join(admin_emails)}"
        )
        return True
    except Exception as e:
        AuditLog.objects.create(
            actor=backup_record.created_by,
            action="BACKUP_EMAIL_FAILED",
            details=f"Failed sending backup email for '{backup_record.backup_name}': {str(e)}"
        )
        return False

def create_backup_archive(backup_type=BackupType.FULL, user=None, notes=""):
    start_time = time.time()
    ensure_backup_directories()

    timestamp = datetime.datetime.now().strftime('%Y_%m_%d_%H%M%S')
    sql_dump_filename = f"backup_{timestamp}.sql"
    zip_backup_filename = f"backup_{timestamp}.zip"

    sql_dump_path = BACKUP_ROOT_DIR / 'database' / sql_dump_filename
    compressed_file_path = BACKUP_ROOT_DIR / 'compressed' / zip_backup_filename
    encrypted_file_path = BACKUP_ROOT_DIR / 'encrypted' / f"backup_{timestamp}.zip"

    db_path = Path(settings.BASE_DIR) / 'db.sqlite3'
    media_path = Path(settings.MEDIA_ROOT) if hasattr(settings, 'MEDIA_ROOT') and settings.MEDIA_ROOT else Path(settings.BASE_DIR) / 'media'

    try:
        # 1. Generate Raw SQL Database Dump File
        if db_path.exists():
            generate_sqlite_dump(db_path, sql_dump_path)

        # 2. Compress .sql Dump into AES-256 Encrypted ZIP Archive (using pyzipper & password Admin@1234)
        with pyzipper.AESZipFile(
            encrypted_file_path,
            'w',
            compression=pyzipper.ZIP_DEFLATED,
            encryption=pyzipper.WZ_AES
        ) as zipf:
            zipf.setpassword(BACKUP_PASSWORD)

            if sql_dump_path.exists():
                zipf.write(sql_dump_path, arcname=sql_dump_filename)
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
                f"Encryption Standard: AES-256 (pyzipper / WinZip AES)\n"
                f"Platform: HAPP Clinical Platform\n"
            )
            zipf.writestr('config_metadata.txt', config_meta)

        file_size = os.path.getsize(encrypted_file_path)
        checksum = compute_file_sha256(encrypted_file_path)
        duration = round(time.time() - start_time, 2)

        record = BackupRecord.objects.create(
            backup_name=zip_backup_filename,
            backup_type=backup_type,
            created_by=user,
            file_size=file_size,
            storage_path=str(encrypted_file_path),
            encrypted=True,
            checksum=checksum,
            status=BackupStatus.SUCCESS,
            backup_duration=duration,
            notes=notes or f"AES-256 encrypted SQL database backup file ({zip_backup_filename}) protected with password 'Admin@1234'."
        )

        AuditLog.objects.create(
            actor=user,
            action="BACKUP_CREATED",
            details=f"Created password-protected AES-256 backup archive '{zip_backup_filename}' ({record.get_formatted_file_size()})"
        )

        if user:
            Notification.objects.create(
                user=user,
                message=f"System backup '{zip_backup_filename}' completed successfully and sent to Admin email.",
                notif_type="SUCCESS"
            )

        # 3. Dispatch Password-Protected Backup File to Admin Email via SMTP
        send_backup_email_to_admin(record, encrypted_file_path)

        return record

    except Exception as e:
        duration = round(time.time() - start_time, 2)
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

    sha256_hash = compute_file_sha256(file_path)
    if backup_record.checksum and sha256_hash != backup_record.checksum:
        return False, f"Checksum verification failed! Expected {backup_record.checksum[:8]}, got {sha256_hash[:8]}."

    try:
        with pyzipper.AESZipFile(file_path, 'r') as z:
            z.setpassword(BACKUP_PASSWORD)
            bad_file = z.testzip()
            if bad_file:
                return False, f"Corrupted file found inside archive: {bad_file}"
    except Exception as e:
        return False, f"AES-256 ZIP archive validation/decryption error: {str(e)}"

    return True, "Backup archive integrity and AES-256 password encryption verified successfully."

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

    temp_dir = BACKUP_ROOT_DIR / 'temp_restore'
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        with pyzipper.AESZipFile(file_path, 'r') as z:
            z.setpassword(BACKUP_PASSWORD)
            z.extractall(temp_dir)

        # 1. Look for .sql dump file in temp_restore
        sql_files = list(temp_dir.glob("*.sql")) + list((temp_dir / "database").glob("*.sql"))
        db_target = Path(settings.BASE_DIR) / 'db.sqlite3'

        if sql_files:
            sql_file = sql_files[0]
            from django.db import connection
            connection.close()

            # Re-create empty target database before running SQL script
            if db_target.exists():
                try:
                    os.remove(db_target)
                except Exception:
                    pass

            conn = sqlite3.connect(str(db_target))
            with open(sql_file, 'r', encoding='utf-8') as f:
                sql_script = f.read()
            conn.executescript(sql_script)
            conn.close()
        else:
            restored_db = temp_dir / 'database' / 'db.sqlite3'
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
