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
from .otp_service import (
    generate_secure_otp, mask_email_address, send_login_otp_email,
    send_email_verification_otp, send_password_reset_otp, send_account_lockout_email
)
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
                user.email_verified = False

                otp = generate_secure_otp()
                user.email_verification_otp = otp
                user.email_verification_expiry = timezone.now() + datetime.timedelta(minutes=5)
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

                send_email_verification_otp(user, otp)

            request.session['pre_2fa_user_id'] = user.id
            messages.info(request, "Registration successful! Please enter the email verification OTP sent to your inbox.")
            return redirect('verify_email_otp')
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
                user.email_verified = False

                otp = generate_secure_otp()
                user.email_verification_otp = otp
                user.email_verification_expiry = timezone.now() + datetime.timedelta(minutes=5)
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

                send_email_verification_otp(user, otp)

            request.session['pre_2fa_user_id'] = user.id
            messages.info(request, "Registration submitted! Please verify your email OTP. (Admin approval is also required before full access).")
            return redirect('verify_email_otp')
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

            # Reset failed attempts counter immediately after successful credentials check
            user.record_successful_login(ip=ip, user_agent=user_agent)

            # Check email verification status
            if not user.email_verified and not user.is_superuser:
                otp = generate_secure_otp()
                user.email_verification_otp = otp
                user.email_verification_expiry = timezone.now() + datetime.timedelta(minutes=5)
                user.save(update_fields=['email_verification_otp', 'email_verification_expiry'])

                send_email_verification_otp(user, otp)
                request.session['pre_2fa_user_id'] = user.id
                messages.warning(request, "Your email address is not verified. A verification code has been sent to your email.")
                return redirect('verify_email_otp')

            # Gating check for unapproved doctors
            if user.role == User.Role.DOCTOR:
                doc_profile = getattr(user, 'doctor_profile', None)
                if not doc_profile or not doc_profile.is_approved:
                    messages.error(
                        request,
                        "Your Doctor account is pending Admin approval. Access will be enabled once verified."
                    )
                    return render(request, 'accounts/login.html', {'form': CustomLoginForm(request, data=request.POST)})

            # Generate 2FA Login OTP
            otp = generate_secure_otp()
            now = timezone.now()
            user.login_otp = otp
            user.login_otp_expiry = now + datetime.timedelta(minutes=5)
            user.otp_attempts = 0
            user.resend_count = 0
            user.save(update_fields=['login_otp', 'login_otp_expiry', 'otp_attempts', 'resend_count'])

            request.session['pre_2fa_user_id'] = user.id
            send_login_otp_email(user, otp)

            AuditLog.objects.create(
                actor=user,
                action="OTP_GENERATED",
                details=f"Generated 2FA login OTP for {user.username} (Role: {user.get_role_display()}) from IP {ip}",
                ip_address=ip
            )

            messages.info(request, f"Credentials verified. A 6-digit OTP code has been sent to {mask_email_address(user.email)}.")
            return redirect('verify_otp')

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


