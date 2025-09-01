# club/models.py  (better than stuffing inside members)

from django.db import models
from django.utils import timezone


class ClubNotice(models.Model):
    LEVEL_CHOICES = [
        ("info", "Info"),
        ("success", "Success"),
        ("warning", "Warning"),
        ("danger", "Danger"),
    ]

    title = models.CharField(max_length=200)
    text = models.TextField()
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default="info")
    url = models.URLField(blank=True, null=True)

    # Visibility controls
    active = models.BooleanField(default=True)
    valid_from = models.DateField(blank=True, null=True)
    valid_to = models.DateField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def is_current(self):
        today = timezone.now().date()
        if not self.active:
            return False
        if self.valid_from and today < self.valid_from:
            return False
        if self.valid_to and today > self.valid_to:
            return False
        return True


class QuickLink(models.Model):
    label = models.CharField(max_length=100)
    url = models.URLField()
    icon = models.CharField(
        max_length=50,
        blank=True,
        help_text="Optional FontAwesome icon class (e.g. 'fas fa-id-card-alt')",
    )
    sort_order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "label"]

    def __str__(self):
        return self.label
