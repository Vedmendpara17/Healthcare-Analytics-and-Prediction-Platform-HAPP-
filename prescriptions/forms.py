import datetime
from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from prescriptions.models import Prescription, PrescriptionMedicine, PrescriptionStatus, MedicineType, MealInstruction
from patients.models import PatientProfile
from appointments.models import Appointment

class PrescriptionForm(forms.ModelForm):
    class Meta:
        model = Prescription
        fields = [
            'appointment', 'diagnosis', 'symptoms', 'clinical_notes',
            'follow_up_date', 'prescription_status'
        ]
        widgets = {
            'diagnosis': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Primary clinical diagnosis e.g. Acute Upper Respiratory Tract Infection...', 'class': 'form-control rounded-3', 'maxlength': 500}),
            'symptoms': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Presenting clinical symptoms e.g. Fever, Cough, Sore Throat...', 'class': 'form-control rounded-3'}),
            'clinical_notes': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Dietary advice, general instructions, precautions...', 'class': 'form-control rounded-3'}),
            'follow_up_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control rounded-3'}),
            'prescription_status': forms.Select(attrs={'class': 'form-select rounded-3'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.initial.get('follow_up_date'):
            self.initial['follow_up_date'] = datetime.date.today() + datetime.timedelta(days=7)
        if not self.initial.get('clinical_notes'):
            self.initial['clinical_notes'] = 'Maintain adequate hydration, get sufficient rest, and take medications strictly as instructed.'

    def clean_diagnosis(self):
        diagnosis = self.cleaned_data.get('diagnosis', '').strip()
        if not diagnosis:
            raise ValidationError("Diagnosis is required.")
        if len(diagnosis) > 500:
            raise ValidationError("Diagnosis cannot exceed 500 characters.")
        return diagnosis

    def clean_follow_up_date(self):
        follow_up_date = self.cleaned_data.get('follow_up_date')
        if follow_up_date and follow_up_date < datetime.date.today():
            raise ValidationError("Follow-up date cannot be in the past.")
        return follow_up_date


class PrescriptionMedicineForm(forms.ModelForm):
    class Meta:
        model = PrescriptionMedicine
        fields = [
            'medicine_name', 'medicine_type', 'strength', 'dosage', 'frequency',
            'morning', 'afternoon', 'night', 'duration', 'meal_instruction', 'quantity', 'notes'
        ]
        widgets = {
            'medicine_name': forms.TextInput(attrs={'placeholder': 'e.g. Paracetamol, Amoxicillin, Ibuprofen', 'class': 'form-control rounded-3 med-name-input'}),
            'medicine_type': forms.Select(attrs={'class': 'form-select rounded-3 med-type-select'}),
            'strength': forms.TextInput(attrs={'placeholder': 'e.g. 500 mg, 10 mL, 250 mg/5mL', 'class': 'form-control rounded-3 med-strength-input'}),
            'dosage': forms.TextInput(attrs={'placeholder': 'e.g. 1 tablet, 5 mL, 2 capsules', 'class': 'form-control rounded-3 med-dosage-input'}),
            'frequency': forms.TextInput(attrs={'placeholder': 'e.g. Twice daily, Every 8 hours, Once after dinner', 'class': 'form-control rounded-3 med-freq-input'}),
            'duration': forms.TextInput(attrs={'placeholder': 'e.g. 5 days, 2 weeks, 1 month', 'class': 'form-control rounded-3 med-duration-input'}),
            'meal_instruction': forms.Select(attrs={'class': 'form-select rounded-3 med-meal-select'}),
            'quantity': forms.TextInput(attrs={'placeholder': 'e.g. 10 tablets, 1 bottle', 'class': 'form-control rounded-3 med-qty-input'}),
            'notes': forms.TextInput(attrs={'placeholder': 'e.g. Take after meals, Take with water, Avoid alcohol', 'class': 'form-control rounded-3 med-notes-input'}),
        }

PrescriptionMedicineFormSet = inlineformset_factory(
    Prescription,
    PrescriptionMedicine,
    form=PrescriptionMedicineForm,
    extra=1,
    can_delete=True
)
