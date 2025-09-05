# club_calendar/urls.py
from django.urls import path

from . import views

app_name = "club_calendar"

urlpatterns = [
    path("", views.CalendarPageView.as_view(), name="index"),
    path("api/events/", views.events_feed, name="events_feed"),
    path("events/add/", views.EventCreateView.as_view(), name="event_add"),
    path("events/<int:pk>/edit/", views.EventUpdateView.as_view(), name="event_edit"),
    path("events/<int:pk>/delete/", views.EventDeleteView.as_view(), name="event_delete"),
    path("events/<int:pk>/cancel_occurrence/", views.cancel_occurrence, name="cancel_occurrence"),
    path("events/<int:pk>/edit_occurrence/", views.edit_occurrence, name="edit_occurrence"),
]
