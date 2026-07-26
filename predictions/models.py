from django.db import models
from django.conf import settings

class RiskAssessment(models.Model):
    LEVEL_CHOICES = [
        ('LOW', 'Low Risk'),
        ('MEDIUM', 'Medium Risk'),
        ('HIGH', 'High Risk'),
    ]

    patient = models.ForeignKey('patients.PatientProfile', on_delete=models.CASCADE, related_name='risk_assessments')
    doctor = models.ForeignKey('doctors.DoctorProfile', on_delete=models.SET_NULL, null=True, related_name='authored_assessments')
    appointment = models.ForeignKey('appointments.Appointment', on_delete=models.SET_NULL, null=True, blank=True, related_name='assessments')

    # Input parameters
    age = models.IntegerField(default=30)
    gender = models.CharField(max_length=15, default='Male')
    systolic_bp = models.IntegerField(default=120, help_text="mmHg")
    diastolic_bp = models.IntegerField(default=80, help_text="mmHg")
    heart_rate = models.IntegerField(default=72, null=True, blank=True, help_text="BPM")
    body_temperature = models.FloatField(default=36.6, null=True, blank=True, help_text="°C")
    spo2_percentage = models.FloatField(default=98.0, null=True, blank=True, help_text="%")
    fasting_sugar = models.FloatField(default=90.0, help_text="mg/dL")
    postprandial_sugar = models.FloatField(default=120.0, help_text="mg/dL")
    total_cholesterol = models.FloatField(default=180.0, help_text="mg/dL")
    hdl_cholesterol = models.FloatField(default=50.0, help_text="mg/dL")
    ldl_cholesterol = models.FloatField(default=100.0, help_text="mg/dL")
    height_cm = models.FloatField(default=170.0)
    weight_kg = models.FloatField(default=70.0)
    bmi = models.FloatField(default=24.2)
    smoking_status = models.CharField(max_length=20, default='never')
    alcohol_consumption = models.CharField(max_length=20, default='none')
    physical_activity = models.CharField(max_length=20, default='moderate')
    family_history_text = models.TextField(blank=True, null=True, help_text="Comma-separated list e.g. Diabetes, Heart Disease")
    chronic_conditions_text = models.TextField(blank=True, null=True)
    symptoms_text = models.TextField(blank=True, null=True)

    # Computed prediction outcomes
    computed_score = models.IntegerField(default=0, help_text="Risk score between 0 and 100")
    computed_level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default='LOW')
    heart_score = models.IntegerField(default=0)
    diabetes_score = models.IntegerField(default=0)
    hypertension_score = models.IntegerField(default=0)
    precautions_json = models.TextField(blank=True, null=True, help_text="JSON string of precautions")

    # Doctor override & clinical observations
    doctor_override_level = models.CharField(max_length=10, choices=LEVEL_CHOICES, blank=True, null=True)
    doctor_notes = models.TextField(blank=True, null=True, help_text="Doctor's custom clinical impression and orders")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def final_level(self):
        return self.doctor_override_level or self.computed_level

    def __str__(self):
        return f"Assessment for {self.patient} on {self.created_at.strftime('%Y-%m-%d')} - {self.final_level}"
