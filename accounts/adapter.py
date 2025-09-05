# accounts/adapters.py
from allauth.account.adapter import DefaultAccountAdapter
from django.shortcuts import resolve_url

from consents.models import user_has_required_consents


class RHCAccountAdapter(DefaultAccountAdapter):
    def _consent_or(self, request, fallback):
        user = getattr(request, "user", None)
        if user and user.is_authenticated and not user_has_required_consents(user):
            return resolve_url("consents:consents")  # <-- namespaced
        return resolve_url(fallback)

    def get_login_redirect_url(self, request):
        return self._consent_or(request, "dashboard")

    def get_signup_redirect_url(self, request):
        return self._consent_or(request, "dashboard")
