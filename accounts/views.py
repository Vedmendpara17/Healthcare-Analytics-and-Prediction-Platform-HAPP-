import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction, models
from django.urls import reverse_lazy
from django.utils import timezone

from .forms import PatientRegistrationForm, DoctorRegistrationForm, CustomLoginForm
from .models import User
from .utils import send_account_lockout_email
from patients.models import PatientProfile
from doctors.models import DoctorProfile
from core.models import AuditLog, Notification

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


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
                    chronic_conditions=form.cleaned_data.get('chronic_conditions'),
                )

                AuditLog.objects.create(
                    actor=user,
                    action="PATIENT_REGISTER",
                    details=f"New patient account created for {user.username}",
                    ip_address=get_client_ip(request)
                )

            messages.success(request, "Registration successful! You can now log in with your credentials.")
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
                    is_approved=False
                )

                AuditLog.objects.create(
                    actor=user,
                    action="DOCTOR_REGISTER",
                    details=f"Doctor registration submitted by {user.username} (License: {form.cleaned_data.get('license_number')})",
                    ip_address=get_client_ip(request)
                )

            messages.info(request, "Registration submitted! Admin approval is required before account activation.")
            return redirect('login')
    else:
        form = DoctorRegistrationForm()

    return render(request, 'accounts/register_doctor.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard_redirect')

    if request.method == 'POST':
        username_or_email = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        ip = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')

        # Candidate user lookup (supports both username and email)
        target_user = User.objects.filter(
            models.Q(username__iexact=username_or_email) | models.Q(email__iexact=username_or_email)
        ).first()

        # 1. Lock status MUST be checked before validating password
        if target_user and target_user.is_account_locked():
            rem_display = target_user.get_remaining_lock_display()
            AuditLog.objects.create(
                actor=target_user,
                action="ACCOUNT_LOCKED",
                details=f"Blocked login attempt for locked account ({target_user.username}) from IP {ip}. Remaining: {rem_display}",
                ip_address=ip
            )
            lock_msg = f"Your account is currently locked. Please try again after the remaining lock time expires ({rem_display})." if rem_display else "Your account has been temporarily locked due to multiple failed login attempts. Please try again after 15 minutes or use the Forgot Password option."
            messages.error(request, lock_msg)
            return render(request, 'accounts/login.html', {
                'form': CustomLoginForm(request, data=request.POST),
                'is_locked': True,
                'remaining_seconds': target_user.get_remaining_lock_seconds(),
                'remaining_display': rem_display
            })

        user = authenticate(request, username=username_or_email, password=password)
        if user is None and target_user:
            user = authenticate(request, username=target_user.username, password=password)

        if user is not None:
            if user.is_account_locked():
                rem_display = user.get_remaining_lock_display()
                AuditLog.objects.create(
                    actor=user,
                    action="ACCOUNT_LOCKED",
                    details=f"Blocked login attempt for locked account ({user.username}) from IP {ip}. Remaining: {rem_display}",
                    ip_address=ip
                )
                lock_msg = f"Your account is currently locked. Please try again after the remaining lock time expires ({rem_display})." if rem_display else "Your account has been temporarily locked due to multiple failed login attempts. Please try again after 15 minutes or use the Forgot Password option."
                messages.error(request, lock_msg)
                return render(request, 'accounts/login.html', {
                    'form': CustomLoginForm(request, data=request.POST),
                    'is_locked': True,
                    'remaining_seconds': user.get_remaining_lock_seconds(),
                    'remaining_display': rem_display
                })

            # Gating check for unapproved doctors
            if user.role == User.Role.DOCTOR:
                doc_profile = getattr(user, 'doctor_profile', None)
                if not doc_profile or not doc_profile.is_approved:
                    messages.error(
                        request,
                        "Your Doctor account is pending Admin approval. Access will be enabled once verified."
                    )
                    return render(request, 'accounts/login.html', {'form': CustomLoginForm(request, data=request.POST)})

            # Successful login without OTP
            user.record_successful_login(ip=ip, user_agent=user_agent)
            login(request, user)

            AuditLog.objects.create(
                actor=user,
                action="LOGIN_SUCCESS",
                details=f"User login successful from IP {ip}",
                ip_address=ip
            )

            messages.success(request, f"Welcome back, {user.get_full_name() or user.username}!")
            return redirect('dashboard_redirect')

        else:
            # Generic error message to prevent revealing email existence
            generic_error = "Invalid email or password."
            
            if target_user:
                is_locked, remaining_attempts = target_user.record_failed_login(ip=ip, user_agent=user_agent)
                AuditLog.objects.create(
                    actor=target_user,
                    action="FAILED_LOGIN",
                    details=f"Failed login attempt ({target_user.failed_login_attempts}/5) for user {target_user.username} (Role: {target_user.get_role_display()}) from IP {ip}",
                    ip_address=ip
                )
                if is_locked:
                    send_account_lockout_email(target_user)
                    AuditLog.objects.create(
                        actor=target_user,
                        action="ACCOUNT_LOCKED",
                        details=f"Account locked for 15 minutes after 5 failed attempts from IP {ip}",
                        ip_address=ip
                    )
                    rem_display = target_user.get_remaining_lock_display()
                    messages.error(
                        request,
                        "Your account has been temporarily locked due to multiple failed login attempts. Please try again after 15 minutes or use the Forgot Password option."
                    )
                    return render(request, 'accounts/login.html', {
                        'form': CustomLoginForm(request, data=request.POST),
                        'is_locked': True,
                        'remaining_seconds': target_user.get_remaining_lock_seconds(),
                        'remaining_display': rem_display
                    })
                else:
                    messages.error(request, generic_error)
                    if remaining_attempts == 1:
                        messages.warning(request, "Account will be locked on the next failed attempt.")
                    elif remaining_attempts > 0:
                        messages.info(request, f"You have {remaining_attempts} login attempt{'s' if remaining_attempts > 1 else ''} remaining.")
            else:
                AuditLog.objects.create(
                    actor=None,
                    action="FAILED_LOGIN",
                    details=f"Failed login attempt for unknown user '{username_or_email}' from IP {ip}",
                    ip_address=ip
                )
                messages.error(request, generic_error)

            return render(request, 'accounts/login.html', {'form': CustomLoginForm(request, data=request.POST)})
    else:
        form = CustomLoginForm()

    return render(request, 'accounts/login.html', {'form': form})


@login_required
def logout_view(request):
    user = request.user
    AuditLog.objects.create(
        actor=user,
        action="USER_LOGOUT",
        details="User logged out",
        ip_address=get_client_ip(request)
    )
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
