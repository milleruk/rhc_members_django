from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .forms import ConsentForm
from .models import ConsentLog, ConsentType, user_has_required_consents


@login_required
@require_http_methods(["GET", "POST"])
def consents_view(request):
    # If user already has required consents, bounce to dashboard
    if user_has_required_consents(request.user):
        return redirect("dashboard")

    if request.method == "POST":
        form = ConsentForm(request.POST)
        if form.is_valid():
            ip = request.META.get("REMOTE_ADDR")
            ua = request.META.get("HTTP_USER_AGENT", "")
            user = request.user

            # Required
            for ct in (ConsentType.TERMS, ConsentType.CLUB, ConsentType.ENGLAND_HOCKEY):
                ConsentLog.objects.update_or_create(
                    user=user,
                    consent_type=ct,
                    defaults={"given": True, "ip_address": ip, "user_agent": ua},
                )

            # Optional
            ConsentLog.objects.update_or_create(
                user=user,
                consent_type=ConsentType.MARKETING,
                defaults={
                    "given": bool(form.cleaned_data.get("accept_marketing")),
                    "ip_address": ip,
                    "user_agent": ua,
                },
            )

            return redirect("dashboard")
    else:
        form = ConsentForm()

    return render(request, "account/consents.html", {"form": form})
