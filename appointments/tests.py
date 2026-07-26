import datetime
from django.test import TestCase
from django.db import IntegrityError
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client

from appointments.models import Specialization, Appointment, EmailLog
from doctors.models import DoctorProfile
from patients.models import PatientProfile
from core.models import Notification

User = get_user_model()

class AppointmentModuleFeatureTests(TestCase):
    def setUp(self):
        self.spec = Specialization.objects.create(name="Cardiology")

        self.doc_user = User.objects.create_user(
            username='doc_test',
            email='doc_test@example.com',
            password='Password123!',
            role=User.Role.DOCTOR,
            phone='9876543210'
        )
        self.doctor = DoctorProfile.objects.create(
            user=self.doc_user,
            specialization=self.spec,
            license_number='LIC-BOOK-1',
            qualification='MD',
            hospital_name='Central Hospital',
            is_approved=True
        )

        self.p1_user = User.objects.create_user(
            username='patient_test',
            email='patient_test@example.com',
            password='Password123!',
            role=User.Role.PATIENT,
            phone='9123456781'
        )
        self.patient_profile = PatientProfile.objects.create(user=self.p1_user, height_cm=175.0, weight_kg=72.0)

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
        p2_user = User.objects.create_user(username='p2', password='Password123!', role=User.Role.PATIENT, phone='9123456782')
        with self.assertRaises(IntegrityError):
            Appointment.objects.create(
                patient=p2_user,
                doctor=self.doctor,
                date=date_target,
                time_slot=slot,
                reason='Consultation 2'
            )

    def test_is_past_property_and_display_status(self):
        past_date = datetime.date.today() - datetime.timedelta(days=2)
        past_app = Appointment.objects.create(
            patient=self.p1_user,
            doctor=self.doctor,
            date=past_date,
            time_slot='09:00',
            reason='Past checkup'
        )
        self.assertTrue(past_app.is_past)
        self.assertIn('Expired', past_app.display_status)

    def test_3hour_reminder_management_command(self):
        now = datetime.datetime.now()
        today = now.date()
        future_time = now + datetime.timedelta(hours=2)
        slot_str = f"{future_time.hour:02d}:{future_time.minute:02d}"

        # Appointment scheduled today in 2 hours
        app = Appointment.objects.create(
            patient=self.p1_user,
            doctor=self.doctor,
            date=today,
            time_slot=slot_str,
            status=Appointment.Status.APPROVED,
            reminder_3h_sent=False
        )

        # Run management command
        call_command('send_appointment_reminders')
        app.refresh_from_db()
        self.assertTrue(app.reminder_3h_sent)

    def test_patient_reschedule_appointment_flow(self):
        future_date1 = datetime.date.today() + datetime.timedelta(days=2)
        future_date2 = datetime.date.today() + datetime.timedelta(days=5)

        app = Appointment.objects.create(
            patient=self.p1_user,
            doctor=self.doctor,
            date=future_date1,
            time_slot='09:00',
            status=Appointment.Status.APPROVED
        )

        client = Client()
        client.login(username='patient_test', password='Password123!')

        # Reschedule POST request
        response = client.post(f'/appointments/{app.id}/reschedule/', {
            'date': future_date2.strftime('%Y-%m-%d'),
            'time_slot': '11:00',
            'reason': 'Conflict with work schedule'
        })
        self.assertEqual(response.status_code, 302)

        app.refresh_from_db()
        self.assertEqual(app.date, future_date2)
        self.assertEqual(app.time_slot, '11:00')
        self.assertEqual(app.status, Appointment.Status.RESCHEDULED)

        # Doctor Notification created
        notif = Notification.objects.filter(user=self.doc_user).first()
        self.assertIsNotNone(notif)
        self.assertIn("rescheduled Appointment", notif.message)
