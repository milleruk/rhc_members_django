# staff/urls.py
from django.urls import path
from . import views

app_name = "staff"

urlpatterns = [
    path("", views.StaffHomeView.as_view(), name="home"),
    path("players/", views.PlayerListView.as_view(), name="player_list"),
    path("players/<int:player_id>/", views.PlayerDetailView.as_view(), name="player_detail"),
    path("memberships/<int:membership_id>/remove/", views.remove_membership, name="remove_membership"),
]