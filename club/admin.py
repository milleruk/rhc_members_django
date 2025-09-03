# club/admin.py
from django.contrib import admin

from .models import ClubNotice, QuickLink


@admin.register(ClubNotice)
class ClubNoticeAdmin(admin.ModelAdmin):
    list_display = ("title", "level", "active", "valid_from", "valid_to", "created_at")
    list_filter = ("level", "active")
    search_fields = ("title", "text")
    date_hierarchy = "created_at"

    fieldsets = (
        (None, {"fields": ("title", "text", "level", "active")}),
        (
            "Optional link",
            {
                "fields": ("url",),
                "classes": ("collapse",),
            },
        ),
        (
            "Visibility",
            {
                "fields": ("valid_from", "valid_to"),
            },
        ),
    )


@admin.register(QuickLink)
class QuickLinkAdmin(admin.ModelAdmin):
    list_display = ("label", "url", "icon", "sort_order", "active")
    list_editable = ("sort_order", "active")
    search_fields = ("label", "url", "icon")
