from django.urls import path
from . import views

urlpatterns = [
    path('assess/new/', views.create_risk_assessment_view, name='create_risk_assessment'),
    path('assess/new/<int:patient_id>/', views.create_risk_assessment_view, name='create_risk_assessment_patient'),
    path('assess/<int:assessment_id>/', views.assessment_detail_view, name='assessment_detail'),
    path('assess/<int:assessment_id>/pdf/', views.export_assessment_pdf_view, name='export_assessment_pdf'),
]
