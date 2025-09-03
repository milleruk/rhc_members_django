# hockey_club/admin_celery.py
from __future__ import annotations

import json

from django.contrib import admin, messages
from django.core.management import call_command
from django.shortcuts import redirect
from django.urls import path
from django.utils.html import format_html

from hockey_club.celery import app as celery_app

from .models_celery import (
    BeatClockedSchedule,
    BeatCrontabSchedule,
    BeatIntervalSchedule,
    BeatPeriodicTask,
    BeatSolarSchedule,
)


# ---------- Shared Mixin: "Sync from settings" button ----------
class SyncFromSettingsMixin:
    """
    Adds a 'Sync from settings' link in the admin changelist toolbar.
    This calls the management command that mirrors settings.py -> django-celery-beat.
    """

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "sync-from-settings/",
                self.admin_site.admin_view(self.sync_now),
                name="beat_sync_now",
            ),
        ]
        return custom + urls

    def sync_now(self, request):
        try:
            call_command("sync_beat_from_settings")
            self.message_user(request, "Synced Periodic Tasks from settings.py.")
        except Exception as e:
            self.message_user(request, f"Sync failed: {e}", level=messages.ERROR)
        return redirect("..")


# ---------- Periodic Tasks ----------
@admin.register(BeatPeriodicTask)
class BeatPeriodicTaskAdmin(SyncFromSettingsMixin, admin.ModelAdmin):
    list_display = (
        "name",
        "task",
        "enabled",
        "schedule_display",
        "last_run_at",
        "one_off",
        "queue",
    )
    list_filter = (
        "enabled",
        "one_off",
        "queue",
        "crontab",
        "interval",
        "solar",
        "clocked",
    )
    search_fields = ("name", "task")
    actions = ["run_selected_now"]

    @admin.display(description="Schedule")
    def schedule_display(self, obj):
        if obj.crontab_id:
            return f"crontab {obj.crontab}"
        if obj.interval_id:
            return f"every {obj.interval.every} {obj.interval.period}"
        if obj.solar_id:
            return f"solar {obj.solar}"
        if obj.clocked_id:
            return f"at {obj.clocked.clocked_time}"
        return "-"

    def run_selected_now(self, request, queryset):
        """
        Enqueue the selected periodic tasks immediately, respecting their 'queue' and args/kwargs.
        """
        sent = 0
        for pt in queryset:
            try:
                args = json.loads(pt.args or "[]")
                kwargs = json.loads(pt.kwargs or "{}")
                send_kwargs = {}
                if pt.queue:
                    send_kwargs["queue"] = pt.queue

                # ✅ enqueue with your project's Celery app,
                # and show the task id + queue in an admin message
                result = celery_app.send_task(pt.task, args=args, kwargs=kwargs, **send_kwargs)
                messages.info(
                    request,
                    f"Enqueued '{pt.name}' as task_id={result.id} queue={send_kwargs.get('queue') or 'default'}",
                )
                sent += 1
            except Exception as e:
                messages.error(request, f"Failed to enqueue '{pt.name}': {e}")
        if sent:
            messages.success(request, f"Enqueued {sent} task(s).")

    run_selected_now.short_description = "Run selected now"


# ---------- Schedules ----------
@admin.register(BeatCrontabSchedule)
class BeatCrontabScheduleAdmin(admin.ModelAdmin):
    list_display = (
        "minute",
        "hour",
        "day_of_week",
        "day_of_month",
        "month_of_year",
        "timezone",
    )
    search_fields = (
        "minute",
        "hour",
        "day_of_week",
        "day_of_month",
        "month_of_year",
        "timezone",
    )


@admin.register(BeatIntervalSchedule)
class BeatIntervalScheduleAdmin(admin.ModelAdmin):
    list_display = ("every", "period")
    list_filter = ("period",)


@admin.register(BeatSolarSchedule)
class BeatSolarScheduleAdmin(admin.ModelAdmin):
    list_display = ("event", "latitude", "longitude")


@admin.register(BeatClockedSchedule)
class BeatClockedScheduleAdmin(admin.ModelAdmin):
    list_display = ("clocked_time",)


# ---------- Optional: Spond task health (only if spond_integration is installed) ----------
try:
    from spond_integration.models import SpondTaskStatus
    from spond_integration.tasks import (
        sync_spond_events,
        sync_spond_members,
        sync_spond_transactions,
    )

    @admin.register(SpondTaskStatus)
    class SpondTaskStatusAdmin(admin.ModelAdmin):
        list_display = (
            "key",
            "task_name",
            "status_badge",
            "last_success_at",
            "last_finished_at",
            "last_duration_ms",
            "run_count_ok",
            "run_count_fail",
            "result_short",
            "run_now_link",
        )
        list_filter = ("last_status",)
        search_fields = ("task_name", "last_result", "last_error")
        readonly_fields = [f.name for f in SpondTaskStatus._meta.fields]
        actions = ["run_selected_now"]

        @admin.display(description="Status")
        def status_badge(self, obj):
            color = {
                "ok": "#2e7d32",
                "error": "#c62828",
                "running": "#1565c0",
                "skipped": "#6d4c41",
                "idle": "#616161",
            }.get(obj.last_status or "idle", "#616161")
            return format_html('<b style="color:{}">{}</b>', color, obj.last_status or "idle")

        @admin.display(description="Result")
        def result_short(self, obj):
            txt = obj.last_error if obj.last_status == "error" else obj.last_result
            return (txt or "")[:120]

        @admin.display(description="Run now")
        def run_now_link(self, obj):
            return format_html('<a class="button" href="{}">Run now</a>', f"./run/{obj.pk}/")

        def get_urls(self):
            urls = super().get_urls()
            custom = [
                path(
                    "run/<int:pk>/",
                    self.admin_site.admin_view(self.run_now_view),
                    name="hockeyclub_spond_run_now",
                ),
            ]
            return custom + urls

        def run_now_view(self, request, pk):
            from django.shortcuts import redirect

            try:
                row = SpondTaskStatus.objects.get(pk=pk)
            except SpondTaskStatus.DoesNotExist:
                messages.error(request, "Task not found.")
                return redirect("..")

            if row.key == SpondTaskStatus.KEY_EVENTS:
                sync_spond_events.delay(14, 120)
            elif row.key == SpondTaskStatus.KEY_MEMBERS:
                sync_spond_members.delay()
            elif row.key == SpondTaskStatus.KEY_TXNS:
                sync_spond_transactions.delay(120, 1)

            messages.success(request, f"Enqueued: {row.get_key_display()}")
            return redirect("..")

        def run_selected_now(self, request, queryset):
            for row in queryset:
                if row.key == SpondTaskStatus.KEY_EVENTS:
                    sync_spond_events.delay(14, 120)
                elif row.key == SpondTaskStatus.KEY_MEMBERS:
                    sync_spond_members.delay()
                elif row.key == SpondTaskStatus.KEY_TXNS:
                    sync_spond_transactions.delay(120, 1)
            messages.success(request, "Enqueued selected tasks.")

except Exception:
    # If spond_integration isn't installed, skip the health admin
    pass
