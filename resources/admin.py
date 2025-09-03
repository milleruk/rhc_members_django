from django.contrib import admin

from .models import Document, Policy


@admin.register(Policy)
class PolicyAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "is_active", "published_at")
    list_filter = ("is_active", "category")
    search_fields = ("title", "category", "body")


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "is_active", "created_at")
    list_filter = ("is_active", "category")
    search_fields = ("title", "category", "description")
