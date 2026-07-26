import os
import uuid
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
import datetime

def validate_media_document(value):
    ext = value.name.split('.')[-1].lower()
    valid_extensions = ['pdf', 'jpg', 'jpeg', 'png']
    if ext not in valid_extensions:
        raise ValidationError("File type not supported. Allowed formats: PDF, JPG, JPEG, PNG.")
    if value.size > 5 * 1024 * 1024:
        raise ValidationError("File size must not exceed 5MB.")

def validate_report_file(value):
    if not value:
        raise ValidationError("File is required.")
    ext = value.name.split('.')[-1].lower()
    allowed_exts = ['pdf', 'jpg', 'jpeg', 'png']
    rejected_exts = ['exe', 'bat', 'php', 'js', 'zip', 'rar', 'sh', 'cmd', 'vbs', 'jar', 'py']
    
    if ext in rejected_exts or ext not in allowed_exts:
        raise ValidationError("Invalid file type. Only PDF, JPG, JPEG, and PNG files are permitted.")

    if value.size > 10 * 1024 * 1024:
        raise ValidationError("File size exceeds maximum limit of 10 MB.")

    if value.size <= 0:
        raise ValidationError("Uploaded file is empty or corrupted.")

    # MIME type validation if content_type is available
    content_type = getattr(value, 'content_type', '').lower()
    if content_type:
        allowed_mimes = ['application/pdf', 'image/jpeg', 'image/jpg', 'image/png']
        if content_type not in allowed_mimes and not any(m in content_type for m in ['pdf', 'jpeg', 'jpg', 'png']):
            raise ValidationError("File MIME type mismatch. Only valid PDF and image documents are accepted.")

def medical_report_upload_path(instance, filename):
    ext = filename.split('.')[-1].lower()
    unique_filename = f"{uuid.uuid4().hex}.{ext}"
    patient_id = instance.patient_id if instance.patient_id else 'general'
    return os.path.join('medical_reports', f"patient_{patient_id}", unique_filename)


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


class MedicalReport(models.Model):
    REPORT_CATEGORIES = [
        ('Blood Test', 'Blood Test'),
        ('X-Ray', 'X-Ray'),
        ('MRI', 'MRI'),
        ('CT Scan', 'CT Scan'),
        ('ECG', 'ECG'),
        ('Ultrasound', 'Ultrasound'),
        ('Prescription', 'Prescription'),
        ('Lab Report', 'Lab Report'),
        ('Vaccination Record', 'Vaccination Record'),
        ('Discharge Summary', 'Discharge Summary'),
        ('Other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('PENDING', 'Pending Review'),
        ('REVIEWED', 'Reviewed'),
    ]

    patient = models.ForeignKey(PatientProfile, on_delete=models.CASCADE, related_name='medical_reports_v2')
    doctor = models.ForeignKey('doctors.DoctorProfile', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_medical_reports')
    appointment = models.ForeignKey('appointments.Appointment', on_delete=models.SET_NULL, null=True, blank=True, related_name='medical_reports')
    
    report_name = models.CharField(max_length=100)
    report_category = models.CharField(max_length=30, choices=REPORT_CATEGORIES)
    description = models.TextField(max_length=500, blank=True, null=True)
    file = models.FileField(upload_to=medical_report_upload_path, validators=[validate_report_file])
    file_size = models.BigIntegerField(default=0, help_text="File size in bytes")
    file_type = models.CharField(max_length=50, help_text="MIME type or file extension")
    
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    review_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    doctor_notes = models.TextField(blank=True, null=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    
    is_deleted = models.BooleanField(default=False)
    created_ip = models.GenericIPAddressField(blank=True, null=True)
    last_accessed = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-uploaded_at']

    @property
    def formatted_size(self):
        if self.file_size < 1024:
            return f"{self.file_size} B"
        elif self.file_size < 1024 * 1024:
            return f"{round(self.file_size / 1024, 1)} KB"
        else:
            return f"{round(self.file_size / (1024 * 1024), 2)} MB"

    @property
    def is_pdf(self):
        return self.file_type.lower() == 'application/pdf' or self.file.name.endswith('.pdf')

    @property
    def is_image(self):
        return self.file_type.startswith('image/') or any(self.file.name.endswith(ext) for ext in ['.jpg', '.jpeg', '.png'])

    def __str__(self):
        return f"{self.report_name} - {self.report_category} ({self.patient})"

