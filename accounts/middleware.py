import time
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.conf import settings

class SessionTimeoutMiddleware:
    """
    Middleware that automatically logs out authenticated users after 30 minutes
    (1800 seconds) of inactivity.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            now = time.time()
            last_activity = request.session.get('last_activity')
            timeout = getattr(settings, 'SESSION_TIMEOUT_SECONDS', 1800) # 30 minutes default

            if last_activity and (now - last_activity > timeout):
                logout(request)
                messages.warning(request, "Your session expired due to 30 minutes of inactivity. Please log in again.")
                return redirect('login')

            request.session['last_activity'] = now

        response = self.get_response(request)
        return response
