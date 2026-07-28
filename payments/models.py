from django.db import models
from django.conf import settings
import uuid
import datetime

class Payment(models.Model):
    class PaymentMethod(models.TextChoices):
        UPI = 'UPI', 'UPI Payment'
        CREDIT_CARD = 'CREDIT_CARD', 'Credit Card'
        DEBIT_CARD = 'DEBIT_CARD', 'Debit Card'
        NET_BANKING = 'NET_BANKING', 'Net Banking'
        DIGITAL_WALLET = 'DIGITAL_WALLET', 'Digital Wallet'
        CASH = 'CASH', 'Cash at Hospital'

    class PaymentStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        PROCESSING = 'PROCESSING', 'Processing'
        PAID = 'PAID', 'Paid'
        FAILED = 'FAILED', 'Failed'
        CANCELLED = 'CANCELLED', 'Cancelled'
        REFUNDED = 'REFUNDED', 'Refunded'

    payment_id = models.CharField(max_length=50, unique=True)
    transaction_id = models.CharField(max_length=50, unique=True)
    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payments')
    doctor = models.ForeignKey('doctors.DoctorProfile', on_delete=models.CASCADE, related_name='payments_received')
    appointment = models.OneToOneField('appointments.Appointment', on_delete=models.CASCADE, related_name='payment')
    
    amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Consultation fee")
    platform_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    payment_method = models.CharField(max_length=30, choices=PaymentMethod.choices)
    card_type = models.CharField(max_length=30, blank=True, null=True, help_text="e.g. Visa, Mastercard, RuPay, American Express")
    last_four_digits = models.CharField(max_length=4, blank=True, null=True, help_text="Last 4 digits of card number")
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    masked_payment_reference = models.CharField(max_length=100, blank=True, null=True, help_text="e.g. **** **** **** 4523 or user@upi")
    
    invoice_number = models.CharField(max_length=50, unique=True)
    invoice_pdf = models.FileField(upload_to='invoices/', blank=True, null=True)
    payment_date = models.DateTimeField(blank=True, null=True)
    remarks = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.payment_id} - {self.patient.get_full_name()} - {self.total_amount} ({self.payment_status})"


class Invoice(models.Model):
    invoice_number = models.CharField(max_length=50, unique=True)
    payment = models.OneToOneField(Payment, on_delete=models.CASCADE, related_name='invoice_record')
    invoice_file = models.FileField(upload_to='invoices/')
    generated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Invoice {self.invoice_number} for {self.payment.payment_id}"


class Refund(models.Model):
    class RefundStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        APPROVED = 'APPROVED', 'Approved'
        COMPLETED = 'COMPLETED', 'Completed'
        REJECTED = 'REJECTED', 'Rejected'

    refund_id = models.CharField(max_length=50, unique=True)
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='refunds')
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2)
    refund_reason = models.TextField()
    refund_status = models.CharField(max_length=20, choices=RefundStatus.choices, default=RefundStatus.PENDING)
    processed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='processed_refunds')
    processed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Refund {self.refund_id} ({self.refund_amount}) - {self.refund_status}"
