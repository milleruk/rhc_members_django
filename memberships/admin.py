from django import forms
from django.contrib import admin

from .models import (
    AddOnFee,
    MatchFeeTariff,
    MembershipCategory,
    MembershipProduct,
    PaymentPlan,
    Season,
    Subscription,
)


class SeasonForm(forms.ModelForm):
    class Meta:
        model = Season
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        # Ensure model.clean() runs
        self.instance.start = cleaned.get("start")
        self.instance.end = cleaned.get("end")
        self.instance.name = cleaned.get("name")
        self.instance.full_clean()  # triggers Season.clean()
        return cleaned


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    form = SeasonForm
    list_display = ("name", "start", "end", "is_active")
    list_editable = ("is_active",)
    search_fields = ("name",)
    ordering = ("-start",)


class PaymentPlanInline(admin.TabularInline):
    model = PaymentPlan
    extra = 1
    fields = (
        "label",
        "instalment_amount_gbp",
        "instalment_count",
        "frequency",
        "includes_match_fees",
        "active",
        "display_order",
    )


@admin.register(PaymentPlan)
class PaymentPlanAdmin(admin.ModelAdmin):
    list_display = (
        "label",
        "product",
        "instalment_amount_gbp",
        "instalment_count",
        "frequency",
        "active",
    )
    list_filter = ("frequency", "active", "product__season", "product__category")
    search_fields = (
        "label",
        "product__name",
        "product__sku",
        "product__season__name",
        "product__category__label",
    )
    autocomplete_fields = ("product",)
    list_select_related = ("product", "product__season", "product__category")


@admin.register(MembershipCategory)
class MembershipCategoryAdmin(admin.ModelAdmin):
    list_display = ("label", "code", "is_selectable")
    list_editable = ("is_selectable",)
    filter_horizontal = ("applies_to",)


@admin.register(AddOnFee)
class AddOnFeeAdmin(admin.ModelAdmin):
    list_display = ("name", "season", "amount_gbp", "active")
    list_filter = ("season", "active")


@admin.register(MembershipProduct)
class MembershipProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "season",
        "category",
        "sku",
        "list_price_gbp",
        "requires_plan",
        "pay_per_match",
        "active",
    )
    list_filter = ("season", "category", "active", "pay_per_match", "requires_plan")
    search_fields = ("name", "sku")
    inlines = [PaymentPlanInline]


@admin.register(MatchFeeTariff)
class MatchFeeTariffAdmin(admin.ModelAdmin):
    list_display = ("name", "season", "category", "product", "amount_gbp", "is_default", "active")
    list_filter = ("season", "category", "product", "active", "is_default")
    search_fields = ("name", "season__name", "category__label", "product__name")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("player", "season", "product", "plan", "status", "started_at")
    list_filter = ("status", "season", "product__category")
    search_fields = ("player__first_name", "player__last_name", "product__name", "external_ref")
    autocomplete_fields = ("player", "product", "plan", "created_by")
    list_select_related = ("season", "product", "product__season", "product__category")
