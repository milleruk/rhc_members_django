# accounts/views.py
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView
from django.views.generic import CreateView
from django.urls import reverse_lazy
from django.contrib.auth import login, authenticate
from django.db import transaction

from .forms import EmailOnlyAuthenticationForm, EmailOnlySignupForm
from hockey_club.emails import send_activation_email  # from prior step


class EmailLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = EmailOnlyAuthenticationForm
    redirect_authenticated_user = True  # if already logged in, go to LOGIN_REDIRECT_URL

    def form_valid(self, form):
        # Let Django log the user in first
        response = super().form_valid(form)

        # Handle "Remember me" – if unchecked, expire on browser close
        remember = form.cleaned_data.get("remember_me")
        if not remember:
            self.request.session.set_expiry(0)          # expire at browser close
        else:
            self.request.session.set_expiry(60 * 60 * 24 * 14)  # 2 weeks

        return response


class SignupView(CreateView):
    #form_class = EmailOnlySignupForm
    #template_name = "registration/signup.html"
    #success_url = reverse_lazy("login")  # or reverse_lazy("dashboard") if you auto-login

    # If you want to auto-login after signup, uncomment this:
    # def form_valid(self, form):
    #     user = form.save()
    #     # authenticate with email-as-username + password1 from the form
    #     raw_password = form.cleaned_data.get("password1")
    #     user = authenticate(self.request, username=user.username, password=raw_password)
    #     if user:
    #         login(self.request, user)
    #         return redirect("dashboard")
    #     return super().form_valid(form)

    template_name = "registration/signup.html"
    form_class = EmailOnlySignupForm
    success_url = reverse_lazy("login")

    def form_valid(self, form):
        user: User = form.save(commit=False)
        user.is_active = False                    # <-- critical
        user.email = form.cleaned_data["email"]   # ensure saved
        user.save()

        # Send activation email AFTER transaction commits (avoids race on token)
        transaction.on_commit(lambda: send_activation_email(self.request, user))

        messages.success(self.request, "Account created. Check your email to confirm.")
        return super().form_valid(form)