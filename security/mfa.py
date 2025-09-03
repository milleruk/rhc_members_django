# security/mfa.py
from functools import wraps

from allauth.mfa.adapter import get_adapter
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.decorators import method_decorator


def user_has_mfa_enabled(user) -> bool:
    # allauth exposes this through the adapter
    return get_adapter().is_mfa_enabled(user)


def mfa_setup_required(view_func):
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not user_has_mfa_enabled(request.user):
            # Send them to Activate TOTP, bounce back after
            return redirect(f"{reverse('mfa_activate_totp')}?next={request.get_full_path()}")
        return view_func(request, *args, **kwargs)

    return _wrapped


class MFASetupRequiredMixin:
    @method_decorator(mfa_setup_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)
