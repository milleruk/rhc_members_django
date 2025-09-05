# hockey_club/calendar/apps.py
from django.apps import AppConfig


class ClubCalendarConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "club_calendar"
    label = "club_calendar"
    verbose_name = "Club Calendar"
