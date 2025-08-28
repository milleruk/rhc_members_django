# spond/urls.py
from django.urls import path
from . import views

app_name = "spond"

urlpatterns = [
    path("search/", views.search_members, name="search"),
    path("link/<int:player_id>/", views.link_player, name="link"),
    path("unlink/<int:player_id>/<int:link_id>/", views.unlink_player, name="unlink"),
    path("can-access/", views.can_access, name="can_access"),  # simple probe for front-end
]
