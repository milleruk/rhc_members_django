from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.tokens import default_token_generator
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode

from .emails import send_activation_email

User = get_user_model()


def custom_404(request, exception):
    return render(request, "404.html", status=404)


def register(request):
    """
    Example registration view:
    - Create user inactive
    - Send activation email
    - Redirect to 'check your inbox' page
    """
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        first_name = request.POST.get("first_name", "")
        last_name = request.POST.get("last_name", "")

        if not email or not password:
            messages.error(request, "Email and password are required.")
            return redirect("register")

        if User.objects.filter(email__iexact=email).exists():
            messages.error(request, "That email is already registered.")
            return redirect("register")

        user = User.objects.create_user(
            username=email,  # or your own username scheme
            email=email,
            first_name=first_name,
            last_name=last_name,
            password=password,
            is_active=False,  # critical: inactive until confirmed
        )
        send_activation_email(request, user)
        messages.success(request, "Account created. Check your inbox to confirm your email.")
        return redirect("login")  # or a 'check-your-email' page

    return render(request, "accounts/register.html")


def activate_account(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = get_object_or_404(User, pk=uid)
    except (TypeError, ValueError, OverflowError):
        return HttpResponseBadRequest("Invalid activation link.")

    if user.is_active:
        messages.info(request, "Your account is already active. You can sign in.")
        return redirect("login")

    if default_token_generator.check_token(user, token):
        user.is_active = True
        user.save(update_fields=["is_active"])
        messages.success(request, "Email confirmed. Welcome!")
        login(request, user)
        return redirect("dashboard")  # adjust
    else:
        messages.error(request, "Activation link is invalid or expired.")
        return redirect("resend_activation")


def resend_activation(request):
    if request.method == "POST":
        email = request.POST.get("email")
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            messages.error(request, "We couldn't find an account with that email.")
            return redirect("resend_activation")

        if user.is_active:
            messages.info(request, "Your account is already active. Please sign in.")
            return redirect("login")

        send_activation_email(request, user)
        messages.success(request, "We’ve sent a new activation email.")
        return redirect("login")

    return render(request, "accounts/resend_activation.html")
