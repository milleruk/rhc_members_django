from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.contrib.auth import views as auth_views
from django.conf.urls import handler403
from members.views import TermsView, PrivacyView
from . import views


urlpatterns = [
path("admin/", admin.site.urls),
path('hijack/', include('hijack.urls')),
#path("accounts/", include("accounts.urls")),
path("accounts/", include("allauth.urls")),   # ⚠️ adds login/signup/confirm/resend etc.
path("tasks/", include("tasks.urls")),


path("resources/", include(("resources.urls", "resources"), namespace="resources")),
path("", include("members.urls")),
path("", RedirectView.as_view(pattern_name="dashboard", permanent=False)),


#path("accounts/password_reset/", auth_views.PasswordResetView.as_view(), name="password_reset"),
#path("accounts/password_reset/done/", auth_views.PasswordResetDoneView.as_view(), name="password_reset_done"),
#path("accounts/reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
#path("accounts/reset/done/", auth_views.PasswordResetCompleteView.as_view(), name="password_reset_complete"),
#path("accounts/activate/<uidb64>/<token>/", views.activate_account, name="activate_account"),

path("memberships/", include("memberships.urls", namespace="memberships")),
path("spond/", include("spond_integration.urls", namespace="spond")),

path("terms/", TermsView.as_view(), name="terms"),
path("privacy/", PrivacyView.as_view(), name="privacy_policy"),


]


def permission_denied_view(request, exception=None):
    from django.shortcuts import render
    return render(request, "403.html", status=403)

handler403 = permission_denied_view

admin.site.site_title = "Redditch Hockey Club Portal (DEV)"
admin.site.site_header = "Redditch Hockey Club Portal"
admin.site.index_title = "Site administration"