def verify_otp_view(request):
    pre_2fa_user_id = request.session.get('pre_2fa_user_id')
    if not pre_2fa_user_id:
        messages.error(request, "Login session expired. Please log in again.")
        return redirect('login')

    user = get_object_or_404(User, id=pre_2fa_user_id)
    masked_email = mask_email_address(user.email)
    ip = get_client_ip(request)
    now = timezone.now()

    if request.method == 'POST':
        submitted_otp = request.POST.get('otp', '').strip()

        # Check OTP Expiry
        if not user.login_otp or not user.login_otp_expiry or now > user.login_otp_expiry:
            AuditLog.objects.create(
                actor=user,
                action="OTP_EXPIRED",
                details=f"Expired 2FA OTP attempt from IP {ip}",
                ip_address=ip
            )
            messages.error(request, "The OTP code has expired. Please click 'Resend OTP' to receive a new code.")
            return render(request, 'accounts/verify_otp.html', {
                'masked_email': masked_email,
                'expiry_seconds': 0
            })

        # Incorrect OTP
        if submitted_otp != user.login_otp:
            user.otp_attempts += 1
            user.save(update_fields=['otp_attempts'])

            AuditLog.objects.create(
                actor=user,
                action="OTP_FAILED",
                details=f"Incorrect OTP attempt ({user.otp_attempts}/5) from IP {ip}",
                ip_address=ip
            )

            if user.otp_attempts >= 5:
                # Cancel login session & clear OTP
                user.login_otp = None
                user.login_otp_expiry = None
                user.otp_attempts = 0
                user.save(update_fields=['login_otp', 'login_otp_expiry', 'otp_attempts'])

                if 'pre_2fa_user_id' in request.session:
                    del request.session['pre_2fa_user_id']

                messages.error(request, "Too many failed OTP attempts. Your login session has been cancelled. Please log in again.")
                return redirect('login')
            else:
                remaining = 5 - user.otp_attempts
                messages.error(request, f"Invalid OTP code. Remaining attempts: {remaining}.")
                expiry_seconds = max(0, int((user.login_otp_expiry - now).total_seconds()))
                return render(request, 'accounts/verify_otp.html', {
                    'masked_email': masked_email,
                    'expiry_seconds': expiry_seconds
                })

        # Valid OTP
        user.login_otp = None
        user.login_otp_expiry = None
        user.otp_attempts = 0
        user.resend_count = 0
        user.save(update_fields=['login_otp', 'login_otp_expiry', 'otp_attempts', 'resend_count'])
        user.record_successful_login(ip=ip, user_agent=request.META.get('HTTP_USER_AGENT', ''))

        del request.session['pre_2fa_user_id']
        login(request, user)
        request.session.cycle_key()

        AuditLog.objects.create(
            actor=user,
            action="OTP_VERIFIED",
            details=f"2FA OTP verified successfully from IP {ip}",
            ip_address=ip
        )
        AuditLog.objects.create(
            actor=user,
            action="LOGIN_SUCCESS",
            details=f"User 2FA login successful from IP {ip}",
            ip_address=ip
        )

        messages.success(request, f"Welcome back, {user.get_full_name() or user.username}!")
        return redirect('dashboard_redirect')

    expiry_seconds = max(0, int((user.login_otp_expiry - now).total_seconds())) if user.login_otp_expiry else 300
    return render(request, 'accounts/verify_otp.html', {
        'masked_email': masked_email,
        'expiry_seconds': expiry_seconds
    })


def resend_otp_view(request):
    pre_2fa_user_id = request.session.get('pre_2fa_user_id')
    if not pre_2fa_user_id:
        messages.error(request, "Login session expired. Please log in again.")
        return redirect('login')

    user = get_object_or_404(User, id=pre_2fa_user_id)
    now = timezone.now()

    if user.resend_count >= 3:
        messages.error(request, "Maximum OTP resend requests (3) reached. Please log in again.")
        return redirect('login')

    if user.last_resend_time:
        seconds_since = (now - user.last_resend_time).total_seconds()
        if seconds_since < 60:
            rem = int(60 - seconds_since)
            messages.warning(request, f"Please wait {rem} seconds before requesting another OTP.")
            return redirect('verify_otp')

    new_otp = generate_secure_otp()
    user.login_otp = new_otp
    user.login_otp_expiry = now + datetime.timedelta(minutes=5)
    user.resend_count += 1
    user.last_resend_time = now
    user.save(update_fields=['login_otp', 'login_otp_expiry', 'resend_count', 'last_resend_time'])

    send_login_otp_email(user, new_otp)

    AuditLog.objects.create(
        actor=user,
        action="OTP_RESENT",
        details=f"Resent 2FA login OTP ({user.resend_count}/3) to {user.email}",
        ip_address=get_client_ip(request)
    )

    messages.success(request, "A new OTP has been sent to your email.")
    return redirect('verify_otp')


