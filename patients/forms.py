from django import forms
from .models import MedicalReport
from appointments.models import Appointment

class MedicalReportForm(forms.ModelForm):
    report_name = forms.CharField(
        max_length=100,
        min_length=3,
        required=True,
        widget=forms.TextInput(attrs={
            'placeholder': 'Report Title (e.g. Annual Blood Work 2026)',
            'class': 'form-control rounded-3'
        }),
        help_text="Provide a clear descriptive title (3 to 100 characters)."
    )
    report_category = forms.ChoiceField(
        choices=MedicalReport.REPORT_CATEGORIES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select rounded-3'})
    )
    description = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Optional details or notes regarding this diagnostic report...',
            'class': 'form-control rounded-3'
        })
    )
    appointment = forms.ModelChoiceField(
        queryset=Appointment.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select rounded-3'}),
        help_text="Optionally link this report to a scheduled appointment."
    )
    file = forms.FileField(
        required=True,
        widget=forms.FileInput(attrs={
            'class': 'form-control rounded-3',
            'accept': '.pdf,.jpg,.jpeg,.png'
        }),
        help_text="Allowed formats: PDF, JPG, JPEG, PNG (Max 10 MB)."
    )

    class Meta:
        model = MedicalReport
        fields = ['report_name', 'report_category', 'description', 'appointment', 'file']

    def __init__(self, *args, **kwargs):
        patient_user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if patient_user and hasattr(patient_user, 'patient_appointments'):
            self.fields['appointment'].queryset = Appointment.objects.filter(
                patient=patient_user
            ).select_related('doctor', 'doctor__user')
            self.fields['appointment'].label_from_instance = lambda obj: f"Dr. {obj.doctor.user.get_full_name() or obj.doctor.user.username} ({obj.date})"
