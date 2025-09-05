# hockey_club/urls.py
import os

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from accounts.views import ResendConfirmationView
from members.views import PrivacyView, TermsView

urlpatterns = [
    # ---- Admin & auth ----
    path("jet/", include("jet.urls", "jet")),  # Django JET URLS
    path(
        "jet/dashboard/", include("jet.dashboard.urls", "jet-dashboard")
    ),  # Django JET dashboard URL
    path("admin/", admin.site.urls),
    path("hijack/", include("hijack.urls")),
    path(
        "accounts/resend-confirmation/",
        ResendConfirmationView.as_view(),
        name="account_resend_confirmation",
    ),
    path("accounts/", include(("consents.urls", "consents"), namespace="consents")),
    path("accounts/", include("allauth.urls")),
    path("accounts/mfa/", include("allauth.mfa.urls")),
    # Settings hub
    path("settings/", include(("accounts.urls", "accounts"), namespace="accounts")),
    # ---- Root → dashboard (exact match) ----
    path("", RedirectView.as_view(pattern_name="dashboard", permanent=False)),
    # ---- Core app mounts ----
    # Mount members WITHOUT a namespace so names like 'dashboard' remain global.
    path("", include("members.urls")),  # <- no ("members", namespace="members")
    # Memberships & wallet helpers
    path("wallet/", include("memberships.wallet_urls")),
    # Other apps (namespaced)
    path("tasks/", include(("tasks.urls", "tasks"), namespace="tasks")),
    path("resources/", include(("resources.urls", "resources"), namespace="resources")),
    path(
        "memberships/",
        include(("memberships.urls", "memberships"), namespace="memberships"),
    ),
    path("spond/", include(("spond_integration.urls", "spond"), namespace="spond")),
    path("staff/", include(("staff.urls", "staff"), namespace="staff")),
    path("incidents/", include(("incidents.urls", "incidents"), namespace="incidents")),
    path("calendar/", include("club_calendar.urls")),
    # ---- Static pages ----
    path("terms/", TermsView.as_view(), name="terms"),
    path("privacy/", PrivacyView.as_view(), name="privacy_policy"),
]


# ---- Error handlers ----
def permission_denied_view(request, exception=None):
    from django.shortcuts import render

    return render(request, "403.html", status=403)


def page_not_found_view(request, exception=None):
    from django.shortcuts import render

    return render(request, "404.html", status=404)


handler403 = permission_denied_view
handler404 = page_not_found_view

# ---- Admin branding ----
admin.site.site_title = "Redditch Hockey Club Portal (DEV)"
admin.site.site_header = "Redditch Hockey Club Portal"
admin.site.index_title = "Site administration"

# ---- Conditionally include WalletPass API only when fully configured ----
wallet_enabled = getattr(settings, "WALLET_APPLE_ENABLED", False)
wallet_conf = getattr(settings, "WALLETPASS", {})
cert_path = wallet_conf.get("CERT_PATH") or ""
key_path = wallet_conf.get("KEY_PATH") or ""

if (
    wallet_enabled
    and cert_path
    and key_path
    and os.path.exists(cert_path)
    and os.path.exists(key_path)
    and "django_walletpass" in settings.INSTALLED_APPS
):
    urlpatterns += [path("api/passes/", include("django_walletpass.urls"))]
