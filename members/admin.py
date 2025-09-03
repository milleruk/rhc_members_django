from django.contrib import admin
from .models import (
    Player,
    PlayerType,
    DynamicQuestion,
    PlayerAnswer,
    Team,
    Position,
    TeamMembership,
    PlayerAccessLog,
    QuestionCategory,
)

@admin.register(PlayerType)
class PlayerTypeAdmin(admin.ModelAdmin):
    list_display = ("name",)

@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ("public_id", "first_name", "last_name", "player_type", "relation", "created_by", "created_at")
    readonly_fields = ("public_id",)
    search_fields = ("first_name", "last_name", "created_by__username", "created_by__email")
    list_filter = ("player_type", "relation")

@admin.register(QuestionCategory)
class QuestionCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "display_order")
    ordering = ("display_order",)

@admin.register(DynamicQuestion)
class DynamicQuestionAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "label",
        "question_type",
        "required",
        "requires_detail_if_yes",
        "category",
        "display_order",
        "active",
    )
    list_filter = ("question_type", "required", "active", "applies_to", "category")
    search_fields = ("code", "label")
    filter_horizontal = ("applies_to", "visible_to_groups")

@admin.register(PlayerAnswer)
class PlayerAnswerAdmin(admin.ModelAdmin):
    list_display = ("player", "question", "boolean_answer", "short_text")
    list_select_related = ("player", "question")
    search_fields = ("player__first_name", "player__last_name", "question__label", "text_answer")

    def short_text(self, obj):
        return (obj.text_answer or obj.detail_text)[:60]

@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "active")
    list_filter = ("active",)
    filter_horizontal = ("staff",)
    search_fields = ("name",)

@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)

@admin.register(TeamMembership)
class TeamMembershipAdmin(admin.ModelAdmin):
    list_display = ("team", "player", "assigned_by", "assigned_at")
    list_filter = ("team",)
    search_fields = ("player__first_name", "player__last_name", "team__name")
    filter_horizontal = ("positions",)

@admin.register(PlayerAccessLog)
class PlayerAccessLogAdmin(admin.ModelAdmin):
    list_display = ("player", "accessed_by", "accessed_at")
    list_filter = ("accessed_at", "accessed_by")
    search_fields = ("player__first_name", "player__last_name", "accessed_by__username")


# ──────────────────────────────────────────────────────────────────────────────
# Integrate django-hijack with the Django User admin
# (Fixes: "User is not registered in the default admin..." warning)
# ──────────────────────────────────────────────────────────────────────────────
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from hijack.contrib.admin import HijackUserAdminMixin

User = get_user_model()

# Unregister the default User admin (registered by django.contrib.auth)
try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass

# Re-register with Hijack integration
@admin.register(User)
class CustomUserAdmin(HijackUserAdminMixin, UserAdmin):
    """User admin with django-hijack integration."""
    pass
