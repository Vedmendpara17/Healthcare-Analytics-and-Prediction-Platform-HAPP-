from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.admin_dashboard_view, name='admin_dashboard'),
    path('doctors/', views.manage_doctors_view, name='manage_doctors'),
    path('doctors/<int:doctor_id>/approve/', views.approve_doctor_view, name='approve_doctor'),
    path('doctors/<int:doctor_id>/toggle-status/', views.toggle_doctor_status_view, name='toggle_doctor_status'),
    path('patients/', views.manage_patients_view, name='manage_patients'),
    path('patients/<int:patient_id>/', views.view_patient_detail_view, name='admin_patient_detail'),
    path('appointments/', views.manage_appointments_view, name='manage_appointments'),
    path('specializations/', views.manage_specializations_view, name='manage_specializations'),
    path('analytics/', views.admin_analytics_view, name='admin_analytics'),
    path('export/appointments/csv/', views.export_appointments_csv_view, name='export_appointments_csv'),
    path('broadcast/', views.broadcast_announcement_view, name='broadcast_announcement'),
    path('reports/', views.admin_medical_reports_view, name='admin_medical_reports'),
    path('reports/<int:report_id>/delete/', views.admin_delete_medical_report_view, name='admin_delete_medical_report'),
    path('security/', views.admin_security_dashboard_view, name='admin_security_dashboard'),
]
