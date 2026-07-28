from django.urls import path
from . import views

urlpatterns = [
    path('checkout/<int:appointment_id>/', views.checkout_view, name='checkout'),
    path('process/<int:appointment_id>/', views.process_payment_view, name='process_payment'),
    path('success/<str:payment_id>/', views.payment_success_view, name='payment_success'),
    path('my-payments/', views.patient_payments_list_view, name='patient_payments'),
    path('invoice/<str:invoice_number>/download/', views.download_invoice_view, name='download_invoice'),
    path('admin/analytics/', views.admin_payment_analytics_view, name='admin_payment_analytics'),
    path('admin/refund/<str:payment_id>/', views.process_refund_view, name='process_refund'),
]
