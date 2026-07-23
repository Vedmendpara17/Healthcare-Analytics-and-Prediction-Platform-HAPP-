from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.patient_dashboard_view, name='patient_dashboard'),
    path('doctors/', views.doctor_directory_view, name='doctor_directory'),
    path('risk-history/', views.patient_risk_history_view, name='patient_risk_history'),
    path('prescriptions/', views.patient_prescriptions_view, name='patient_prescriptions'),
    path('records/', views.medical_records_vault_view, name='medical_records_vault'),
    path('records/<int:record_id>/delete/', views.delete_medical_record_view, name='delete_medical_record'),
    path('profile/edit/', views.edit_patient_profile_view, name='edit_patient_profile'),
]
