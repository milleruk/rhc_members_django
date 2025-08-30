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


class SpondEvent(models.Model):
    spond_event_id = models.CharField(max_length=64, unique=True)
    title          = models.CharField(max_length=255, blank=True)          # from "heading"
    description    = models.TextField(blank=True)                           # from "description"
    start_at       = models.DateTimeField(null=True, blank=True)            # from "startTimestamp"
    end_at         = models.DateTimeField(null=True, blank=True)            # from "endTimestamp"
    meetup_at      = models.DateTimeField(null=True, blank=True)            # from "meetupTimestamp" (optional)
    timezone       = models.CharField(max_length=64, blank=True)            # not in sample, kept if appears
    location_name  = models.CharField(max_length=255, blank=True)           # from location.feature
    location_addr  = models.CharField(max_length=512, blank=True)           # from location.address
    location_lat   = models.FloatField(null=True, blank=True)
    location_lng   = models.FloatField(null=True, blank=True)
    group          = models.ForeignKey("SpondGroup", null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name="events")
    subgroups = models.ManyToManyField("SpondGroup", blank=True,
                                       related_name="events_as_subgroup")
    data           = models.JSONField(default=dict, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.title or self.spond_event_id} @ {self.start_at or 'TBA'}"
    

class SpondAttendance(models.Model):
    STATUS = (
        ("going", "Going"),
        ("maybe", "Maybe"),
        ("declined", "Not going"),
        ("attended", "Attended / Checked-in"),
        ("unknown", "Unknown"),
    )
    event         = models.ForeignKey("SpondEvent", on_delete=models.CASCADE, related_name="attendances")
    member        = models.ForeignKey("SpondMember", on_delete=models.CASCADE, related_name="attendances")
    status        = models.CharField(max_length=16, choices=STATUS, default="unknown")
    responded_at  = models.DateTimeField(null=True, blank=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    data          = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = [("event", "member")]

    def __str__(self):
        return f"{self.member} → {self.event}: {self.status}"


class SpondTransaction(models.Model):
    """
    A payment/charge/refund reported by Spond.
    We attach it to the SpondMember (payer) and, if possible, resolve to a Player via PlayerSpondLink.
    """
    spond_txn_id   = models.CharField(max_length=64, unique=True)  # Spond's id
    type           = models.CharField(max_length=32, blank=True)   # e.g. "PAYMENT", "REFUND", "CHARGE"
    status         = models.CharField(max_length=32, blank=True)   # e.g. "COMPLETED", "PENDING", "FAILED"
    description    = models.CharField(max_length=512, blank=True)

    amount_minor   = models.IntegerField(default=0)                 # store in minor units (pennies)
    currency       = models.CharField(max_length=8, default="GBP")

    created_at     = models.DateTimeField(null=True, blank=True)    # when Spond recorded the txn
    settled_at     = models.DateTimeField(null=True, blank=True)

    group          = models.ForeignKey("SpondGroup", null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name="transactions")
    event          = models.ForeignKey("SpondEvent", null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name="transactions")

    member         = models.ForeignKey("SpondMember", null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name="transactions")
    player         = models.ForeignKey("members.Player", null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name="spond_transactions")

    reference      = models.CharField(max_length=128, blank=True)   # external ref / order no if present
    metadata       = models.JSONField(default=dict, blank=True)     # raw Spond transaction payload
    last_synced_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["member"]),
            models.Index(fields=["player"]),
        ]

    def __str__(self):
        amt = f"{self.currency} {self.amount_minor/100:.2f}"
        who = self.player or self.member or "unknown"
        return f"{self.type or 'TXN'} {amt} → {who} ({self.status or 'n/a'})"