# tasks/tasks.py
from celery import shared_task
from django.conf import settings

from .emailing import _build_user_task_map, _send_digest


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_daily_task_digest(self):
    """
    Send a daily digest of open tasks to each assignee.
    Idempotent: safe to run once per day via Celery Beat.
    """
    if not getattr(settings, "TASKS_DIGEST_ENABLED", True):
        return {"sent": 0, "skipped": "disabled"}

    sent = 0
    user_map = _build_user_task_map()
    for user, tasks in user_map.items():
        try:
            sent += _send_digest(user, tasks)
        except Exception as e:
            # optional: log or retry
            raise self.retry(exc=e)
    return {"sent": sent, "users": len(user_map)}
