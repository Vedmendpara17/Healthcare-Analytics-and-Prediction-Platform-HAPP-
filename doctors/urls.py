from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.doctor_dashboard_view, name='doctor_dashboard'),
    path('patients/', views.doctor_patient_list_view, name='doctor_patient_list'),
    path('patients/<int:patient_id>/', views.doctor_patient_detail_view, name='doctor_patient_detail'),
    path('appointments/<int:appointment_id>/status/', views.update_appointment_status_view, name='update_appointment_status'),
    path('appointments/<int:appointment_id>/prescription/', views.add_prescription_view, name='add_prescription'),
    path('schedule/', views.manage_schedule_view, name='manage_schedule'),
    path('schedule/<int:slot_id>/delete/', views.delete_availability_view, name='delete_availability'),
    path('profile/edit/', views.edit_doctor_profile_view, name='edit_doctor_profile'),
]
