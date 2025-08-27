# accounts/views.py
from django.contrib.auth.views import LoginView
from django.views.generic import CreateView
from django.urls import reverse_lazy
from django.contrib.auth import login, authenticate

from .forms import EmailOnlyAuthenticationForm, EmailOnlySignupForm


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
    form_class = EmailOnlySignupForm
    template_name = "registration/signup.html"
    success_url = reverse_lazy("login")  # or reverse_lazy("dashboard") if you auto-login

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
