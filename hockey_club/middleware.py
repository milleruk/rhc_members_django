# hockey_club/middleware.py
from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse, NoReverseMatch
from django.contrib import messages
from django.utils.deprecation import MiddlewareMixin

class LoginRequiredMiddleware(MiddlewareMixin):
    """
    Force login for all views by default, unless explicitly exempt.
    """

    def process_view(self, request, view_func, view_args, view_kwargs):
        assert hasattr(request, "user")

        if request.user.is_authenticated:
            return None

        # Exempt URLs
        exempt_urls = [
            settings.LOGIN_URL,
            getattr(settings, "LOGOUT_URL", reverse("account_logout")),
            reverse("account_signup"),
            reverse("account_reset_password"),
            reverse("account_reset_password_done"),
        ]
        exempt_urls += getattr(settings, "LOGIN_EXEMPT_URLS", [])

        if request.path.startswith(settings.STATIC_URL) or (
            hasattr(settings, "MEDIA_URL") and request.path.startswith(settings.MEDIA_URL)
        ):
            return None

        try:
            if request.path in exempt_urls:
                return None
        except NoReverseMatch:
            pass

        # 👇 Add warning message before redirect
        messages.warning(request, "Please log in to access that page.")
        return redirect(settings.LOGIN_URL)
