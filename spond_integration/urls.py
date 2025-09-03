from django.shortcuts import redirect
from django.urls import path, re_path

from . import views
from .views import (
    debug_spond_call,
    debug_spond_events_json,
    debug_spond_methods,
)

app_name = "spond"

urlpatterns = [
    path("search/", views.search_members, name="search"),
    path("link/<int:player_id>/", views.link_player, name="link"),
    path("unlink/<int:player_id>/<int:link_id>/", views.unlink_player, name="unlink"),
    path("can-access/", views.can_access, name="can_access"),
    path("dashboard/", views.SpondDashboardView.as_view(), name="dashboard"),  # FIXED
    path("events/", views.SpondEventsDashboardView.as_view(), name="events_dashboard"),
    path("debug/events.json", debug_spond_events_json, name="spond_debug_events_json"),
    path("debug/methods.json", debug_spond_methods, name="spond_debug_methods"),
    path("debug/call.json", debug_spond_call, name="spond_debug_call"),
    # Catch-all: anything unmatched under this app goes to dashboard
    re_path(r"^.*$", lambda request: redirect("spond:dashboard")),
]
