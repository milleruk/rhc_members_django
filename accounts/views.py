# accounts/views.py
from __future__ import annotations

from typing import Optional

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.shortcuts import resolve_url
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import EmailOnlyAuthenticationForm, EmailOnlySignupForm
from hockey_club.emails import send_activation_email


REMEMBER_ME_AGE_SECONDS = 60 * 60 * 24 * 14  # 14 days


def _safe_redirect_url(request, fallback: str) -> str:
    """
    Return a safe post-auth redirect URL. Prefers ?next= when present and safe.
    """
    next_url: Optional[str] = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return resolve_url(fallback)


class EmailLoginView(LoginView):
    """
    Email-based login view with optional 'remember me' session persistence.
    """
    template_name = "registration/login.html"
    authentication_form = EmailOnlyAuthenticationForm
    redirect_authenticated_user = True  # already-logged-in users skip to redirect URL

    def form_valid(self, form):
        # Delegate to Django to authenticate + log in (rotates session key).
        response = super().form_valid(form)

        # Session lifetime: browser session if not 'remember me'
        remember = form.cleaned_data.get("remember_me")
        if not remember:
            self.request.session.set_expiry(0)  # expire on browser close
        else:
            self.request.session.set_expiry(REMEMBER_ME_AGE_SECONDS)

        return response

    def get_success_url(self) -> str:
        # Respect ?next= when safe; otherwise LOGIN_REDIRECT_URL
        return _safe_redirect_url(self.request, getattr(settings, "LOGIN_REDIRECT_URL", "/"))


class SignupView(CreateView):
    """
    Email-first signup: user is created inactive and must verify via email.
    """
    template_name = "registration/signup.html"
    form_class = EmailOnlySignupForm
    success_url = reverse_lazy("login")

    def form_valid(self, form):
        # All-or-nothing DB write; send mail only after commit.
        with transaction.atomic():
            user: User = form.save(commit=False)
            # Ensure email is set on the user model from the form
            user.email = form.cleaned_data["email"]
            # Keep new accounts inactive until confirmed
            user.is_active = False
            user.save()

            # Defer email until the DB commit has succeeded
            transaction.on_commit(lambda: send_activation_email(self.request, user))

        messages.success(
            self.request,
            "Account created. Please check your email to confirm your address before logging in.",
        )
        return super().form_valid(form)
