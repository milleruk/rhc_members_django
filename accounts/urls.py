from django.urls import path
from .views import EmailLoginView, SignupView
from django.contrib.auth.views import LogoutView

urlpatterns = [
    path("login/", EmailLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("signup/", SignupView.as_view(), name="signup"),
]
