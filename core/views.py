from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required

from doctors.models import DoctorProfile
from appointments.models import Specialization
from core.models import Notification, Review, AuditLog

def home_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard_redirect')

    specializations = Specialization.objects.all()[:6]
    featured_doctors = DoctorProfile.objects.filter(is_approved=True).select_related('user', 'specialization')[:4]
    
    return render(request, 'core/home.html', {
        'specializations': specializations,
        'featured_doctors': featured_doctors,
    })

@login_required
def mark_notification_read_view(request, notif_id):
    notif = get_object_or_404(Notification, id=notif_id, user=request.user)
    notif.is_read = True
    notif.save()
    return JsonResponse({'status': 'ok'})

@login_required
def submit_review_view(request, doctor_id):
    if not request.user.is_patient():
        messages.error(request, "Only patients can submit doctor reviews.")
        return redirect('dashboard_redirect')

    doctor = get_object_or_404(DoctorProfile, id=doctor_id)
    patient = request.user.patient_profile

    if request.method == 'POST':
        rating = int(request.POST.get('rating', 5))
        comment = request.POST.get('comment', '').strip()

        if comment:
            Review.objects.create(
                doctor=doctor,
                patient=patient,
                rating=rating,
                comment=comment
            )
            messages.success(request, f"Thank you! Your review for Dr. {doctor.user.get_full_name()} was submitted.")

    return redirect('doctor_directory')
