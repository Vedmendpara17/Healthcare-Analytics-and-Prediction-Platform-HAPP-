from django.db import models
from django.conf import settings
from django.core.validators import FileExtensionValidator, MinValueValidator, MaxValueValidator

def validate_image_file(value):
    ext = value.name.split('.')[-1].lower()
    valid_extensions = ['jpg', 'jpeg', 'png']
    if ext not in valid_extensions:
        raise models.ValidationError("Only .jpg, .jpeg, and .png image files are allowed.")
    if value.size > 5 * 1024 * 1024:
        raise models.ValidationError("Image file size must not exceed 5MB.")

class DoctorProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='doctor_profile')
    specialization = models.ForeignKey('appointments.Specialization', on_delete=models.SET_NULL, null=True, related_name='doctors')
    license_number = models.CharField(max_length=50, unique=True, help_text="Medical License Number")
    qualification = models.CharField(max_length=150, help_text="e.g. MBBS, MD (Cardiology)")
    experience_years = models.PositiveIntegerField(default=0, validators=[MaxValueValidator(70)])
    hospital_name = models.CharField(max_length=150, help_text="Hospital or Clinic Name")
    consultation_fee = models.DecimalField(max_digits=8, decimal_places=2, default=50.00)
    profile_photo = models.ImageField(upload_to='doctors/photos/', blank=True, null=True, validators=[validate_image_file])
    is_approved = models.BooleanField(default=False, help_text="Approved by system admin for login")
    bio = models.TextField(blank=True, null=True, help_text="Short professional summary")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Dr. {self.user.get_full_name() or self.user.username} ({self.specialization.name if self.specialization else 'General'})"

class DoctorAvailability(models.Model):
    WEEKDAYS = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]

    doctor = models.ForeignKey(DoctorProfile, on_delete=models.CASCADE, related_name='availabilities')
    weekday = models.IntegerField(choices=WEEKDAYS)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        verbose_name_plural = "Doctor Availabilities"
        unique_together = ['doctor', 'weekday', 'start_time']

    def __str__(self):
        return f"{self.doctor} - {self.get_weekday_display()} ({self.start_time} - {self.end_time})"
