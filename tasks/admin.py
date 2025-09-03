# tasks/admin.py
from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils.html import format_html

from .models import Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "assigned_to",
        "assigned_player",  # 👈 new column
        "status",
        "due_at",
        # "subject_link",
        "complete_on",
        "allow_manual_complete",
        "created_at",
    )
    list_filter = (
        "status",
        "complete_on",
        "allow_manual_complete",
        "assigned_to",
        "created_by",
        "subject_ct",
    )
    search_fields = ("title", "description", "subject_id")
    autocomplete_fields = ("assigned_to", "created_by")
    raw_id_fields = ("subject_ct",)
    readonly_fields = ("created_at", "updated_at", "subject_link_display")

    fieldsets = (
        (
            None,
            {"fields": ("title", "description", ("created_by", "assigned_to"), "status", "due_at")},
        ),
        (
            "Subject (generic link)",
            {
                "fields": ("subject_ct", "subject_id", "subject_link_display"),
                "description": "Choose the content type and enter the object's primary key.",
            },
        ),
        ("Automation", {"fields": ("complete_on", "allow_manual_complete")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    def subject_link_display(self, obj):
        return self.subject_link(obj)

    subject_link_display.short_description = "Subject"

    def subject_link(self, obj):
        if not obj.subject_ct or not obj.subject_id:
            return "—"
        try:
            model = obj.subject_ct.model_class()
            instance = model.objects.filter(pk=obj.subject_id).first()
            if not instance:
                return f"{obj.subject_ct} / {obj.subject_id} (not found)"
            url = reverse(
                f"admin:{obj.subject_ct.app_label}_{obj.subject_ct.model}_change",
                args=[instance.pk],
            )
            return format_html('<a href="{}">{} • {}</a>', url, obj.subject_ct, instance)
        except Exception:
            return f"{obj.subject_ct} / {obj.subject_id}"

    subject_link.short_description = "Subject"

    # 👇 NEW: show a dedicated Player link when subject is a Player
    def assigned_player(self, obj):
        if not obj.subject_ct or not obj.subject_id:
            return "—"
        if obj.subject_ct.app_label == "members" and obj.subject_ct.model == "player":
            model = obj.subject_ct.model_class()
            player = model.objects.filter(pk=obj.subject_id).first()
            if not player:
                return "—"
            url = reverse("admin:members_player_change", args=[player.pk])
            return format_html('<a href="{}">{}</a>', url, player)
        return "—"

    assigned_player.short_description = "Player"

    # (Optional) limit ContentTypes selectable for subject
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        try:
            allowed_apps = ["members", "memberships", "spond_integration", "resources", "tasks"]
            form.base_fields["subject_ct"].queryset = ContentType.objects.filter(
                app_label__in=allowed_apps
            )
        except Exception:
            pass
        return form
