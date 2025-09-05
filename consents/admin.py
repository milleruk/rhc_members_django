from django.contrib import admin

from .models import ConsentLog


@admin.register(ConsentLog)
class ConsentLogAdmin(admin.ModelAdmin):
    list_display = ("user", "consent_type", "given", "created_at", "ip_address")
    list_filter = ("consent_type", "given", "created_at")
    search_fields = ("user__email", "user__username", "ip_address", "user_agent")
    autocomplete_fields = ("user",)
