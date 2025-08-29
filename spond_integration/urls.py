from django.urls import path, re_path
from django.shortcuts import redirect
from . import views

app_name = "spond"

urlpatterns = [
    path("search/", views.search_members, name="search"),
    path("link/<int:player_id>/", views.link_player, name="link"),
    path("unlink/<int:player_id>/<int:link_id>/", views.unlink_player, name="unlink"),
    path("can-access/", views.can_access, name="can_access"),
    path("dashboard/", views.SpondDashboardView.as_view(), name="dashboard"),  # FIXED
    path("events/", views.SpondEventsDashboardView.as_view(), name="events_dashboard"),

    # Catch-all: anything unmatched under this app goes to dashboard
    re_path(r"^.*$", lambda request: redirect("spond:dashboard")),
]
