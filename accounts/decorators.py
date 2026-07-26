from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.core.exceptions import PermissionDenied

def role_required(allowed_roles=None):
    if allowed_roles is None:
        allowed_roles = []
        
    allowed_roles = [str(r).lower() for r in allowed_roles]

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.error(request, "Please log in to access this page.")
                return redirect('login')
            
            user_role = str(request.user.role).lower() if request.user.role else ''

            if request.user.is_superuser or request.user.is_staff or user_role == 'admin':
                if 'admin' in allowed_roles or not allowed_roles:
                    return view_func(request, *args, **kwargs)

            if user_role in allowed_roles:
                return view_func(request, *args, **kwargs)
            
            messages.error(request, "You do not have permission to access that section.")
            if user_role == 'doctor':
                return redirect('doctor_dashboard')
            elif user_role == 'patient':
                return redirect('patient_dashboard')
            elif user_role == 'admin':
                return redirect('admin_dashboard')
            else:
                return redirect('login')
        return _wrapped_view
    return decorator

def admin_required(view_func):
    return role_required(['admin'])(view_func)

def doctor_required(view_func):
    return role_required(['doctor'])(view_func)

def patient_required(view_func):
    return role_required(['patient'])(view_func)
