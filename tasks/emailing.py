from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.urls import reverse
from django.utils import timezone

from .models import Task, TaskStatus

DIGEST_LOOKAHEAD_DAYS = getattr(settings, "TASKS_DIGEST_LOOKAHEAD_DAYS", 7)

def _build_user_task_map():
    """
    Returns {user: [tasks]} for users with OPEN tasks, prioritizing overdue and due soon.
    """
    now = timezone.now()
    soon = now + timedelta(days=DIGEST_LOOKAHEAD_DAYS)

    qs = (Task.objects
          .select_related("assigned_to")
          .filter(status=TaskStatus.OPEN, assigned_to__isnull=False))

    overdue = qs.filter(due_at__lt=now).order_by("due_at")
    due_soon = qs.filter(due_at__gte=now, due_at__lte=soon).order_by("due_at")
    no_due = qs.filter(due_at__isnull=True).order_by("-created_at")

    user_map = defaultdict(list)
    for bucket in (overdue, due_soon, no_due):
        for t in bucket:
            user_map[t.assigned_to].append(t)
    return user_map

def _send_digest(to_user, tasks):
    if not getattr(to_user, "email", None):
        return 0

    site_name = getattr(settings, "SITE_NAME", "RHC Members")
    site_url = getattr(settings, "SITE_URL", "").rstrip("/")
    list_url = reverse("tasks:my_list")
    base_list_url = f"{site_url}{list_url}" if site_url else list_url

    ctx = {"user": to_user, "tasks": tasks, "base_list_url": base_list_url, "site_name": site_name}
    subject = f"[{site_name}] You have {len(tasks)} open task(s)"

    text_body = render_to_string("emails/tasks/digest.txt", ctx)
    html_body = render_to_string("emails/tasks/digest.html", ctx)

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[to_user.email],
    )
    msg.attach_alternative(html_body, "text/html")
    msg.send()
    return 1
