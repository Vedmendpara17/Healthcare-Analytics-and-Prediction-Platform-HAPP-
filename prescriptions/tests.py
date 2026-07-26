import datetime
from django.test import TestCase, Client
from django.contrib.auth import get_user_model

from prescriptions.models import Prescription, PrescriptionMedicine, PrescriptionStatus
from doctors.models import DoctorProfile
from patients.models import PatientProfile
from appointments.models import Appointment, Specialization
from prescriptions.services import generate_prescription_pdf

User = get_user_model()

class EPrescriptionModuleTests(TestCase):
    def setUp(self):
        self.spec = Specialization.objects.create(name="Internal Medicine")

        self.doc_user = User.objects.create_user(
            username='doc_rx',
            email='doc_rx@example.com',
            password='Password123!',
            role=User.Role.DOCTOR,
            phone='9876543200'
        )
        self.doctor = DoctorProfile.objects.create(
            user=self.doc_user,
            specialization=self.spec,
            license_number='LIC-RX-101',
            qualification='MD Medicine',
            hospital_name='City Medical Center',
            is_approved=True
        )

        self.patient_user = User.objects.create_user(
            username='patient_rx',
            email='patient_rx@example.com',
            password='Password123!',
            role=User.Role.PATIENT,
            phone='9123456700'
        )
        self.patient_profile = PatientProfile.objects.create(user=self.patient_user, height_cm=170, weight_kg=68)

        self.other_patient_user = User.objects.create_user(
            username='other_rx',
            email='other_rx@example.com',
            password='Password123!',
            role=User.Role.PATIENT,
            phone='9123456799'
        )

        self.appointment = Appointment.objects.create(
            patient=self.patient_user,
            doctor=self.doctor,
            date=datetime.date.today(),
            time_slot='10:00',
            status=Appointment.Status.COMPLETED,
            reason='Acute Fever and Cough'
        )

        self.client = Client()

    def test_prescription_and_medicine_creation(self):
        rx = Prescription.objects.create(
            patient=self.patient_user,
            doctor=self.doctor,
            appointment=self.appointment,
            diagnosis='Acute Viral Bronchitis',
            symptoms='Persistent cough, mild fever',
            clinical_notes='Drink plenty of fluids and rest.',
            follow_up_date=datetime.date.today() + datetime.timedelta(days=7),
            prescription_status=PrescriptionStatus.FINALIZED
        )

        self.assertTrue(rx.prescription_number.startswith('RX-'))
        
        med = PrescriptionMedicine.objects.create(
            prescription=rx,
            medicine_name='Amoxicillin',
            medicine_type='Tablet',
            strength='500 mg',
            dosage='1 Tablet',
            frequency='1-0-1 (Morning + Night)',
            duration='5 Days',
            meal_instruction='After Food',
            quantity='10'
        )
        self.assertEqual(rx.medicines.count(), 1)
        self.assertEqual(med.medicine_name, 'Amoxicillin')

    def test_reportlab_pdf_generator(self):
        rx = Prescription.objects.create(
            patient=self.patient_user,
            doctor=self.doctor,
            appointment=self.appointment,
            diagnosis='Hypertension',
            prescription_status=PrescriptionStatus.FINALIZED
        )
        PrescriptionMedicine.objects.create(
            prescription=rx,
            medicine_name='Amlodipine',
            strength='5 mg',
            dosage='1 Tablet',
            frequency='0-0-1',
            duration='30 Days'
        )
        pdf_bytes = generate_prescription_pdf(rx)
        self.assertTrue(isinstance(pdf_bytes, bytes))
        self.assertTrue(len(pdf_bytes) > 500)
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))

    def test_idor_protection_patient_access(self):
        rx = Prescription.objects.create(
            patient=self.patient_user,
            doctor=self.doctor,
            appointment=self.appointment,
            diagnosis='Migraine',
            prescription_status=PrescriptionStatus.FINALIZED
        )

        # Log in as other patient
        self.client.login(username='other_rx', password='Password123!')

        # Attempt viewing other patient's prescription -> Redirected/Denied
        res = self.client.get(f'/prescriptions/{rx.id}/')
        self.assertEqual(res.status_code, 302)

        # Log in as correct patient owner -> Success (200)
        self.client.login(username='patient_rx', password='Password123!')
        res_owner = self.client.get(f'/prescriptions/{rx.id}/')
        self.assertEqual(res_owner.status_code, 200)
        self.assertContains(res_owner, 'Migraine')
