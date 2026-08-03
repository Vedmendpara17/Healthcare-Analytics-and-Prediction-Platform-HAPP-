from django.test import TestCase, RequestFactory, Client
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.utils import timezone
import datetime

from accounts.views import login_view
from doctors.models import DoctorProfile
from patients.models import PatientProfile
from appointments.models import Specialization

User = get_user_model()

class RoleBasedAccessControlTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.spec = Specialization.objects.create(name="Cardiology")

        # Admin user
        self.admin = User.objects.create_user(
            username='admin_test',
            email='admin_test@example.com',
            password='AdminPassword123!',
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True
        )

        # Approved doctor user
        self.doc_user = User.objects.create_user(
            username='doctor_test',
            email='doctor_test@example.com',
            password='DoctorPassword123!',
            role=User.Role.DOCTOR,
            phone='9876543210'
        )
        self.doc_profile = DoctorProfile.objects.create(
            user=self.doc_user,
            specialization=self.spec,
            license_number='LIC-100',
            qualification='MD',
            hospital_name='Test Hospital',
            is_approved=True
        )

        # Unapproved doctor user
        self.unapproved_doc = User.objects.create_user(
            username='unapproved_doc',
            email='unapproved_doc@example.com',
            password='DoctorPassword123!',
            role=User.Role.DOCTOR,
            phone='9876543211'
        )
        self.unapproved_profile = DoctorProfile.objects.create(
            user=self.unapproved_doc,
            specialization=self.spec,
            license_number='LIC-101',
            qualification='MBBS',
            hospital_name='Test Clinic',
            is_approved=False
        )

        # Patient user
        self.patient_user = User.objects.create_user(
            username='patient_test',
            email='patient_test@example.com',
            password='PatientPassword123!',
            role=User.Role.PATIENT,
            phone='9123456789'
        )
        self.patient_profile = PatientProfile.objects.create(
            user=self.patient_user
        )

        self.client = Client()

    def _add_messages_and_session(self, request):
        setattr(request, 'session', self.client.session)
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

    def test_account_lockout_after_5_failed_attempts(self):
        """Verify account locks on 5th consecutive failed login attempt."""
        from django.contrib.auth.models import AnonymousUser
        
        # 4 failed attempts
        for i in range(4):
            request = self.factory.post('/auth/login/', {'username': 'patient_test', 'password': 'WrongPassword123!'})
            request.user = AnonymousUser()
            self._add_messages_and_session(request)
            response = login_view(request)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Invalid email or password", response.content)

        self.patient_user.refresh_from_db()
        self.assertFalse(self.patient_user.is_account_locked())

        # 5th failed attempt -> Lockout
        request = self.factory.post('/auth/login/', {'username': 'patient_test', 'password': 'WrongPassword123!'})
        request.user = AnonymousUser()
        self._add_messages_and_session(request)
        response = login_view(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"temporarily locked", response.content)

        self.patient_user.refresh_from_db()
        self.assertTrue(self.patient_user.is_account_locked())

    def test_password_validator_rules(self):
        """Verify custom StrongPasswordValidator enforcement."""
        from accounts.validators import StrongPasswordValidator
        from django.core.exceptions import ValidationError

        validator = StrongPasswordValidator()

        # Weak password test
        with self.assertRaises(ValidationError):
            validator.validate('password')

        # Missing special char test
        with self.assertRaises(ValidationError):
            validator.validate('Het1222234')

        # Contains username test
        user = User(username='hetal', email='hetal@example.com', phone='9876543210')
        with self.assertRaises(ValidationError):
            validator.validate('Hetal@1222', user=user)

        # Valid password test
        try:
            validator.validate('ValidP@ssw0rd2026', user=user)
        except ValidationError:
            self.fail("StrongPasswordValidator raised ValidationError unexpectedly on valid password!")


class DirectAuthenticationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='direct_user',
            email='direct_user@example.com',
            password='Password123!',
            role=User.Role.PATIENT
        )
        self.client = Client()

    def test_direct_login_redirects_to_dashboard(self):
        res = self.client.post('/auth/login/', {'username': 'direct_user', 'password': 'Password123!'})
        self.assertEqual(res.status_code, 302)
        self.assertIn('/auth/dashboard/', res.url)
