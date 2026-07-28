import os
import sys
from pathlib import Path
import django

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from doctors.models import DoctorProfile
from appointments.models import Appointment
from payments.models import Payment, Invoice, Refund
from payments.utils import generate_payment_id, generate_transaction_id, generate_invoice_number
from payments.pdf_generator import generate_invoice_pdf

User = get_user_model()

def test_payment_system():
    print("Beginning Payment System Test Suite...")
    
    patient = User.objects.filter(role='PATIENT').first()
    doctor_profile = DoctorProfile.objects.filter(is_approved=True).first()

    if not patient or not doctor_profile:
        print("ERROR: Patient or Doctor profile missing for test.")
        return

    # Create dummy appointment
    appt = Appointment.objects.create(
        patient=patient,
        doctor=doctor_profile,
        date=date.today(),
        time_slot='10:00',
        reason="Routine Payment Test Verification",
        status=Appointment.Status.PENDING
    )
    print(f"Created Test Appointment ID #{appt.id}")

    # Create Payment
    pay_id = generate_payment_id()
    txn_id = generate_transaction_id()
    inv_num = generate_invoice_number()

    payment = Payment.objects.create(
        payment_id=pay_id,
        transaction_id=txn_id,
        patient=patient,
        doctor=doctor_profile,
        appointment=appt,
        amount=doctor_profile.consultation_fee,
        platform_fee=Decimal('5.00'),
        tax=Decimal('2.75'),
        discount=Decimal('0.00'),
        total_amount=doctor_profile.consultation_fee + Decimal('7.75'),
        payment_method=Payment.PaymentMethod.CREDIT_CARD,
        payment_status=Payment.PaymentStatus.PAID,
        masked_payment_reference="**** **** **** 4523",
        invoice_number=inv_num
    )
    print(f"Created Payment {payment.payment_id} | Invoice #{payment.invoice_number}")

    # Generate Invoice PDF
    pdf_path = generate_invoice_pdf(payment)
    print(f"PDF Invoice generated at: {pdf_path}")
    assert os.path.exists(pdf_path), "PDF invoice file was not created!"
    print("SUCCESS: PDF Invoice verification passed.")

    # Clean up test records
    payment.delete()
    appt.delete()
    print("Cleaned up test records.")

if __name__ == '__main__':
    test_payment_system()
