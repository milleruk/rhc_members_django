# tasks/apps.py
from django.apps import AppConfig

class TasksConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tasks"
    verbose_name = "Tasks"

    def ready(self):
        # Import signals only after the app registry is ready
        from . import signals  # noqa: F401
