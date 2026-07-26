from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.patient_dashboard_view, name='patient_dashboard'),
    path('doctors/', views.doctor_directory_view, name='doctor_directory'),
    path('risk-history/', views.patient_risk_history_view, name='patient_risk_history'),
    path('prescriptions/', views.patient_prescriptions_view, name='patient_prescriptions'),
    path('medical-reports/', views.medical_reports_list_view, name='patient_medical_reports'),
    path('medical-reports/<int:report_id>/preview/', views.preview_medical_report_view, name='preview_medical_report'),
    path('medical-reports/<int:report_id>/download/', views.download_medical_report_view, name='download_medical_report'),
    path('medical-reports/<int:report_id>/delete/', views.delete_patient_medical_report_view, name='delete_patient_medical_report'),
    path('profile/edit/', views.edit_patient_profile_view, name='edit_patient_profile'),
]
