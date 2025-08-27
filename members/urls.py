from django.urls import path
from .views import (
    dashboard,
    PlayerCreateView,
    answer_view,
    AdminPlayerListView,
    AdminPlayerDetailView,
    remove_membership,
    player_delete
)



urlpatterns = [
    path("dashboard/", dashboard, name="dashboard"),
    path("players/add/", PlayerCreateView.as_view(), name="player_add"),
    path("players/profile/<int:player_id>/", answer_view, name="answer"),
    path("players/<int:pk>/delete/", player_delete, name="player_delete"),
    

    # Staff views restricted by Groups (avoid clashing with Django admin at /admin/)
    path("staff/players/", AdminPlayerListView.as_view(), name="admin_player_list"),
    path("staff/players/<int:player_id>/", AdminPlayerDetailView.as_view(), name="admin_player_detail"),
    path("staff/memberships/<int:membership_id>/remove/", remove_membership, name="remove_membership"),


]