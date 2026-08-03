from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone

def send_account_lockout_email(user):
    """Sends Security Alert email when account is locked due to failed login attempts."""
    subject = "Security Alert: Account Temporarily Locked"
    user_display = user.get_full_name() or user.username
    now_str = timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC')
    
    body = (
        f"Dear {user_display},\n\n"
        f"Your account has been temporarily locked due to consecutive unsuccessful login attempts.\n\n"
        f"Lock Details:\n"
        f"- Date & Time: {now_str}\n"
        f"- Reason: Multiple failed login attempts\n"
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
