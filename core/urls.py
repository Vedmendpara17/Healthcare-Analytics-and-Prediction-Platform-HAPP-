from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('notifications/<int:notif_id>/read/', views.mark_notification_read_view, name='mark_notification_read'),
    path('doctors/<int:doctor_id>/review/', views.submit_review_view, name='submit_review'),
]
