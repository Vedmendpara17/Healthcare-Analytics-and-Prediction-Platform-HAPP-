from django.urls import path
from backups import views

urlpatterns = [
    path('', views.admin_backup_dashboard_view, name='admin_backup_dashboard'),
    path('create/', views.create_manual_backup_view, name='create_manual_backup'),
    path('<int:backup_id>/download/', views.download_backup_view, name='download_backup'),
    path('<int:backup_id>/verify/', views.verify_backup_view, name='verify_backup'),
    path('<int:backup_id>/restore/', views.restore_backup_view, name='restore_backup'),
    path('<int:backup_id>/delete/', views.delete_backup_view, name='delete_backup'),
    path('settings/', views.backup_settings_view, name='backup_settings'),
]
