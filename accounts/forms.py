import re
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from doctors.models import DoctorProfile
from patients.models import PatientProfile
from appointments.models import Specialization

User = get_user_model()

class PatientRegistrationForm(forms.ModelForm):
    first_name = forms.CharField(max_length=30, required=True, widget=forms.TextInput(attrs={'placeholder': 'First Name'}))
    last_name = forms.CharField(max_length=30, required=True, widget=forms.TextInput(attrs={'placeholder': 'Last Name'}))
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'placeholder': 'email@example.com'}))
    phone = forms.CharField(
        max_length=10, 
        min_length=10, 
        required=True, 
        widget=forms.TextInput(attrs={'placeholder': '10-digit number (e.g. 9876543210)'}),
        help_text="10-digit mobile number starting with 6, 7, 8, or 9"
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Create strong password (e.g. Het@1222)'}), 
        required=True,
        help_text="Must contain uppercase & lowercase letters, numbers, and special characters (e.g. Het@1222, Yug#5445)."
    )
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder': 'Confirm password'}), required=True)

    # Patient profile fields
    dob = forms.DateField(required=True, widget=forms.DateInput(attrs={'type': 'date'}))
    gender = forms.ChoiceField(choices=PatientProfile.GENDER_CHOICES, required=True)
    blood_group = forms.ChoiceField(choices=PatientProfile.BLOOD_GROUP_CHOICES, required=False)
    height_cm = forms.FloatField(initial=170.0, min_value=30.0, max_value=250.0, label="Height (cm)")
    weight_kg = forms.FloatField(initial=70.0, min_value=2.0, max_value=300.0, label="Weight (kg)")
    address = forms.CharField(widget=forms.Textarea(attrs={'rows': 2}), required=False)
    emergency_contact_name = forms.CharField(max_length=100, required=False)
    emergency_contact_phone = forms.CharField(
        max_length=10, 
        required=False,
        help_text="Optional 10-digit mobile number starting with 6, 7, 8, or 9"
    )
    allergies = forms.CharField(widget=forms.Textarea(attrs={'rows': 2}), required=False, help_text="e.g. Penicillin, Peanuts")
    chronic_conditions = forms.CharField(widget=forms.Textarea(attrs={'rows': 2}), required=False, help_text="e.g. Asthma, Diabetes")

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'phone']

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("A user with this email address already exists.")
        return email

    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '').strip()
        if not re.match(r'^[6-9]\d{9}$', phone):
            raise ValidationError("Phone number must be a valid 10-digit number starting with 6, 7, 8, or 9.")
        return phone

    def clean_emergency_contact_phone(self):
        phone = self.cleaned_data.get('emergency_contact_phone', '').strip()
        if phone and not re.match(r'^[6-9]\d{9}$', phone):
            raise ValidationError("Emergency contact phone must be a valid 10-digit number starting with 6, 7, 8, or 9.")
        return phone

    def clean_password(self):
        password = self.cleaned_data.get('password')
        if password:
            validate_password(password)
        return password

    def clean(self):
        cleaned_data = super().clean()
        pwd = cleaned_data.get('password')
        cpwd = cleaned_data.get('confirm_password')
        if pwd and cpwd and pwd != cpwd:
            self.add_error('confirm_password', "Passwords do not match.")
        return cleaned_data


class DoctorRegistrationForm(forms.ModelForm):
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    email = forms.EmailField(required=True)
    phone = forms.CharField(
        max_length=10, 
        min_length=10, 
        required=True,
        widget=forms.TextInput(attrs={'placeholder': '10-digit number (e.g. 9876543210)'}),
        help_text="10-digit mobile number starting with 6, 7, 8, or 9"
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Create strong password (e.g. Het@1222)'}), 
        required=True,
        help_text="Must contain uppercase & lowercase letters, numbers, and special characters (e.g. Het@1222, Yug#5445)."
    )
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder': 'Confirm password'}), required=True)

    # Doctor profile fields
    specialization = forms.ModelChoiceField(queryset=Specialization.objects.all(), required=True)
    license_number = forms.CharField(max_length=50, required=True, help_text="Unique Medical License ID")
    qualification = forms.CharField(max_length=150, required=True, help_text="e.g. MBBS, MD Cardiology")
    experience_years = forms.IntegerField(min_value=0, max_value=70, initial=5)
    hospital_name = forms.CharField(max_length=150, required=True)
    consultation_fee = forms.DecimalField(max_digits=8, decimal_places=2, initial=50.00)
    profile_photo = forms.ImageField(required=False)
    bio = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False)

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'phone']

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("A user with this email address already exists.")
        return email

    def clean_license_number(self):
        lic = self.cleaned_data.get('license_number')
        if DoctorProfile.objects.filter(license_number__iexact=lic).exists():
            raise ValidationError("This Medical License Number is already registered.")
        return lic

    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '').strip()
        if not re.match(r'^[6-9]\d{9}$', phone):
            raise ValidationError("Phone number must be a valid 10-digit number starting with 6, 7, 8, or 9.")
        return phone

    def clean_password(self):
        password = self.cleaned_data.get('password')
        if password:
            validate_password(password)
        return password

    def clean(self):
        cleaned_data = super().clean()
        pwd = cleaned_data.get('password')
        cpwd = cleaned_data.get('confirm_password')
        if pwd and cpwd and pwd != cpwd:
            self.add_error('confirm_password', "Passwords do not match.")
        return cleaned_data


class CustomLoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={'placeholder': 'Username or Email', 'class': 'form-control'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder': 'Password', 'class': 'form-control'}))
