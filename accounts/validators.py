import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

COMMON_WEAK_PASSWORDS = {
    'password', '12345678', 'qwerty', 'admin123', 'letmein',
    'password123', 'admin', 'welcome', '123456', '123456789',
    '1234567890', 'abc123', 'iloveyou', 'sunshine', 'pass1234'
}

class StrongPasswordValidator:
    """
    Validates password against security guidelines:
    - Min length 8, Max length 64
    - At least one uppercase letter (A-Z)
    - At least one lowercase letter (a-z)
    - At least one numerical digit (0-9)
    - At least one special character (!@#$%^&*()_+-=[]{}|;:'",.<>?/`)
    - Rejects common weak passwords
    - Rejects passwords containing username, email prefix/address, or phone number
    """
    def validate(self, password, user=None):
        if len(password) < 8:
            raise ValidationError(
                _("Password must be at least 8 characters long."),
                code='password_too_short',
            )
        if len(password) > 64:
            raise ValidationError(
                _("Password must not exceed 64 characters in length."),
                code='password_too_long',
            )
        if not re.search(r'[A-Z]', password):
            raise ValidationError(
                _("Password must contain at least one uppercase letter (A-Z)."),
                code='password_no_upper',
            )
        if not re.search(r'[a-z]', password):
            raise ValidationError(
                _("Password must contain at least one lowercase letter (a-z)."),
                code='password_no_lower',
            )
        if not re.search(r'\d', password):
            raise ValidationError(
                _("Password must contain at least one numerical digit (0-9)."),
                code='password_no_digit',
            )
        if not re.search(r'[!@#$%^&*()_+\-=\[\]{};:\'",.<>/?\\|`~]', password):
            raise ValidationError(
                _("Password must contain at least one special character (e.g. !@#$%^&*)."),
                code='password_no_special',
            )

        if password.lower() in COMMON_WEAK_PASSWORDS:
            raise ValidationError(
                _("This password is too common or weak. Please choose a stronger password."),
                code='password_too_common',
            )

        if user:
            pwd_lower = password.lower()
            if getattr(user, 'username', None) and len(user.username) >= 3:
                if user.username.lower() in pwd_lower:
                    raise ValidationError(
                        _("Password must not contain your username."),
                        code='password_contains_username',
                    )
            if getattr(user, 'email', None) and len(user.email) >= 3:
                email_part = user.email.split('@')[0].lower()
                if email_part and len(email_part) >= 3 and email_part in pwd_lower:
                    raise ValidationError(
                        _("Password must not contain your email address."),
                        code='password_contains_email',
                    )
            if getattr(user, 'phone', None) and len(str(user.phone)) >= 4:
                phone_str = str(user.phone).strip()
                if phone_str and phone_str in pwd_lower:
                    raise ValidationError(
                        _("Password must not contain your phone number."),
                        code='password_contains_phone',
                    )

    def get_help_text(self):
        return _("Password must be between 8 and 64 characters long and contain uppercase, lowercase, numbers, and special characters.")


# Alias for backward compatibility
NumberAndSpecialCharValidator = StrongPasswordValidator

