from django.urls import path
from . import views

urlpatterns = [
    path('book/', views.book_appointment_view, name='book_appointment'),
    path('book/<int:doctor_id>/', views.book_appointment_view, name='book_appointment_doctor'),
    path('my-appointments/', views.patient_appointments_list_view, name='patient_appointments_list'),
    path('<int:appointment_id>/cancel/', views.cancel_appointment_view, name='cancel_appointment'),
    path('<int:appointment_id>/reschedule/', views.reschedule_appointment_view, name='reschedule_appointment'),
    path('api/available-slots/', views.available_slots_api, name='available_slots_api'),
    path('api/calendar-events/', views.calendar_events_api, name='calendar_events_api'),
]
