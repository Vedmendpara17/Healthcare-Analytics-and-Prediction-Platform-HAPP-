import secrets
import string
import datetime
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.template.loader import render_to_string

def generate_secure_otp():
    """Generates a cryptographically secure 6-digit numeric string."""
    digits = string.digits
    return ''.join(secrets.choice(digits) for _ in range(6))

def mask_email_address(email):
    """Masks email address e.g. john.doe@gmail.com -> jo*****@gmail.com"""
    if not email or '@' not in email:
        return email
    local, domain = email.split('@', 1)
    if len(local) <= 2:
        masked_local = local[0] + '*' * 5 if local else '*****'
    else:
        masked_local = local[:2] + '*' * 5
    return f"{masked_local}@{domain}"

def send_login_otp_email(user, otp):
    """Dispatches the login verification 2FA OTP to the user's email."""
    subject = "Your Login Verification Code"
    user_display = user.get_full_name() or user.username
    
    body = (
        f"Hello {user_display},\n\n"
        f"Your One-Time Password (OTP) is:\n\n"
        f"{otp}\n\n"
        f"This OTP is valid for 5 minutes.\n"
        f"Do not share this OTP with anyone.\n\n"
        f"If you did not attempt to log in, please ignore this email.\n\n"
        f"Regards,\n"
        f"Healthcare Analytics & Prediction Platform"
    )
    
    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
        <h2 style="color: #0f766e; margin-bottom: 20px;">Healthcare Analytics & Prediction Platform</h2>
        <p>Hello <strong>{user_display}</strong>,</p>
        <p>Your One-Time Password (OTP) for login verification is:</p>
        <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 6px; padding: 15px; text-align: center; margin: 20px 0;">
            <span style="font-size: 32px; font-weight: bold; letter-spacing: 6px; color: #0f766e;">{otp}</span>
        </div>
        <p style="color: #64748b; font-size: 14px;">This OTP is valid for <strong>5 minutes</strong>. Do not share this code with anyone.</p>
        <p style="color: #94a3b8; font-size: 13px; margin-top: 30px; border-top: 1px solid #cbd5e1; padding-top: 15px;">
            If you did not attempt to log in, please ignore this email.<br>
            Regards,<br>
            <strong>Healthcare Analytics & Prediction Platform</strong>
        </p>
    </div>
    """
    
    send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL if hasattr(settings, 'DEFAULT_FROM_EMAIL') else 'noreply@happ.com',
        recipient_list=[user.email],
        html_message=html_body,
        fail_silently=True
    )

def send_email_verification_otp(user, otp):
    """Dispatches registration email verification OTP."""
    subject = "Verify Your Email Address - HAPP"
    user_display = user.get_full_name() or user.username
    body = (
        f"Hello {user_display},\n\n"
        f"Thank you for registering. Your Email Verification OTP is:\n\n"
        f"{otp}\n\n"
        f"This OTP is valid for 5 minutes.\n\n"
        f"Regards,\n"
        f"Healthcare Analytics & Prediction Platform"
    )
    send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL if hasattr(settings, 'DEFAULT_FROM_EMAIL') else 'noreply@happ.com',
        recipient_list=[user.email],
        fail_silently=True
    )

def send_password_reset_otp(user, otp):
    """Dispatches password reset OTP (10 min expiry)."""
    subject = "Password Reset Code - HAPP"
    user_display = user.get_full_name() or user.username
    body = (
        f"Hello {user_display},\n\n"
        f"You requested to reset your password. Your Password Reset OTP is:\n\n"
        f"{otp}\n\n"
        f"This OTP is valid for 10 minutes.\n"
        f"If you did not request a password reset, please ignore this email.\n\n"
        f"Regards,\n"
        f"Healthcare Analytics & Prediction Platform"
    )
    send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL if hasattr(settings, 'DEFAULT_FROM_EMAIL') else 'noreply@happ.com',
        recipient_list=[user.email],
        fail_silently=True
    )

def send_account_lockout_email(user):
    """Sends Security Alert email when account is locked due to 4 failed attempts."""
    subject = "Security Alert: Account Temporarily Locked"
    user_display = user.get_full_name() or user.username
    now_str = timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC')
    
    body = (
        f"Dear {user_display},\n\n"
        f"Your account has been temporarily locked due to 4 consecutive unsuccessful login attempts.\n\n"
        f"Lock Details:\n"
        f"- Date & Time: {now_str}\n"
        f"- Reason: Multiple failed login attempts (4/4)\n"
        f"- Lock Duration: 15 minutes\n\n"
        f"If these login attempts were not made by you, please reset your password immediately or contact system administration.\n\n"
        f"Best regards,\n"
        f"Healthcare Analytics & Prediction Platform Security Team"
    )
    
    send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL if hasattr(settings, 'DEFAULT_FROM_EMAIL') else 'noreply@happ.com',
        recipient_list=[user.email],
        fail_silently=True
    )

