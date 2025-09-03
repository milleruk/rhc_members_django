# tasks/context_processors.py
from urllib.parse import urlencode

from django.urls import reverse
from django.utils import timezone

from .models import Task, TaskStatus


def task_counts(request):
    if not request.user.is_authenticated:
        return {}
    return {
        "open_task_count": Task.objects.filter(
            assigned_to=request.user, status=TaskStatus.OPEN
        ).count()
    }


def task_header(request):
    if not request.user.is_authenticated:
        return {}

    qs = Task.objects.filter(assigned_to=request.user, status=TaskStatus.OPEN).order_by(
        "due_at", "-created_at"
    )
    now = timezone.now()

    overdue = list(qs.filter(due_at__lt=now)[:6])
    upcoming = list(qs.filter(due_at__gte=now)[: max(0, 6 - len(overdue))])
    nodue = list(qs.filter(due_at__isnull=True)[: max(0, 6 - len(overdue) - len(upcoming))])
    items = overdue + upcoming + nodue

    base_list_url = reverse("tasks:my_list")

    dropdown = []
    for t in items:
        # /tasks/?status=open&focus=<id>
        query = urlencode({"status": "open", "focus": t.id})
        dropdown.append(
            {
                "id": t.id,
                "title": t.title,
                "subject": str(t.subject) if t.subject else "",
                "due_at": t.due_at,
                "overdue": bool(t.due_at and t.due_at < now),
                "url": f"{base_list_url}?{query}",
            }
        )

    return {
        "open_task_count": qs.count(),
        "task_notifications": dropdown,
    }
