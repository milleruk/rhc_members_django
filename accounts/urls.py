# accounts/urls.py
from django.urls import path

from .views import UserSettingsView

app_name = "accounts"

urlpatterns = [
    path("", UserSettingsView.as_view(), name="settings"),
]
