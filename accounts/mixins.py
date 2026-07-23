from django.contrib.auth.mixins import AccessMixin
from django.shortcuts import redirect
from django.contrib import messages

class RoleRequiredMixin(AccessMixin):
    allowed_roles = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if request.user.is_superuser or request.user.role == 'admin':
            if 'admin' in self.allowed_roles or not self.allowed_roles:
                return super().dispatch(request, *args, **kwargs)

        if request.user.role in self.allowed_roles:
            return super().dispatch(request, *args, **kwargs)

        messages.error(request, "Access restricted. Insufficient role permissions.")
        if request.user.role == 'doctor':
            return redirect('doctor_dashboard')
        elif request.user.role == 'patient':
            return redirect('patient_dashboard')
        elif request.user.role == 'admin':
            return redirect('admin_dashboard')
        return redirect('login')

class AdminRequiredMixin(RoleRequiredMixin):
    allowed_roles = ['admin']

class DoctorRequiredMixin(RoleRequiredMixin):
    allowed_roles = ['doctor']

class PatientRequiredMixin(RoleRequiredMixin):
    allowed_roles = ['patient']
