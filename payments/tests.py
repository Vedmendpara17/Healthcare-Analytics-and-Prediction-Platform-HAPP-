from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
import datetime

from doctors.models import DoctorProfile
from appointments.models import Appointment, Specialization
from payments.models import Payment, Invoice, Refund
from payments.utils import generate_payment_id, generate_transaction_id, generate_invoice_number

User = get_user_model()

class PaymentSystemTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.patient = User.objects.create_user(
            username='patient_test',
            email='patient@test.com',
            password='Password123!',
            role='PATIENT',
            first_name='John',
            last_name='Doe'
        )
        self.doctor_user = User.objects.create_user(
            username='doctor_test',
            email='doctor@test.com',
            password='Password123!',
            role='DOCTOR',
            first_name='Sarah',
            last_name='Smith'
        )
        self.spec = Specialization.objects.create(name='Cardiology')
        self.doctor_profile = DoctorProfile.objects.create(
            user=self.doctor_user,
            specialization=self.spec,
            license_number='LIC12345',
            qualification='MBBS, MD',
            hospital_name='HAPP Heart Clinic',
            consultation_fee=Decimal('150.00'),
            is_approved=True
        )
        self.appointment = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor_profile,
            date=datetime.date.today() + datetime.timedelta(days=1),
            time_slot='10:00',
            reason='Cardiology Checkup',
            status=Appointment.Status.PENDING
        )

    def test_payment_id_generators(self):
        pay_id = generate_payment_id()
        txn_id = generate_transaction_id()
        inv_num = generate_invoice_number()
        
        self.assertTrue(pay_id.startswith("PAY-"))
        self.assertTrue(txn_id.startswith("TXN-"))
        self.assertTrue(inv_num.startswith("INV-"))

    def test_payment_creation_and_invoice(self):
        payment = Payment.objects.create(
            payment_id=generate_payment_id(),
            transaction_id=generate_transaction_id(),
            patient=self.patient,
            doctor=self.doctor_profile,
            appointment=self.appointment,
            amount=self.doctor_profile.consultation_fee,
            platform_fee=Decimal('5.00'),
            tax=Decimal('7.75'),
            discount=Decimal('0.00'),
            total_amount=Decimal('162.75'),
            payment_method=Payment.PaymentMethod.CREDIT_CARD,
            payment_status=Payment.PaymentStatus.PAID,
            masked_payment_reference='**** **** **** 1234',
            invoice_number=generate_invoice_number(),
            payment_date=timezone.now()
        )
        self.assertEqual(payment.payment_status, Payment.PaymentStatus.PAID)
        self.assertEqual(payment.total_amount, Decimal('162.75'))

    def test_checkout_and_process_payment_view(self):
        self.client.login(username='patient_test', password='Password123!')
        
        # Test checkout GET
        response = self.client.get(f'/payments/checkout/{self.appointment.id}/')
        self.assertEqual(response.status_code, 200)

        # Test process payment POST (Card)
        post_data = {
            'payment_method': 'CREDIT_CARD',
            'card_holder': 'Rahul Sharma',
            'card_number': '4111 1111 1111 1111',
            'expiry_date': '12/29',
            'cvv': '123',
            'simulation_outcome': 'SUCCESS'
        }
        resp_process = self.client.post(f'/payments/process/{self.appointment.id}/', post_data, follow=True)
        self.assertEqual(resp_process.status_code, 200)

        # Verify payment & appointment updated
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.APPROVED)
        payment_record = Payment.objects.get(appointment=self.appointment)
        self.assertEqual(payment_record.payment_status, Payment.PaymentStatus.PAID)
        self.assertEqual(payment_record.card_type, 'Visa')
        self.assertEqual(payment_record.last_four_digits, '1111')
