from django.contrib import admin
from .models import Policy, Document, Task


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


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "priority", "due_date", "assigned_to")
    list_filter = ("status", "priority", "assigned_to")
    search_fields = ("title", "description")
