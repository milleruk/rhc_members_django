# club_calendar/admin.py
from django.contrib import admin
from django.utils.html import format_html

from .models import Event, EventCancellation, Topic


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("name", "color_swatch", "active")
    list_filter = ("active",)
    search_fields = ("name", "description")

    def color_swatch(self, obj):
        return format_html(
            '<span style="display:inline-block;width:18px;height:18px;border-radius:3px;border:1px solid #ddd;background:{};"></span> {}',
            obj.color,
            obj.color,
        )


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "start", "end", "all_day", "topic", "is_recurring")
    list_filter = ("all_day", "topic", "is_recurring", "visible_to_groups", "visible_to_teams")
    search_fields = ("title", "description", "location")
    filter_horizontal = ("visible_to_groups", "visible_to_teams")


@admin.register(EventCancellation)
class EventCancellationAdmin(admin.ModelAdmin):
    list_display = ("event", "occurrence_start")
    search_fields = ("event__title",)
    list_filter = ("event__topic",)
