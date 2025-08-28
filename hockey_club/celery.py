# hockey_club/celery.py
import os
from celery import Celery   # <-- this was the problem

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hockey_club.settings")

app = Celery("hockey_club")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
