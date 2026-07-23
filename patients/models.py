from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
import datetime

def validate_media_document(value):
    ext = value.name.split('.')[-1].lower()
    valid_extensions = ['pdf', 'jpg', 'jpeg', 'png']
    if ext not in valid_extensions:
        raise models.ValidationError("File type not supported. Allowed formats: PDF, JPG, JPEG, PNG.")
    if value.size > 5 * 1024 * 1024:
        raise models.ValidationError("File size must not exceed 5MB.")

class PatientProfile(models.Model):
    GENDER_CHOICES = [
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Other', 'Other'),
    ]

    BLOOD_GROUP_CHOICES = [
        ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'),
        ('O+', 'O+'), ('O-', 'O-'),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='patient_profile')
    dob = models.DateField(null=True, blank=True, help_text="Date of Birth")
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, default='Male')
    blood_group = models.CharField(max_length=5, choices=BLOOD_GROUP_CHOICES, blank=True, null=True)
    height_cm = models.FloatField(default=170.0, validators=[MinValueValidator(30.0), MaxValueValidator(250.0)], help_text="Height in cm")
    weight_kg = models.FloatField(default=70.0, validators=[MinValueValidator(2.0), MaxValueValidator(300.0)], help_text="Weight in kg")
    address = models.TextField(blank=True, null=True)
    emergency_contact_name = models.CharField(max_length=100, blank=True, null=True)
    emergency_contact_phone = models.CharField(max_length=15, blank=True, null=True)
    allergies = models.TextField(blank=True, null=True, help_text="Known allergies e.g. Penicillin")
    chronic_conditions = models.TextField(blank=True, null=True, help_text="Existing conditions e.g. Asthma, Diabetes")
    profile_photo = models.ImageField(upload_to='patients/photos/', blank=True, null=True, validators=[validate_media_document])
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def age(self):
        if not self.dob:
            return 30
        today = datetime.date.today()
        return today.year - self.dob.year - ((today.month, today.day) < (self.dob.month, self.dob.day))

    @property
    def bmi(self):
        if self.height_cm and self.weight_kg and self.height_cm > 0:
            height_m = self.height_cm / 100.0
            return round(self.weight_kg / (height_m * height_m), 1)
        return 0.0

    def __str__(self):
        return f"Patient: {self.user.get_full_name() or self.user.username}"

class MedicalRecord(models.Model):
    RECORD_TYPES = [
        ('LAB', 'Lab Report'),
        ('PRESCRIPTION', 'Prescription'),
        ('SCAN', 'Imaging Scan / X-Ray'),
        ('GENERAL', 'General Medical Document'),
    ]

    patient = models.ForeignKey(PatientProfile, on_delete=models.CASCADE, related_name='medical_records')
    title = models.CharField(max_length=150)
    record_type = models.CharField(max_length=20, choices=RECORD_TYPES, default='LAB')
    file = models.FileField(upload_to='patients/records/', validators=[validate_media_document])
    description = models.TextField(blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.get_record_type_display()}: {self.title} ({self.patient})"
