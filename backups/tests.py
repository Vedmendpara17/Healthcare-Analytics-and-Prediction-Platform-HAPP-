import os
import shutil
from pathlib import Path
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core.management import call_command

from backups.models import BackupRecord, RecoveryRecord, BackupScheduleConfig, BackupType, BackupStatus
from backups.services import create_backup_archive, verify_backup_integrity, restore_backup_archive, purge_expired_backups, BACKUP_ROOT_DIR

User = get_user_model()

class BackupAndRecoverySystemTests(TestCase):
    def setUp(self):
        self.super_admin = User.objects.create_user(
            username='super_admin_test',
            email='superadmin@example.com',
            password='SuperPassword123!',
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
            email_verified=True
        )

        self.doctor = User.objects.create_user(
            username='doctor_test',
            email='doc@example.com',
            password='DoctorPassword123!',
            role=User.Role.DOCTOR,
            email_verified=True
        )

        self.patient = User.objects.create_user(
            username='patient_test',
            email='patient@example.com',
            password='PatientPassword123!',
            role=User.Role.PATIENT,
            email_verified=True
        )

    def tearDown(self):
        if BACKUP_ROOT_DIR.exists():
            shutil.rmtree(BACKUP_ROOT_DIR, ignore_errors=True)

    def test_create_backup_archive_service(self):
        record = create_backup_archive(backup_type=BackupType.FULL, user=self.super_admin, notes="Test snapshot")
        self.assertIsNotNone(record)
        self.assertEqual(record.status, BackupStatus.SUCCESS)
        self.assertTrue(record.checksum)
        self.assertTrue(os.path.exists(record.storage_path))
        self.assertTrue(record.file_size > 0)

    def test_verify_backup_integrity_service(self):
        record = create_backup_archive(backup_type=BackupType.FULL, user=self.super_admin)
        is_valid, msg = verify_backup_integrity(record)
        self.assertTrue(is_valid)
        self.assertIn("verified successfully", msg)

    def test_restore_backup_archive_requires_super_admin(self):
        record = create_backup_archive(backup_type=BackupType.FULL, user=self.super_admin)

        # Invalid password test
        with self.assertRaises(ValueError):
            restore_backup_archive(record, self.super_admin, "WrongPassword123!")

        # Valid restore test
        recovery = restore_backup_archive(record, self.super_admin, "SuperPassword123!")
        self.assertIsNotNone(recovery)
        self.assertEqual(recovery.recovery_status, BackupStatus.SUCCESS)

    def test_run_scheduled_backup_management_command(self):
        call_command('run_scheduled_backup')
        self.assertEqual(BackupRecord.objects.count(), 1)
        record = BackupRecord.objects.first()
        self.assertEqual(record.status, BackupStatus.SUCCESS)

    def test_admin_dashboard_role_gating(self):
        # Patient denied access
        pat_client = Client()
        pat_client.force_login(self.patient)
        res_pat = pat_client.get('/administration/backups/')
        self.assertEqual(res_pat.status_code, 302)

        # Super Admin granted access
        adm_client = Client()
        adm_client.force_login(self.super_admin)
        res_adm = adm_client.get('/administration/backups/')
        self.assertEqual(res_adm.status_code, 200)
        self.assertIn(b"System Backup", res_adm.content)
