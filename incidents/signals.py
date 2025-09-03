from django.contrib.auth import get_user_model
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Incident, IncidentRouting

# ---------- Helpers for tasks (adapt to your Task model if needed) ----------


def _get_task_model():
    try:
        from tasks.models import Task

        return Task
    except Exception:
        return None


def _task_title(prefix, incident):
    return f"[{prefix}] Incident #{incident.pk}: {incident.summary[:60]}"


def _incident_link(incident):
    # If you have full domain, you could generate an absolute URL. Relative is fine inside site.
    return incident.get_absolute_url()


def _create_task(
    task_model, title, description, *, assigned_to=None, assignees=None, due_days=0, task_type=None
):
    due_date = (
        timezone.now().date()
        if due_days == 0
        else (timezone.now().date() + timezone.timedelta(days=due_days))
    )

    base = {
        "title": title,
        "description": description,
    }
    if hasattr(task_model, "due_date"):
        base["due_date"] = due_date
    if hasattr(task_model, "allow_manual_complete"):
        base["allow_manual_complete"] = False  # <-- lock manual completion
    if hasattr(task_model, "is_auto"):
        base["is_auto"] = True  # <-- mark as auto/system task
    if hasattr(task_model, "task_type") and task_type:
        base["task_type"] = task_type

    if assignees and hasattr(task_model, "assignees"):
        t = task_model.objects.create(**base)
        t.assignees.add(*assignees)
        return t

    if assigned_to and hasattr(task_model, "assigned_to"):
        base["assigned_to"] = assigned_to

    return task_model.objects.create(**base)


def _close_open_tasks_for_incident(task_model, incident, contains_tag):
    """
    Close/complete any open tasks that look like they're for this incident by title match.
    Adjust if your Task has a better linking mechanism.
    """
    if task_model is None:
        return
    qs = task_model.objects.all()
    if hasattr(task_model, "is_complete"):
        qs = qs.filter(is_complete=False)
    title_like = f"{contains_tag} Incident #{incident.pk}"
    for t in qs:
        if title_like in t.title:
            if hasattr(t, "is_complete"):
                t.is_complete = True
                t.save(update_fields=["is_complete"])
            elif hasattr(t, "completed_at"):
                t.completed_at = timezone.now()
                t.save(update_fields=["completed_at"])
            else:
                # last resort: delete to avoid clutter
                try:
                    t.delete()
                except Exception:
                    pass


# ---------- Track old values so we can detect transitions ----------


@receiver(pre_save, sender=Incident)
def cache_old_state(sender, instance: Incident, **kwargs):
    if not instance.pk:
        instance._old_status = None
        instance._old_assigned_to_id = None
        return
    try:
        old = Incident.objects.get(pk=instance.pk)
        instance._old_status = old.status
        instance._old_assigned_to_id = old.assigned_to_id
    except Incident.DoesNotExist:
        instance._old_status = None
        instance._old_assigned_to_id = None


@receiver(post_save, sender=Incident)
def handle_transitions(sender, instance: Incident, created, **kwargs):
    Task = _get_task_model()
    if Task is None:
        return

    # On create with SUBMITTED -> create review tasks for routing team
    if created and instance.status == Incident.Status.SUBMITTED:
        routings = IncidentRouting.objects.filter(is_active=True)
        reviewer_ids = list(routings.values_list("reviewers__id", flat=True))
        reviewers = get_user_model().objects.filter(id__in=reviewer_ids).distinct()
        if reviewers:
            title = _task_title("REVIEW", instance)
            desc = (
                "A new incident has been submitted and needs review.\n\n"
                f"Location: {instance.location}\n"
                f"Date/Time: {instance.incident_datetime:%Y-%m-%d %H:%M}\n"
                f"Open: {_incident_link(instance)}"
            )
            # ⬇️ EDIT HERE
            _create_task(Task, title, desc, assignees=list(reviewers), task_type="incident_review")

    old_status = getattr(instance, "_old_status", None)

    # SUBMITTED -> ASSIGNED
    if (
        old_status in [None, Incident.Status.SUBMITTED]
    ) and instance.status == Incident.Status.ASSIGNED:
        _close_open_tasks_for_incident(Task, instance, "[REVIEW]")
        if instance.assigned_to:
            title = _task_title("REVIEW (Assigned)", instance)
            desc = (
                "You are assigned to review this incident.\n\n" f"Open: {_incident_link(instance)}"
            )
            # ⬇️ EDIT HERE
            _create_task(
                Task,
                title,
                desc,
                assigned_to=instance.assigned_to,
                task_type="incident_review_assigned",
            )

    # ASSIGNED -> ACTION_REQUIRED
    if (
        old_status == Incident.Status.ASSIGNED
        and instance.status == Incident.Status.ACTION_REQUIRED
    ):
        _close_open_tasks_for_incident(Task, instance, "[REVIEW (Assigned)]")
        if instance.assigned_to:
            title = _task_title("ACTION NEEDED", instance)
            desc = (
                "Follow safeguarding/EH reporting process, add notes, and complete.\n\n"
                f"Open: {_incident_link(instance)}"
            )
            # ⬇️ EDIT HERE
            _create_task(
                Task,
                title,
                desc,
                assigned_to=instance.assigned_to,
                task_type="incident_action_needed",
            )

    # (ASSIGNED or ACTION_REQUIRED) -> CLOSED
    if instance.status == Incident.Status.CLOSED and old_status != Incident.Status.CLOSED:
        for tag in ("[REVIEW]", "[REVIEW (Assigned)]", "[ACTION NEEDED]"):
            _close_open_tasks_for_incident(Task, instance, tag)


@receiver(post_delete, sender=Incident)
def cleanup_tasks_on_delete(sender, instance: Incident, **kwargs):
    Task = _get_task_model()
    if Task is None:
        return

    # If you add a proper FK later (e.g., Task.incident = ForeignKey),
    # replace this with: Task.objects.filter(incident=instance).delete()
    tags = ("[REVIEW]", "[REVIEW (Assigned)]", "[ACTION NEEDED]")
    for tag in tags:
        qs = Task.objects.all()
        title_like = f"{tag} Incident #{instance.pk}"
        for t in qs:
            if title_like in getattr(t, "title", ""):
                try:
                    t.delete()
                except Exception:
                    # fallback: mark complete if deletion not allowed
                    if hasattr(t, "is_complete"):
                        t.is_complete = True
                        t.save(update_fields=["is_complete"])
                    elif hasattr(t, "completed_at"):
                        t.completed_at = timezone.now()
                        t.save(update_fields=["completed_at"])
