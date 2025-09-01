# hockey_club/celery.py
import os
from celery import Celery
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hockey_club.settings")
app = Celery("hockey_club")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

@app.on_after_configure.connect
def _auto_sync_beat(sender, **kwargs):
    """
    When Celery (Beat or Worker) starts, try to sync schedules from settings.
    Fail-soft (won't crash if DB not ready).
    """
    try:
        from django.core.management import call_command
        call_command("sync_beat_from_settings")
    except Exception as e:
        sender.log.get_default_logger().warning("Beat sync skipped: %r", e)