from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.fields import GenericRelation

import uuid

class PlayerType(models.Model):
    name = models.CharField(max_length=20, unique=True)  # "Senior" / "Junior"

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


RELATION_CHOICES = (
    ("self", "Self"),
    ("additional_adult", "Additional adult"),
    ("child", "Child (under 18)"),
)

GENDER_CHOICES = (
    ("male", "Male"),
    ("female", "Female"),
    ("other", "Other / Prefer not to say"),
)


class Player(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="players"
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES, default="other")
    relation = models.CharField(
        max_length=20, choices=RELATION_CHOICES, default="self"
    )
    player_type = models.ForeignKey("PlayerType", on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="player_updates"
    )

    tasks = GenericRelation(
        "tasks.Task",
        content_type_field="subject_ct",
        object_id_field="subject_id",
        related_query_name="player_subject",
    )
    
    membership_number = models.CharField(
        max_length=10,
        unique=True,
        blank=False,
        null=False,
        help_text="Automatically generated sequential membership number"
    )


    class Meta:
        permissions = (
            ("view_staff_area", "Can view staff area"),
            ("view_all_players", "Can view all players"),
        )
        ordering = ["last_name", "first_name"]
        unique_together = ("created_by", "first_name", "last_name", "date_of_birth")

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name} ({self.player_type})"
    
    # Optional centralised permission helper:
    def can_edit(self, user):
        if not getattr(user, "is_authenticated", False):
            return False
        if user.is_superuser or user.is_staff or user.has_perm("members.change_player"):
            return True
        if getattr(self, "created_by_id", None) == user.id:
            return True
        # If you have a guardians M2M, allow them too
        if hasattr(self, "guardians"):
            try:
                if self.guardians.filter(pk=user.pk).exists():
                    return True
            except Exception:
                pass
        return False

    @property
    def age(self) -> int:
        today = timezone.localdate()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day)
            < (self.date_of_birth.month, self.date_of_birth.day)
        )
    
    @property
    def has_active_spond_link(self):
        return self.spond_links.filter(active=True).exists()
    
    # 🚨 Add validation so DOB must be strictly before today

    def clean(self):
        super().clean()
        dob = self.date_of_birth
        if dob is None:
            return

        if dob >= timezone.localdate():
            raise ValidationError({
                "date_of_birth": "Date of birth cannot be today or in the future."
            })
        
    @property
    def active_subscription(self):
        # Adjust related name & fields to your models
        return (
            self.subscriptions  # e.g. related_name='subscriptions'
            .filter(status='active')
            .select_related('product', 'season', 'plan')
            .order_by('-started_at')
            .first()
        )
        
    def save(self, *args, **kwargs):
        creating = self._state.adding and not self.pk
        super().save(*args, **kwargs)  # save first so we have a pk/id

        if creating and not self.membership_number:
            self.membership_number = f"{self.pk:05d}"  # e.g. 00001, 00002
            super().save(update_fields=["membership_number"])


QUESTION_TYPE_CHOICES = (
    ("text", "Text"),
    ("boolean", "Checkbox"),
    ("choice", "Dropdown"),
    ("number", "Number"),
)


class QuestionCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    display_order = models.PositiveIntegerField(default=0)
    description = models.TextField(
        blank=True,
        help_text="Optional detailed description or instructions (Markdown supported)."
    )

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name


class DynamicQuestion(models.Model):
    code = models.SlugField(
        max_length=64,
        unique=True,
        help_text="Stable identifier (e.g. 'medical_conditions')",
    )
    label = models.CharField(max_length=255)
    help_text = models.CharField(max_length=255, blank=True)
    description = models.TextField(
        blank=True,
        help_text="Optional detailed description or instructions (Markdown supported)."
    )
    question_type = models.CharField(
        max_length=10, choices=QUESTION_TYPE_CHOICES, default="text"
    )
    required = models.BooleanField(default=False)
    requires_detail_if_yes = models.BooleanField(
        default=False, help_text="If checkbox is ticked, require additional detail"
    )
    category = models.ForeignKey(
        "QuestionCategory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="questions",
    )
    applies_to = models.ManyToManyField("PlayerType", related_name="questions")
    visible_to_groups = models.ManyToManyField(
        Group, related_name="viewable_questions", blank=True
    )
    display_order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)

    # For choice questions
    choices_text = models.TextField(
        blank=True,
        help_text="For dropdown questions, provide options separated by commas",
    )

    # For numerical questions
    number_min = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Minimum allowed value (optional, numeric questions only)."
    )
    number_max = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Maximum allowed value (optional, numeric questions only)."
    )
    number_step = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="UI step for HTML number input (optional)."
    )

    class Meta:
        ordering = ["display_order", "id"]

    def __str__(self) -> str:
        return self.label

    def get_field_name(self):
        return f"q_{self.pk}"

    def get_detail_field_name(self):
        return f"q_{self.pk}_detail"


class PlayerAnswer(models.Model):
    player = models.ForeignKey(
        "Player", on_delete=models.CASCADE, related_name="answers"
    )
    question = models.ForeignKey(
        "DynamicQuestion", on_delete=models.CASCADE, related_name="answers"
    )
    text_answer = models.TextField(blank=True)
    boolean_answer = models.BooleanField(null=True, blank=True)
    detail_text = models.TextField(blank=True)
    numeric_answer = models.CharField(
        max_length=32, blank=True, null=True,
        help_text="For numeric-style answers (mobile, ID, etc.), stored as string to preserve leading zeros."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("player", "question")

    def __str__(self) -> str:
        return f"{self.player} – {self.question.code}"


# --- Teams & Positions ---
class Team(models.Model):
    name = models.CharField(max_length=80, unique=True)
    description = models.CharField(max_length=255, blank=True)
    active = models.BooleanField(default=True)
    staff = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="managed_teams"
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Position(models.Model):
    name = models.CharField(max_length=40, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class TeamMembership(models.Model):
    team = models.ForeignKey("Team", on_delete=models.CASCADE, related_name="memberships")
    player = models.ForeignKey(
        "Player", on_delete=models.CASCADE, related_name="team_memberships"
    )
    positions = models.ManyToManyField("Position", blank=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        permissions = (
            ("view_team_assignment", "Can View Team Assignments"),
            ("edit_team_assignment", "Can Edit Team Assignments"),
            ("view_access_logs", "Can View Access logs of a player"),
        )
        unique_together = ("team", "player")
        verbose_name = "Team membership"
        verbose_name_plural = "Team memberships"

    def __str__(self) -> str:
        return f"{self.player} → {self.team}"


class PlayerAccessLog(models.Model):
    player = models.ForeignKey(
        "Player", on_delete=models.CASCADE, related_name="access_logs"
    )
    accessed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    accessed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-accessed_at"]

    def __str__(self):
        return f"{self.accessed_by} viewed {self.player} at {self.accessed_at:%Y-%m-%d %H:%M}"

class Notice(models.Model):
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    audience = models.CharField(
        max_length=50,
        choices=[("all","All"), ("senior","Senior"), ("junior","Junior")],
        default="all"
    )
    active = models.BooleanField(default=True)
    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)
    pinned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-pinned", "-created_at"]

class DirectMessage(models.Model):
    to_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    subject = models.CharField(max_length=200)
    body = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    attachment = models.FileField(upload_to="messages/", blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]