def verify_email_otp_view(request):
    pre_2fa_user_id = request.session.get('pre_2fa_user_id')
    if not pre_2fa_user_id:
        messages.error(request, "Session expired. Please log in.")
        return redirect('login')

    user = get_object_or_404(User, id=pre_2fa_user_id)
    masked_email = mask_email_address(user.email)
    ip = get_client_ip(request)

    if request.method == 'POST':
        submitted_otp = request.POST.get('otp', '').strip()

        if not user.email_verification_otp or not user.email_verification_expiry or timezone.now() > user.email_verification_expiry:
            messages.error(request, "Verification OTP has expired. Please request a new code.")
            return render(request, 'accounts/verify_email_otp.html', {'masked_email': masked_email})

        if submitted_otp == user.email_verification_otp:
            user.email_verified = True
            user.email_verification_otp = None
            user.email_verification_expiry = None
            user.save(update_fields=['email_verified', 'email_verification_otp', 'email_verification_expiry'])

            AuditLog.objects.create(
                actor=user,
                action="EMAIL_VERIFICATION",
                details=f"Email address verified for {user.username}",
                ip_address=ip
            )
            Notification.objects.create(
                user=user,
                message="Your email address has been verified successfully.",
                notif_type="INFO"
            )

            if 'pre_2fa_user_id' in request.session:
                del request.session['pre_2fa_user_id']

            messages.success(request, "Email verified successfully! You can now log in.")
            return redirect('login')
        else:
            messages.error(request, "Invalid email verification code.")

    return render(request, 'accounts/verify_email_otp.html', {'masked_email': masked_email})


def forgot_password_otp_view(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        user = User.objects.filter(email__iexact=email).first()
        if user:
            otp = generate_secure_otp()
            user.password_reset_otp = otp
            user.password_reset_otp_expiry = timezone.now() + datetime.timedelta(minutes=10)
            user.save(update_fields=['password_reset_otp', 'password_reset_otp_expiry'])

            send_password_reset_otp(user, otp)

            AuditLog.objects.create(
                actor=user,
                action="PASSWORD_RESET_REQUEST",
                details=f"Password reset OTP requested for {email}",
                ip_address=get_client_ip(request)
            )

            request.session['reset_user_id'] = user.id
            messages.info(request, "Password reset OTP sent to your registered email.")
            return redirect('reset_password_otp')
        else:
            messages.info(request, "If an account with that email exists, a password reset OTP has been sent.")
            return redirect('login')

    return render(request, 'accounts/forgot_password_otp.html')


def reset_password_otp_view(request):
    reset_user_id = request.session.get('reset_user_id')
    if not reset_user_id:
        messages.error(request, "Session expired. Please request password reset again.")
        return redirect('forgot_password_otp')

    user = get_object_or_404(User, id=reset_user_id)

    if request.method == 'POST':
        submitted_otp = request.POST.get('otp', '').strip()
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')

        if not user.password_reset_otp or not user.password_reset_otp_expiry or timezone.now() > user.password_reset_otp_expiry:
            messages.error(request, "Reset OTP code has expired. Please request password reset again.")
            return redirect('forgot_password_otp')

        if submitted_otp != user.password_reset_otp:
            messages.error(request, "Invalid reset OTP code.")
            return render(request, 'accounts/reset_password_otp.html', {'masked_email': mask_email_address(user.email)})

        if new_password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, 'accounts/reset_password_otp.html', {'masked_email': mask_email_address(user.email)})

        user.set_password(new_password)
        user.password_reset_otp = None
        user.password_reset_otp_expiry = None
        user.unlock_account()
        user.save(update_fields=['password', 'password_reset_otp', 'password_reset_otp_expiry'])

        if 'reset_user_id' in request.session:
            del request.session['reset_user_id']

        AuditLog.objects.create(
            actor=user,
            action="PASSWORD_RESET",
            details=f"Password reset successfully for {user.username}",
            ip_address=get_client_ip(request)
        )
        Notification.objects.create(
            user=user,
            message="Your account password was changed successfully.",
            notif_type="WARNING"
        )

        messages.success(request, "Password reset successfully! Please log in with your new password.")
        return redirect('login')

    return render(request, 'accounts/reset_password_otp.html', {'masked_email': mask_email_address(user.email)})


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
