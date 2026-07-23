from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction

from .forms import PatientRegistrationForm, DoctorRegistrationForm, CustomLoginForm
from .models import User
from patients.models import PatientProfile
from doctors.models import DoctorProfile
from core.models import AuditLog, Notification

def register_patient_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard_redirect')

    if request.method == 'POST':
        form = PatientRegistrationForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = form.save(commit=False)
                user.set_password(form.cleaned_data['password'])
                user.role = User.Role.PATIENT
                user.save()

                PatientProfile.objects.create(
                    user=user,
                    dob=form.cleaned_data.get('dob'),
                    gender=form.cleaned_data.get('gender'),
                    blood_group=form.cleaned_data.get('blood_group'),
                    height_cm=form.cleaned_data.get('height_cm'),
                    weight_kg=form.cleaned_data.get('weight_kg'),
                    address=form.cleaned_data.get('address'),
                    emergency_contact_name=form.cleaned_data.get('emergency_contact_name'),
                    emergency_contact_phone=form.cleaned_data.get('emergency_contact_phone'),
                    allergies=form.cleaned_data.get('allergies'),
                    chronic_conditions=form.cleaned_data.get('chronic_conditions'),
                )

                AuditLog.objects.create(
                    actor=user,
                    action="PATIENT_REGISTER",
                    details=f"New patient account created for {user.username}"
                )

                Notification.objects.create(
                    user=user,
                    message="Welcome to Healthcare Analytics System! Complete your profile and book appointments.",
                    notif_type="INFO"
                )

            messages.success(request, "Registration successful! You can now log in.")
            return redirect('login')
    else:
        form = PatientRegistrationForm()

    return render(request, 'accounts/register_patient.html', {'form': form})


def register_doctor_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard_redirect')

    if request.method == 'POST':
        form = DoctorRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                user = form.save(commit=False)
                user.set_password(form.cleaned_data['password'])
                user.role = User.Role.DOCTOR
                user.save()

                DoctorProfile.objects.create(
                    user=user,
                    specialization=form.cleaned_data.get('specialization'),
                    license_number=form.cleaned_data.get('license_number'),
                    qualification=form.cleaned_data.get('qualification'),
                    experience_years=form.cleaned_data.get('experience_years'),
                    hospital_name=form.cleaned_data.get('hospital_name'),
                    consultation_fee=form.cleaned_data.get('consultation_fee'),
                    profile_photo=form.cleaned_data.get('profile_photo'),
                    bio=form.cleaned_data.get('bio'),
                    is_approved=False  # Requires admin approval
                )

                AuditLog.objects.create(
                    actor=user,
                    action="DOCTOR_REGISTER",
                    details=f"Doctor registration submitted by {user.username} (License: {form.cleaned_data.get('license_number')})"
                )

            messages.info(request, "Registration submitted! Your doctor account is pending Admin approval before you can log in.")
            return redirect('login')
    else:
        form = DoctorRegistrationForm()

    return render(request, 'accounts/register_doctor.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard_redirect')

    if request.method == 'POST':
        form = CustomLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            
            # Gating check for unapproved doctors
            if user.role == User.Role.DOCTOR:
                doc_profile = getattr(user, 'doctor_profile', None)
                if not doc_profile or not doc_profile.is_approved:
                    messages.error(
                        request,
                        "Your Doctor account is pending Admin approval. Access will be enabled once verified."
                    )
                    return render(request, 'accounts/login.html', {'form': form})

            login(request, user)
            AuditLog.objects.create(
                actor=user,
                action="USER_LOGIN",
                details=f"User logged in from IP {request.META.get('REMOTE_ADDR')}"
            )
            messages.success(request, f"Welcome back, {user.get_full_name() or user.username}!")
            return redirect('dashboard_redirect')
        else:
            messages.error(request, "Invalid username/email or password. Please check your credentials.")
    else:
        form = CustomLoginForm()

    return render(request, 'accounts/login.html', {'form': form})


@login_required
def logout_view(request):
    user = request.user
    AuditLog.objects.create(actor=user, action="USER_LOGOUT", details="User logged out")
    logout(request)
    messages.success(request, "You have been logged out safely.")
    return redirect('login')


@login_required
def dashboard_redirect_view(request):
    if request.user.is_admin():
        return redirect('admin_dashboard')
    elif request.user.is_doctor():
        return redirect('doctor_dashboard')
    elif request.user.is_patient():
        return redirect('patient_dashboard')
    return redirect('login')
