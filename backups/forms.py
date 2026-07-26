from django import forms
from backups.models import BackupScheduleConfig

class BackupScheduleConfigForm(forms.ModelForm):
    class Meta:
        model = BackupScheduleConfig
        fields = ['frequency', 'backup_time', 'retention_days', 'is_enabled']
        widgets = {
            'frequency': forms.Select(attrs={'class': 'form-select rounded-3'}),
            'backup_time': forms.TimeInput(attrs={'class': 'form-control rounded-3', 'type': 'time'}),
            'retention_days': forms.NumberInput(attrs={'class': 'form-control rounded-3', 'min': 1, 'max': 365}),
            'is_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class RestoreConfirmationForm(forms.Form):
    admin_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control form-control-lg rounded-3', 'placeholder': 'Enter your Administrator Password'}),
        label="Super Admin Password",
        required=True
    )
    confirm_checkbox = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="I understand that restoring a backup will replace current application data and media files."
    )
