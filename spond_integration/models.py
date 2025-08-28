# spond/models.py
from django.conf import settings
from django.db import models
from django.utils import timezone

class SpondAccessAnchor(models.Model):
    """
    Anchor model to hold a custom permission that gates access to the Spond features.
    No DB table is created (managed=False).
    """
    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("access_spond_app", "Has Access to Spond App"),
        )

class SpondMember(models.Model):
    spond_member_id = models.CharField(max_length=64, unique=True)
    full_name       = models.CharField(max_length=255)
    email           = models.EmailField(blank=True)
    groups          = models.ManyToManyField("SpondGroup", related_name="members", blank=True)
    data            = models.JSONField(default=dict, blank=True)
    last_synced_at  = models.DateTimeField(null=True, blank=True)
    

    def __str__(self):
        return f"{self.full_name} ({self.email or 'no email'})"

class PlayerSpondLink(models.Model):
    player        = models.ForeignKey("members.Player", on_delete=models.CASCADE, related_name="spond_links")
    spond_member  = models.ForeignKey(SpondMember, on_delete=models.CASCADE, related_name="player_links")
    linked_by     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    linked_at     = models.DateTimeField(default=timezone.now)
    active        = models.BooleanField(default=True)

    class Meta:
        unique_together = [("player", "spond_member")]

    def __str__(self):
        return f"{self.player} ↔ {self.spond_member} ({'active' if self.active else 'inactive'})"
    
class SpondGroup(models.Model):
    spond_group_id = models.CharField(max_length=64, unique=True)
    name           = models.CharField(max_length=255)
    parent         = models.ForeignKey("self", null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name="children")
    data           = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.name
