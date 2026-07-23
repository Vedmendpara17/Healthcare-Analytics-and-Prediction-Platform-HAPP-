from django.test import TestCase
from django.db import IntegrityError
from django.contrib.auth import get_user_model
import datetime

from appointments.models import Specialization, Appointment
from doctors.models import DoctorProfile
from patients.models import PatientProfile

User = get_user_model()

class DoubleBookingPreventionTests(TestCase):
    def setUp(self):
        self.spec = Specialization.objects.create(name="Cardiology")

        self.doc_user = User.objects.create_user(
            username='doc_book',
            password='Password123!',
            role=User.Role.DOCTOR,
            phone='9876543210'
        )
        self.doctor = DoctorProfile.objects.create(
            user=self.doc_user,
            specialization=self.spec,
            license_number='LIC-BOOK-1',
            qualification='MD',
            hospital_name='Clinic',
            is_approved=True
        )

        self.p1_user = User.objects.create_user(username='p1', password='Password123!', role=User.Role.PATIENT, phone='9123456781')
        self.p2_user = User.objects.create_user(username='p2', password='Password123!', role=User.Role.PATIENT, phone='9123456782')

    def test_duplicate_slot_booking_raises_integrity_error(self):
        date_target = datetime.date.today() + datetime.timedelta(days=3)
        slot = '10:00'

        # First booking succeeds
        Appointment.objects.create(
            patient=self.p1_user,
            doctor=self.doctor,
            date=date_target,
            time_slot=slot,
            reason='Consultation 1'
        )

        # Second booking for same doctor, date, and slot must raise IntegrityError due to unique constraint
        with self.assertRaises(IntegrityError):
            Appointment.objects.create(
                patient=self.p2_user,
                doctor=self.doctor,
                date=date_target,
                time_slot=slot,
                reason='Consultation 2'
            )
