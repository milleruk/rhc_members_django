# consents/urls.py
from django.urls import path

from .views import consents_view

app_name = "consents"  # <-- important
urlpatterns = [
    path("consents/", consents_view, name="consents"),
]
