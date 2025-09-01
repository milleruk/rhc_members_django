# members/urls.py
from django.urls import path, include, re_path
from django.shortcuts import redirect
from .views import (
    dashboard,
    PlayerCreateView,
    answer_view,
    AdminPlayerListView,
    AdminPlayerDetailView,
    remove_membership,
    player_delete,
    PlayerUpdateView,
)

urlpatterns = [
    # Member-facing (UUIDs)
    path("dashboard/", dashboard, name="dashboard"),
    path("players/add/", PlayerCreateView.as_view(), name="player_add"),
    path("players/<uuid:public_id>/answers/", answer_view, name="answer"),         
    path("players/<uuid:public_id>/delete/", player_delete, name="player_delete"), 
    path("players/<uuid:public_id>/edit/", PlayerUpdateView.as_view(), name="player_edit"),

    # Staff (ints)
    path("staff/players/", AdminPlayerListView.as_view(), name="admin_player_list"),
    path("staff/", AdminPlayerListView.as_view(), name="admin_player_list"),
    path("staff/players/<int:player_id>/", AdminPlayerDetailView.as_view(), name="admin_player_detail"),
    path("staff/memberships/<int:membership_id>/remove/", remove_membership, name="remove_membership"),
]
