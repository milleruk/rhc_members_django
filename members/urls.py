# members/urls.py
from django.urls import path, include, re_path, reverse_lazy
from django.shortcuts import redirect
from django.views.generic import RedirectView   
from .views import (
    dashboard,
    PlayerCreateView,
    answer_view,
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

]