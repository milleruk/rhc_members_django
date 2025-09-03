# memberships/tasks.py (Celery)
from django.utils.timezone import localdate

from .models import Season


def sync_season_is_active():
    today = localdate()
    active_ids = set(Season.objects.for_date(today).values_list("id", flat=True))
    for s in Season.objects.all():
        should_be = s.id in active_ids
        if s.is_active != should_be:
            s.is_active = should_be
            s.save(update_fields=["is_active"])
