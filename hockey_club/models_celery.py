# hockey_club/models_celery.py
from django_celery_beat.models import (
    PeriodicTask as _BeatPeriodicTask,
    CrontabSchedule as _BeatCrontabSchedule,
    IntervalSchedule as _BeatIntervalSchedule,
    SolarSchedule as _BeatSolarSchedule,
    ClockedSchedule as _BeatClockedSchedule,
)

class BeatPeriodicTask(_BeatPeriodicTask):
    class Meta:
        proxy = True
        app_label = "hockey_club"
        verbose_name = "Periodic task"
        verbose_name_plural = "Periodic tasks"

class BeatCrontabSchedule(_BeatCrontabSchedule):
    class Meta:
        proxy = True
        app_label = "hockey_club"
        verbose_name = "Crontab"
        verbose_name_plural = "Crontabs"

class BeatIntervalSchedule(_BeatIntervalSchedule):
    class Meta:
        proxy = True
        app_label = "hockey_club"
        verbose_name = "Interval"
        verbose_name_plural = "Intervals"

class BeatSolarSchedule(_BeatSolarSchedule):
    class Meta:
        proxy = True
        app_label = "hockey_club"
        verbose_name = "Solar event"
        verbose_name_plural = "Solar events"

class BeatClockedSchedule(_BeatClockedSchedule):
    class Meta:
        proxy = True
        app_label = "hockey_club"
        verbose_name = "Clocked (one-off)"
        verbose_name_plural = "Clocked (one-off)"
