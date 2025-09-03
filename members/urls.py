# members/urls.py
from django.urls import path

from .views import (
    PlayerCreateView,
    PlayerUpdateView,
    answer_view,
    dashboard,
    player_delete,
)

urlpatterns = [
    # Member-facing (UUIDs)
    path("dashboard/", dashboard, name="dashboard"),
    path("players/", dashboard, name="dashboard"),
    path("players/add/", PlayerCreateView.as_view(), name="player_add"),
    path("players/<uuid:public_id>/answers/", answer_view, name="answer"),
    path("players/<uuid:public_id>/delete/", player_delete, name="player_delete"),
    path("players/<uuid:public_id>/edit/", PlayerUpdateView.as_view(), name="player_edit"),
]
