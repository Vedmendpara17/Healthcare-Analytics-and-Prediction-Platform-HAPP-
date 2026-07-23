import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

class StrongPasswordValidator:
    """
    Validates whether the password meets strong security standards:
    - Minimum 8 characters
    - At least one uppercase letter (A-Z)
    - At least one lowercase letter (a-z)
    - At least one numerical digit (0-9)
    - At least one special character (e.g. !@#$%^&*)
    """
    def validate(self, password, user=None):
        if len(password) < 8:
            raise ValidationError(
                _("Password must be at least 8 characters long."),
                code='password_too_short',
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

    def get_help_text(self):
        return _("Your password must be at least 8 characters long and contain a combination of uppercase letters, lowercase letters, numbers, and special characters (e.g. Het@1222, Yug#5445).")


# Alias for backward compatibility
NumberAndSpecialCharValidator = StrongPasswordValidator

