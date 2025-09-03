from django.contrib import admin

from .models import Incident, IncidentRouting


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "incident_datetime",
        "location",
        "activity_type",
        "team",
        "primary_player",
        "treatment_level",
        "status",
        "submitted_to_eh",
    )
    list_filter = (
        "activity_type",
        "status",
        "treatment_level",
        "submitted_to_eh",
        "suspected_concussion",
        "age_under_18",
    )
    search_fields = ("location", "summary", "description")
    date_hierarchy = "incident_datetime"


@admin.register(IncidentRouting)
class IncidentRoutingAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "reviewer_count")
    list_filter = ("is_active",)
    filter_horizontal = ("reviewers",)

    def reviewer_count(self, obj):
        return obj.reviewers.count()

    reviewer_count.short_description = "Reviewers"
