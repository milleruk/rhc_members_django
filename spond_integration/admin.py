# spond/admin.py
from django.contrib import admin
from .models import SpondMember, PlayerSpondLink, SpondGroup, SpondEvent, SpondAttendance

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
    list_display  = ("title", "start_at", "group", "spond_event_id", "last_synced_at")
    search_fields = ("title", "spond_event_id", "location_name", "location_addr")
    list_filter   = ("group",)
    date_hierarchy = "start_at"

@admin.register(SpondAttendance)
class SpondAttendanceAdmin(admin.ModelAdmin):
    list_display  = ("event", "member", "status", "responded_at", "checked_in_at")
    list_filter   = ("status", "event__group")
    search_fields = ("event__title", "member__full_name", "member__email")