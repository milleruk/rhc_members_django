from django.urls import path

from . import views

app_name = "incidents"

urlpatterns = [
    path("", views.IncidentListView.as_view(), name="list"),
    path("add/", views.IncidentCreateView.as_view(), name="add"),
    path("detail/<int:pk>/", views.IncidentDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.IncidentUpdateView.as_view(), name="edit"),
    path("<int:pk>/action/", views.IncidentActionView.as_view(), name="action"),
    # workflow endpoints
    path("<int:pk>/assign/", views.AssignToMeView.as_view(), name="assign_to_me"),
    path(
        "<int:pk>/action-required/",
        views.MarkActionRequiredView.as_view(),
        name="mark_action_required",
    ),
    path("<int:pk>/close/", views.CloseIncidentView.as_view(), name="close"),
    path("<int:pk>/unassign/", views.UnassignView.as_view(), name="unassign"),
]
