from django.conf import settings
from django.db import models
from django.utils import timezone


class ConsentType(models.TextChoices):
    TERMS = "terms", "Terms of Service"
    CLUB = "club", "Club Consent"
    MARKETING = "marketing", "Product Updates"
    ENGLAND_HOCKEY = "england_hockey", "England Hockey Data"


class ConsentLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="consents",
    )
    consent_type = models.CharField(max_length=32, choices=ConsentType.choices)
    given = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")
    version = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ("user", "consent_type")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} · {self.consent_type} · {'given' if self.given else 'not given'}"


def user_has_required_consents(user) -> bool:
    required = {"terms", "club", "england_hockey"}
    qs = user.consents.filter(
        given=True,
        consent_type__in=required,
        version__gte=getattr(settings, "CONSENT_REQUIRED_VERSION", 1),
    )
    return required.issubset(set(qs.values_list("consent_type", flat=True)))
