from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from accounts.views import login_view
from administration.views import admin_dashboard_view

from accounts.decorators import role_required
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
            password='AdminPassword123!',
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True
        )

        # Approved doctor user
        self.doc_user = User.objects.create_user(
            username='doctor_test',
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
            password='PatientPassword123!',
            role=User.Role.PATIENT,
            phone='9123456789'
        )
        self.patient_profile = PatientProfile.objects.create(
            user=self.patient_user,
            gender='Male'
        )

    def _add_messages_and_session(self, request):
        setattr(request, 'session', {})
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

    def test_unapproved_doctor_login_gated(self):
        """Verify unapproved doctor login gating in login_view."""
        from django.contrib.auth.models import AnonymousUser
        request = self.factory.post('/auth/login/', {
            'username': 'unapproved_doc',
            'password': 'DoctorPassword123!'
        })
        request.user = AnonymousUser()
        self._add_messages_and_session(request)
        response = login_view(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"pending Admin approval", response.content)


    def test_patient_cannot_access_admin_dashboard(self):
        """Verify patient is redirected away from admin dashboard."""
        request = self.factory.get('/administration/dashboard/')
        request.user = self.patient_user
        self._add_messages_and_session(request)
        
        # Test decorator directly
        from administration.views import admin_dashboard_view
        response = admin_dashboard_view(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/patients/dashboard/')

    def test_doctor_cannot_access_admin_dashboard(self):
        """Verify doctor is redirected away from admin dashboard."""
        request = self.factory.get('/administration/dashboard/')
        request.user = self.doc_user
        self._add_messages_and_session(request)

        from administration.views import admin_dashboard_view
        response = admin_dashboard_view(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/doctors/dashboard/')

    def test_admin_can_access_admin_dashboard(self):
        """Verify admin user can reach admin dashboard."""
        request = self.factory.get('/administration/dashboard/')
        request.user = self.admin
        self._add_messages_and_session(request)

        from administration.views import admin_dashboard_view
        response = admin_dashboard_view(request)
        self.assertEqual(response.status_code, 200)
