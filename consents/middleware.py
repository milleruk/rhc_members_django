# consents/middleware.py
from django.conf import settings
from django.shortcuts import redirect
from django.urls import resolve

from .models import user_has_required_consents

WHITELISTED_NAMES = {
    "consents:consents",  # your consent page
    "account_logout",
    "account_login",
    "account_signup",
    "account_reset_password",
    # add health, static, media if you reverse by name, etc.
}


class EnforceConsentsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        # Skip entirely in tests/CI
        if not getattr(settings, "ACCOUNTS_REQUIRE_CONSENT", True):
            return self.get_response(request)

        if request.user.is_authenticated:
            try:
                match = resolve(request.path_info)
                name = f"{match.namespace}:{match.url_name}" if match.namespace else match.url_name
            except Exception:
                name = None

            if name not in WHITELISTED_NAMES and not user_has_required_consents(request.user):
                return redirect("consents:consents")

        return self.get_response(request)
