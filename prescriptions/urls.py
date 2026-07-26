from django.urls import path
from . import views

urlpatterns = [
    path('doctor/', views.doctor_prescription_list_view, name='doctor_prescription_list'),
    path('doctor/create/', views.create_prescription_view, name='create_prescription'),
    path('doctor/create/<int:appointment_id>/', views.create_prescription_view, name='create_prescription_appointment'),
    path('doctor/<int:prescription_id>/edit/', views.edit_prescription_view, name='edit_prescription'),
    path('my-prescriptions/', views.patient_prescription_list_view, name='patient_prescriptions_list'),
    path('analytics/', views.admin_prescriptions_analytics_view, name='admin_prescriptions_analytics'),
    path('export/csv/', views.export_prescriptions_csv_view, name='export_prescriptions_csv'),
    path('<int:prescription_id>/', views.prescription_detail_view, name='prescription_detail'),
    path('<int:prescription_id>/pdf/', views.download_prescription_pdf_view, name='download_prescription_pdf'),
    path('<int:prescription_id>/print/', views.print_prescription_view, name='print_prescription'),
]
