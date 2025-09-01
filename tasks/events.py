# tasks/events.py
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from .models import Task, TaskStatus

def emit(event_name: str, *, subject, actor=None, **context) -> int:
    """
    Generic domain event. Completes any OPEN tasks where:
      - complete_on == event_name
      - subject matches (same content type + pk)

    Returns the count of tasks completed.
    """
    if subject is None:
        return 0
    ct = ContentType.objects.get_for_model(subject, for_concrete_model=False)
    # normalize pk to string (supports UUID/int)
    sid = str(getattr(subject, "pk", getattr(subject, "id", None)))
    if not sid:
        return 0

    updated = Task.objects.filter(
        status=TaskStatus.OPEN,
        complete_on=event_name,
        subject_ct=ct,
        subject_id=sid,
    ).update(status=TaskStatus.DONE, updated_at=timezone.now())
    return updated
