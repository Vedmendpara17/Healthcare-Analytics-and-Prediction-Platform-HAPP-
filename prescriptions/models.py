import uuid
import datetime
from django.db import models
from django.conf import settings
from django.utils import timezone

def generate_prescription_number():
    date_str = datetime.date.today().strftime('%Y%m%d')
    random_str = str(uuid.uuid4())[:4].upper()
    return f"RX-{date_str}-{random_str}"

class PrescriptionStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    FINALIZED = 'FINALIZED', 'Finalized'

class MedicineType(models.TextChoices):
    TABLET = 'Tablet', 'Tablet'
    CAPSULE = 'Capsule', 'Capsule'
    SYRUP = 'Syrup', 'Syrup'
    INJECTION = 'Injection', 'Injection'
    OINTMENT = 'Ointment', 'Ointment'
    DROPS = 'Drops', 'Drops'
    INHALER = 'Inhaler', 'Inhaler'
    OTHER = 'Other', 'Other'

class MealInstruction(models.TextChoices):
    AFTER_FOOD = 'After Food', 'After Food'
    BEFORE_FOOD = 'Before Food', 'Before Food'
    WITH_FOOD = 'With Food', 'With Food'
    AS_NEEDED = 'As Needed', 'As Needed'

class Prescription(models.Model):
    prescription_number = models.CharField(max_length=50, unique=True, default=generate_prescription_number)
    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='eprescriptions')
    doctor = models.ForeignKey('doctors.DoctorProfile', on_delete=models.CASCADE, related_name='eprescriptions')
    appointment = models.ForeignKey('appointments.Appointment', on_delete=models.SET_NULL, null=True, blank=True, related_name='eprescriptions')

    diagnosis = models.CharField(max_length=500, help_text="Primary clinical diagnosis (Max 500 characters)")
    symptoms = models.TextField(blank=True, null=True, help_text="Presenting clinical symptoms")
    clinical_notes = models.TextField(blank=True, null=True, help_text="Clinical observations, dietary advice, or general instructions")
    follow_up_date = models.DateField(blank=True, null=True, help_text="Recommended follow-up consultation date")
    doctor_signature = models.ImageField(upload_to='prescriptions/signatures/', blank=True, null=True)
    prescription_status = models.CharField(max_length=20, choices=PrescriptionStatus.choices, default=PrescriptionStatus.FINALIZED)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_prescriptions')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='updated_prescriptions')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.prescription_number} - {self.patient.get_full_name()} (Dr. {self.doctor.user.get_full_name()})"


class PrescriptionMedicine(models.Model):
    prescription = models.ForeignKey(Prescription, on_delete=models.CASCADE, related_name='medicines')
    medicine_name = models.CharField(max_length=200, help_text="Name of medicine e.g. Paracetamol")
    medicine_type = models.CharField(max_length=50, choices=MedicineType.choices, default=MedicineType.TABLET)
    strength = models.CharField(max_length=50, default='500 mg', help_text="e.g. 500 mg, 10 ml")
    dosage = models.CharField(max_length=100, default='1 Tablet', help_text="e.g. 1 Tablet, 5 ml")
    frequency = models.CharField(max_length=100, default='1-0-1 (Morning + Night)')
    morning = models.BooleanField(default=True)
    afternoon = models.BooleanField(default=False)
    night = models.BooleanField(default=True)
    duration = models.CharField(max_length=50, default='5 Days', help_text="e.g. 5 Days, 2 Weeks")
    meal_instruction = models.CharField(max_length=50, choices=MealInstruction.choices, default=MealInstruction.AFTER_FOOD)
    quantity = models.CharField(max_length=50, default='10', help_text="Total units e.g. 10 Tablets")
    notes = models.TextField(blank=True, null=True, help_text="Special instructions e.g. Take with warm water")

    def __str__(self):
        return f"{self.medicine_name} ({self.strength}) - {self.prescription.prescription_number}"
