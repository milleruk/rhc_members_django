# tasks/models.py
from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse, NoReverseMatch
from django.utils.html import format_html
from .utils import reverse_first

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
    
    @property
    def subject_frontend_url(self):
        """
        Best-effort URL to the user-facing page for this task's subject.
        Uses real member-facing routes (UUID public_id for Player).
        """
        obj = getattr(self, "subject", None)
        if not obj:
            return None

        app = obj._meta.app_label
        model = obj._meta.model_name

        # ---- members.Player -> use player_edit (UUID) ----
        if app == "members" and model == "player":
            public_id = getattr(obj, "public_id", None)
            if public_id:
                # You could also add other candidates here if you later add them
                return reverse_first("answer", kwargs={"public_id": public_id})

        # Add more subject types here as your frontend routes exist
        # e.g. memberships.Subscription, etc.

        return None

    @property
    def subject_link(self):
        """
        Render an <a> tag to the frontend subject page if available.
        Fallback: admin link or plain text.
        """
        obj = getattr(self, "subject", None)
        if not obj:
            return None

        url = self.subject_frontend_url
        if url:
            return format_html('<a href="{}">{}</a>', url, str(obj))

        admin_url = getattr(self, "subject_admin_url", None)
        if admin_url:
            return format_html('<a href="{}">{}</a>', admin_url, str(obj))

        return str(obj)

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