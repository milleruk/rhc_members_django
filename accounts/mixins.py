# accounts/mixins.py
from __future__ import annotations
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.module_loading import import_string


MFA_MANAGE_URL = "/accounts/mfa/"


def _get_mfa_adapter(request=None):
    """Return the configured allauth MFA adapter (or the default)."""
    path = getattr(settings, "MFA_ADAPTER", "allauth.mfa.adapter.DefaultMFAAdapter")
    Adapter = import_string(path)
    try:
        return Adapter(request=request)
    except TypeError:
        # Older adapters may not accept request kwarg
        return Adapter()


class RequireMFAMixin:
    """
    Require at least one enabled/confirmed MFA factor for the current user.
    Redirects to /accounts/mfa/?next=<current> if none is found.
    """
    mfa_redirect_url = MFA_MANAGE_URL
    mfa_message = "You need to enable two-factor authentication to access this page."

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        if user.is_authenticated and not self.user_has_mfa(request, user):
            messages.warning(request, self.mfa_message)
            return redirect(f"{self.mfa_redirect_url}?{urlencode({'next': request.get_full_path()})}")
        return super().dispatch(request, *args, **kwargs)

    # Accept both call styles: (user) OR (request, user)
    def user_has_mfa(self, *args, **kwargs) -> bool:
        # Normalize args
        request = None
        user = None
        if len(args) == 1:
            user = args[0]
        elif len(args) >= 2:
            request, user = args[0], args[1]
        user = user or kwargs.get("user")

        if user is None:
            return False

        # 1) Ask allauth’s MFA adapter (canonical)
        try:
            adapter = _get_mfa_adapter(request)
            if hasattr(adapter, "is_mfa_enabled") and adapter.is_mfa_enabled(user):
                return True
        except Exception:
            pass

        # 2) django-otp fallback (covers TOTP/WebAuthn if present)
        try:
            from django_otp import devices_for_user
            for d in devices_for_user(user, confirmed=None):
                confirmed = getattr(d, "confirmed", getattr(d, "confirmed_at", None))
                active = getattr(d, "is_active", True)
                if (confirmed is True or confirmed) and active:
                    return True
        except Exception:
            pass

        # 3) allauth TOTP device models (new/old paths)
        for dotted in (
            "allauth.mfa.totp.models.TOTPDevice",
            "allauth.mfa.models.TOTPDevice",
        ):
            try:
                Model = import_string(dotted)
                for d in Model.objects.filter(user=user):
                    confirmed = getattr(d, "confirmed", getattr(d, "is_confirmed", getattr(d, "confirmed_at", None)))
                    active = getattr(d, "is_active", True)
                    if (confirmed is True or confirmed) and active:
                        return True
            except Exception:
                continue

        return False
