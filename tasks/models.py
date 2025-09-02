# tasks/models.py
from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse, NoReverseMatch

class TaskStatus(models.TextChoices):
    OPEN = "open", "Open"
    DONE = "done", "Done"
    DISMISSED = "dismissed", "Dismissed"


class Task(models.Model):

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks_created"
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks_assigned"
    )
    status = models.CharField(max_length=12, choices=TaskStatus.choices, default=TaskStatus.OPEN)
    due_at = models.DateTimeField(null=True, blank=True)

    # Generic subject this task is about (Player, Membership, Event, etc.)
    subject_ct = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    subject_id = models.CharField(max_length=64, null=True, blank=True)  # supports UUID/int/str PKs
    subject = GenericForeignKey("subject_ct", "subject_id")

    # Optional event name that, when emitted for this subject, should auto-complete the task
    complete_on = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="When an event with this name is emitted for the same subject, mark this task DONE.",
    )

    allow_manual_complete = models.BooleanField(
        default=True,
        help_text="If false, users cannot manually complete this task; completion must be automated (or by admin override)."
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("status", "due_at", "-created_at")
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["subject_ct", "subject_id", "status"]),
            models.Index(fields=["complete_on"]),
            models.Index(fields=["subject_ct", "subject_id", "complete_on", "status"]),
        ]
        permissions = [
            ("view_all_tasks", "Can view all tasks"),
        ]

    def __str__(self):
        return self.title

    @property
    def is_overdue(self):
        from django.utils import timezone
        return self.status == TaskStatus.OPEN and self.due_at and self.due_at < timezone.now()

    def subject_admin_url(self):
        """Return admin change URL for the subject if that admin exists, else None."""
        if not self.subject_ct or not self.subject_id:
            return None
        try:
            app_label = self.subject_ct.app_label
            model = self.subject_ct.model  # already lowercased
            return reverse(f"admin:{app_label}_{model}_change", args=[self.subject_id])
        except NoReverseMatch:
            return None
        
    def can_manual_complete(self, user) -> bool:
        """Who can manually complete this task?"""
        if self.status != "open":
            return False
        # admin/staff override
        if user.is_superuser or user.has_perm("tasks.view_all_tasks"):
            return True
        # normal users: only if explicitly allowed AND assigned to them
        return self.allow_manual_complete and self.assigned_to_id == getattr(user, "id", None)