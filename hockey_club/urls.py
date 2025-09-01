# hockey_club/urls.py
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.conf.urls import handler403, handler404
from members.views import TermsView, PrivacyView
from . import views

urlpatterns = [
    # ---- Admin & auth ----
    path("admin/", admin.site.urls),
    path("hijack/", include("hijack.urls")),
    path("accounts/", include("allauth.urls")),

    # ---- Core pages ----
    # If your dashboard is a function view: views.dashboard
    # If it's a class-based view, change to views.DashboardView.as_view()
    #path("dashboard/", members.views.dashboard, name="dashboard"),
    path("", include("members.urls")),

    # ---- Apps (namespaced) ----
    path("tasks/", include(("tasks.urls", "tasks"), namespace="tasks")),
    path("resources/", include(("resources.urls", "resources"), namespace="resources")),
    path("memberships/", include(("memberships.urls", "memberships"), namespace="memberships")),
    path("spond/", include(("spond_integration.urls", "spond"), namespace="spond")),
    path("players/", include(("members.urls", "members"), namespace="members")),
    path("staff/", include(("staff.urls", "staff"), namespace="staff")),

    # ---- Static pages ----
    path("terms/", TermsView.as_view(), name="terms"),
    path("privacy/", PrivacyView.as_view(), name="privacy_policy"),

    # ---- Root -> dashboard (keep last) ----
    path("", RedirectView.as_view(pattern_name="dashboard", permanent=False)),
]

# ---- 403 handler ----
def permission_denied_view(request, exception=None):
    from django.shortcuts import render
    return render(request, "403.html", status=403)

# ---- 403 handler ----
def page_not_found_view(request, exception=None):
    from django.shortcuts import render
    return render(request, "404.html", status=403)

handler403 = permission_denied_view
handler404 = page_not_found_view

# ---- Admin branding ----
admin.site.site_title = "Redditch Hockey Club Portal (DEV)"
admin.site.site_header = "Redditch Hockey Club Portal"
admin.site.index_title = "Site administration"
