import copy
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.template.context import Context, RequestContext

# Python 3.14 compatibility patch for Django Context copying in test runner
def _context_copy(self):
    obj = Context.__new__(Context)
    obj.dicts = self.dicts[:]
    return obj

Context.__copy__ = _context_copy

def _request_context_copy(self):
    obj = RequestContext.__new__(RequestContext)
    obj.dicts = self.dicts[:]
    obj.request = getattr(self, 'request', None)
    return obj

RequestContext.__copy__ = _request_context_copy

from patients.models import PatientProfile, MedicalReport, validate_report_file
from doctors.models import DoctorProfile
from appointments.models import Appointment, Specialization
from core.models import Notification, AuditLog

User = get_user_model()

class MedicalReportModuleTests(TestCase):
    def setUp(self):
        self.spec = Specialization.objects.create(name="Cardiology")

        # Patient 1
        self.patient_user1 = User.objects.create_user(
            username='patient_one',
            email='patient1@example.com',
            password='PatientPassword123!',
            role=User.Role.PATIENT,
            phone='9123456781'
        )
        self.patient_profile1 = PatientProfile.objects.create(user=self.patient_user1)

        # Patient 2
        self.patient_user2 = User.objects.create_user(
            username='patient_two',
            email='patient2@example.com',
            password='PatientPassword123!',
            role=User.Role.PATIENT,
            phone='9123456782'
        )
        self.patient_profile2 = PatientProfile.objects.create(user=self.patient_user2)

        # Doctor
        self.doc_user = User.objects.create_user(
            username='doctor_one',
            email='doctor1@example.com',
            password='DoctorPassword123!',
            role=User.Role.DOCTOR,
            phone='9876543210'
        )
        self.doc_profile = DoctorProfile.objects.create(
            user=self.doc_user,
            specialization=self.spec,
            license_number='DOC-888',
            is_approved=True
        )

        # Admin
        self.admin_user = User.objects.create_user(
            username='admin_one',
            email='admin1@example.com',
            password='AdminPassword123!',
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True
        )

        # Appointment assigning Patient 1 to Doctor
        self.appointment = Appointment.objects.create(
            patient=self.patient_user1,
            doctor=self.doc_profile,
            date='2026-08-01',
            time_slot='09:00',
            status=Appointment.Status.APPROVED,
            reason='Routine Checkup'
        )

        # Sample valid PDF file
        self.sample_pdf = SimpleUploadedFile(
            "blood_report.pdf",
            b"%PDF-1.4 sample pdf content for medical report testing",
            content_type="application/pdf"
        )

    def test_file_validator_accepts_valid_pdf_and_images(self):
        """Verify validate_report_file accepts valid PDF files."""
        try:
            validate_report_file(self.sample_pdf)
        except ValidationError:
            self.fail("validate_report_file unexpectedly raised ValidationError on valid PDF.")

    def test_file_validator_rejects_executables_and_scripts(self):
        """Verify validate_report_file rejects dangerous extensions like EXE and PHP."""
        exe_file = SimpleUploadedFile("malicious.exe", b"binary data", content_type="application/x-msdownload")
        with self.assertRaises(ValidationError):
            validate_report_file(exe_file)

        php_file = SimpleUploadedFile("script.php", b"<?php echo 1; ?>", content_type="text/plain")
        with self.assertRaises(ValidationError):
            validate_report_file(php_file)

    def test_patient_can_upload_report(self):
        """Verify patient can upload a medical report successfully."""
        self.client.login(username='patient_one', password='PatientPassword123!')

        response = self.client.post('/patients/medical-reports/', {
            'report_name': 'CBC Blood Test',
            'report_category': 'Blood Test',
            'description': 'Normal routine lab results',
            'file': self.sample_pdf
        })
        self.assertEqual(response.status_code, 302)

        report = MedicalReport.objects.filter(patient=self.patient_profile1, report_name='CBC Blood Test').first()
        self.assertIsNotNone(report)
        self.assertEqual(report.report_category, 'Blood Test')
        self.assertEqual(report.review_status, 'PENDING')

    def test_idor_protection_prevents_unauthorized_patient_access(self):
        """Verify Patient 2 cannot access or preview Patient 1's report."""
        report = MedicalReport.objects.create(
            patient=self.patient_profile1,
            report_name='Private Scan',
            report_category='MRI',
            file=self.sample_pdf,
            file_size=self.sample_pdf.size,
            file_type='application/pdf'
        )

        self.client.login(username='patient_two', password='PatientPassword123!')

        # Attempt preview
        response = self.client.get(f'/patients/medical-reports/{report.id}/preview/')
        self.assertEqual(response.status_code, 403)

        # Attempt download
        response = self.client.get(f'/patients/medical-reports/{report.id}/download/')
        self.assertEqual(response.status_code, 403)

    def test_doctor_can_review_assigned_patient_report(self):
        """Verify assigned doctor can view and review patient's medical report."""
        report = MedicalReport.objects.create(
            patient=self.patient_profile1,
            doctor=self.doc_profile,
            report_name='Heart ECG',
            report_category='ECG',
            file=self.sample_pdf,
            file_size=self.sample_pdf.size,
            file_type='application/pdf'
        )

        self.client.login(username='doctor_one', password='DoctorPassword123!')

        response = self.client.post(f'/doctors/reports/{report.id}/review/', {
            'review_status': 'REVIEWED',
            'doctor_notes': 'Heart rhythm appears normal.'
        })
        self.assertEqual(response.status_code, 302)

        report.refresh_from_db()
        self.assertEqual(report.review_status, 'REVIEWED')
        self.assertEqual(report.doctor_notes, 'Heart rhythm appears normal.')

        # Verify Notification sent to patient
        notif = Notification.objects.filter(user=self.patient_user1).first()
        self.assertIsNotNone(notif)
        self.assertIn("reviewed your medical report", notif.message)

    def test_admin_can_view_analytics_and_delete_report(self):
        """Verify admin can view analytics dashboard and delete inappropriate reports."""
        report = MedicalReport.objects.create(
            patient=self.patient_profile1,
            report_name='Duplicate Report',
            report_category='Other',
            file=self.sample_pdf,
            file_size=self.sample_pdf.size,
            file_type='application/pdf'
        )

        self.client.login(username='admin_one', password='AdminPassword123!')

        response = self.client.get('/administration/reports/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Duplicate Report", response.content)

        # Admin delete action
        del_resp = self.client.get(f'/administration/reports/{report.id}/delete/')
        self.assertEqual(del_resp.status_code, 302)

        report.refresh_from_db()
        self.assertTrue(report.is_deleted)
