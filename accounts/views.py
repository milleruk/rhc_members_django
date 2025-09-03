# accounts/views.py
from __future__ import annotations

from allauth.account.views import LoginView as AllauthLoginView
from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError, transaction
from django.urls import reverse_lazy
from django.views.generic import FormView

from hockey_club.emails import send_activation_email

from .forms import AllauthLoginForm, AllauthSignupForm, ProfileForm

User = get_user_model()


class EmailLoginView(AllauthLoginView):
    """Email-only login via Allauth (uses AllauthLoginForm)."""

    template_name = "registration/login.html"
    form_class = AllauthLoginForm


class SignupView(FormView):
    """Signup using Allauth form (not a ModelForm)."""

    template_name = "registration/signup.html"
    form_class = AllauthSignupForm
    success_url = reverse_lazy("account_login")

    def form_valid(self, form):
        email = (form.cleaned_data.get("email") or "").strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            form.add_error(
                "email",
                "An account with this email already exists. Try logging in or resetting your password.",
            )
            return self.form_invalid(form)

        try:
            user = form.save(self.request)  # Allauth creates the user
        except IntegrityError:
            form.add_error(
                "email",
                "An account with this email already exists. Try logging in or resetting your password.",
            )
            return self.form_invalid(form)

        # Require email confirmation before login
        user.is_active = False
        user.save(update_fields=["is_active"])

        transaction.on_commit(lambda: send_activation_email(self.request, user))
        messages.success(
            self.request, "Account created. Please check your email to confirm before logging in."
        )
        return super().form_valid(form)


class UserSettingsView(LoginRequiredMixin, FormView):
    """Simple settings hub for profile (first/last/email)."""

    template_name = "account/settings.html"
    form_class = ProfileForm
    success_url = reverse_lazy("accounts:settings")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Profile updated.")
        return super().form_valid(form)


class ResendActivationForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "name@example.com",
                "autocomplete": "email",
            }
        )
    )


class ResendConfirmationView(FormView):
    template_name = "account/resend_confirmation.html"
    form_class = ResendActivationForm
    success_url = reverse_lazy("account_login")

    def form_valid(self, form):
        email = (form.cleaned_data["email"] or "").strip().lower()
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            messages.info(
                self.request, "If that address exists, a verification email has been sent."
            )
            return super().form_valid(form)

        # Only resend if not verified
        from allauth.account.models import EmailAddress

        try:
            addr = EmailAddress.objects.get(user=user, email__iexact=email)
        except EmailAddress.DoesNotExist:
            # Create and send one
            transaction.on_commit(lambda: send_activation_email(self.request, user))
            messages.success(self.request, "Verification email sent.")
            return super().form_valid(form)

        if addr.verified:
            messages.info(self.request, "This email is already verified. You can log in.")
            return super().form_valid(form)

        transaction.on_commit(lambda: send_activation_email(self.request, user))
        messages.success(self.request, "Verification email sent.")
        return super().form_valid(form)
