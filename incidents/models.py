from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from members.models import Player, Team


class Incident(models.Model):
    class ActivityType(models.TextChoices):
        MATCH = "match", "Match"
        TRAINING = "training", "Training"
        OTHER = "other", "Other"

    class RoleInvolved(models.TextChoices):
        PLAYER = "player", "Player"
        COACH = "coach", "Coach"
        UMPIRE = "umpire", "Umpire"
        VOLUNTEER = "volunteer", "Volunteer"
        SPECTATOR = "spectator", "Spectator"
        OTHER = "other", "Other / Unknown"

    class TreatmentLevel(models.TextChoices):
        NONE = "none", "None"
        FIRST_AID = "first_aid", "First aid specialist"
        HOSPITAL = "hospital", "Hospital treatment"
        GP = "gp", "Subsequent GP visit"

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted (internal)"  # default
        ASSIGNED = "assigned", "Assigned"
        ACTION_REQUIRED = "action_required", "Action Required"
        CLOSED = "closed", "Closed"

    reported_at = models.DateTimeField(default=timezone.now)
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="incidents_reported",
    )

    incident_datetime = models.DateTimeField()
    location = models.CharField(max_length=255)
    activity_type = models.CharField(
        max_length=16, choices=ActivityType.choices, default=ActivityType.MATCH
    )
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True)

    primary_player = models.ForeignKey(
        Player, on_delete=models.SET_NULL, null=True, blank=True, related_name="primary_incidents"
    )
    role_involved = models.CharField(
        max_length=16, choices=RoleInvolved.choices, default=RoleInvolved.PLAYER
    )
    age_under_18 = models.BooleanField(default=False)

    summary = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    suspected_concussion = models.BooleanField(default=False)
    injury_types = models.CharField(max_length=255, blank=True)

    treatment_level = models.CharField(
        max_length=16, choices=TreatmentLevel.choices, default=TreatmentLevel.NONE
    )
    first_aider_name = models.CharField(max_length=255, blank=True)
    first_aider_contact = models.CharField(max_length=255, blank=True)

    attachments = models.FileField(upload_to="incidents/%Y/%m/", blank=True, null=True)

    # Workflow
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED)
    status_notes = models.TextField(blank=True)

    # Assignment
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incidents_assigned",
    )
    assigned_at = models.DateTimeField(null=True, blank=True)

    is_sensitive = models.BooleanField(
        default=False, help_text="Tick if this report contains sensitive information."
    )

    # REVIEW STAGE FIELDS (done during action/review screens)
    safeguarding_notified = models.BooleanField(default=False)
    safeguarding_notes = models.TextField(blank=True)
    submitted_to_eh = models.BooleanField(default=False, help_text="Logged in EH SportSmart")
    eh_submission_datetime = models.DateTimeField(null=True, blank=True)

    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-incident_datetime", "-id"]
        permissions = [
            ("access_app", "Can Access This App"),
            ("submit_incident", "Can Submit Incident Report"),
            ("view_list", "Can See Incident List"),
            ("view_sensitive", "Can View Sensitive Report"),
            ("assign_incident", "Can Assign Incident"),
            ("complete_review", "Can Complete Review"),
            (
                "can_delete_incident",
                "Can Delete Incidents",
            ),  # custom alias besides Django's delete_incident
        ]

    def __str__(self):
        return f"Incident #{self.id} @ {self.location} on {self.incident_datetime:%Y-%m-%d}"

    def get_absolute_url(self):
        return reverse("incidents:detail", args=[self.pk])


class IncidentRouting(models.Model):
    name = models.CharField(max_length=100, default="Default incident review team")
    is_active = models.BooleanField(default=True)
    reviewers = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="incident_routing_reviewers", blank=True
    )

    def __str__(self):
        status = "active" if self.is_active else "inactive"
        return f"{self.name} ({status})"
