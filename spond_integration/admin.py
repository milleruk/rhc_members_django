# spond/admin.py
from django.contrib import admin
from .models import SpondMember, PlayerSpondLink, SpondGroup, SpondEvent, SpondAttendance, SpondTransaction

@admin.register(SpondMember)
class SpondMemberAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "spond_member_id", "last_synced_at")
    search_fields = ("full_name", "email", "spond_member_id")
    list_filter = ("last_synced_at",)

@admin.register(PlayerSpondLink)
class PlayerSpondLinkAdmin(admin.ModelAdmin):
    list_display = ("player", "spond_member", "active", "linked_by", "linked_at")
    search_fields = ("player__first_name", "player__last_name", "spond_member__full_name", "spond_member__email")
    list_filter = ("active", "linked_at")

@admin.register(SpondGroup)
class SpondGroupAdmin(admin.ModelAdmin):
    list_display  = ("name", "spond_group_id", "parent")
    search_fields = ("name", "spond_group_id")
    list_filter   = ("parent",)

@admin.register(SpondEvent)
class SpondEventAdmin(admin.ModelAdmin):
    list_display  = (
        "title", "start_at", "group",
        "kind", "is_match",
        "team_name", "opponent_name", "score_display",
        "spond_event_id", "last_synced_at",
    )
    search_fields = ("title", "spond_event_id", "location_name", "location_addr",
                     "team_name", "opponent_name")
    list_filter   = ("group", "kind", "is_match", "match_home_away", "scores_final")
    date_hierarchy = "start_at"

    @admin.display(description="Score")
    def score_display(self, obj):
        return obj.match_score_display or ""

@admin.register(SpondAttendance)
class SpondAttendanceAdmin(admin.ModelAdmin):
    list_display  = ("event", "member", "status", "responded_at", "checked_in_at")
    list_filter   = ("status", "event__group")
    search_fields = ("event__title", "member__full_name", "member__email")


@admin.register(SpondTransaction)
class SpondTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "spond_txn_id", "type", "status", "amount_display",
        "currency", "player", "member", "group", "event", "created_at",
    )
    list_filter = ("status", "type", "currency", "group")
    search_fields = ("spond_txn_id", "description", "reference",
                     "member__full_name", "player__full_name")
    autocomplete_fields = ("player", "member", "group", "event")

    @admin.display(description="Amount")
    def amount_display(self, obj):
        return f"{obj.currency} {obj.amount_minor/100:.2f}"