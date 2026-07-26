from django.contrib import admin
from prescriptions.models import Prescription, PrescriptionMedicine

class PrescriptionMedicineInline(admin.TabularInline):
    model = PrescriptionMedicine
    extra = 0

@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = ('prescription_number', 'patient', 'doctor', 'diagnosis', 'prescription_status', 'created_at')
    list_filter = ('prescription_status', 'created_at', 'doctor')
    search_fields = ('prescription_number', 'patient__username', 'patient__first_name', 'patient__last_name', 'doctor__user__username', 'diagnosis')
    inlines = [PrescriptionMedicineInline]
    readonly_fields = ('prescription_number', 'created_at', 'updated_at')

@admin.register(PrescriptionMedicine)
class PrescriptionMedicineAdmin(admin.ModelAdmin):
    list_display = ('medicine_name', 'prescription', 'strength', 'dosage', 'frequency', 'duration', 'meal_instruction')
    search_fields = ('medicine_name', 'prescription__prescription_number')
