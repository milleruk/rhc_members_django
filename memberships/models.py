from django.conf import settings
from django.db import models


class Season(models.Model):
    name = models.CharField(max_length=32, unique=True)  # "2025/26"
    start = models.DateField()
    end = models.DateField()
    is_active = models.BooleanField(default=False)

    class Meta:
        ordering = ["-start"]

    def __str__(self):
        return self.name


class MembershipCategory(models.Model):
    """High-level buckets like U12, Teen, Senior, Guest."""
    code = models.SlugField(max_length=50, unique=True)
    label = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    applies_to = models.ManyToManyField("members.PlayerType", blank=True)
    is_selectable = models.BooleanField(default=True)

    def __str__(self):
        return self.label


class MembershipProduct(models.Model):
    season = models.ForeignKey(Season, on_delete=models.PROTECT, related_name="products")
    category = models.ForeignKey(MembershipCategory, on_delete=models.PROTECT, related_name="products")
    name = models.CharField(max_length=150)
    sku = models.SlugField(max_length=80)  # unique within a season
    list_price_gbp = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    # Behaviour flags
    requires_plan = models.BooleanField(
        default=True,
        help_text="If false, plan is optional (e.g., £0 guest memberships)."
    )
    pay_per_match = models.BooleanField(
        default=False,
        help_text="If true, a per-match fee also applies in addition to any membership payment."
    )

    class Meta:
        unique_together = ("season", "sku")
        ordering = ["category__label", "name"]

    def __str__(self):
        return f"{self.name} ({self.season})"


FREQUENCY_CHOICES = (
    ("once", "One-off"),
    ("monthly", "Monthly"),
    ("weekly", "Weekly"),
)


class PaymentPlan(models.Model):
    product = models.ForeignKey(MembershipProduct, on_delete=models.CASCADE, related_name="plans")
    label = models.CharField(max_length=120)  # e.g., "£12.50 x 12 months"
    instalment_amount_gbp = models.DecimalField(max_digits=8, decimal_places=2)
    instalment_count = models.PositiveIntegerField()
    frequency = models.CharField(max_length=16, choices=FREQUENCY_CHOICES, default="monthly")
    includes_match_fees = models.BooleanField(default=True)
    active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "id"]

    def __str__(self):
        return f"{self.product} • {self.label}"


class AddOnFee(models.Model):
    season = models.ForeignKey(Season, on_delete=models.PROTECT, related_name="addons")
    name = models.CharField(max_length=80)
    amount_gbp = models.DecimalField(max_digits=6, decimal_places=2)
    active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("season", "name")
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.season}) £{self.amount_gbp}"


class MatchFeeTariff(models.Model):
    """
    Per-match fee, can be scoped to product or category.
    """
    season = models.ForeignKey(Season, on_delete=models.PROTECT, related_name="match_fees")
    name = models.CharField(max_length=80, default="League Match")
    amount_gbp = models.DecimalField(max_digits=6, decimal_places=2)
    category = models.ForeignKey(
        MembershipCategory, null=True, blank=True, on_delete=models.PROTECT, related_name="match_fees"
    )
    product = models.ForeignKey(
        MembershipProduct, null=True, blank=True, on_delete=models.PROTECT, related_name="match_fees"
    )
    is_default = models.BooleanField(default=False)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-product__id", "-category__id", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["season", "name", "category", "product"],
                name="uniq_match_fee_scope"
            )
        ]

    def __str__(self):
        scope = self.product or self.category or self.season
        return f"{self.name} • £{self.amount_gbp} • {scope}"


class Subscription(models.Model):
    STATUS = (
        ("pending", "Pending"),
        ("active", "Active"),
        ("paused", "Paused"),
        ("cancelled", "Cancelled"),
    )

    player = models.ForeignKey("members.Player", on_delete=models.CASCADE, related_name="subscriptions")
    product = models.ForeignKey("MembershipProduct", on_delete=models.PROTECT, related_name="subscriptions")
    plan = models.ForeignKey(
        "PaymentPlan",
        on_delete=models.PROTECT,
        related_name="subscriptions",
        null=True, blank=True
    )

    # Denormalised season for constraints/queries
    season = models.ForeignKey(
        "Season",
        on_delete=models.PROTECT,
        related_name="subscriptions",
        editable=False,
        null=False, blank=False,
    )

    started_at = models.DateField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS, default="pending")
    external_ref = models.CharField(max_length=120, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        permissions = [
            ("activate_subscription", "Can activate a pending subscription"),
            ("set_pending_subscription", "Can set a subscription back to pending"),
            ("cancel_subscription", "Can cancel a subscription"),
        ]

    class Meta:
        ordering = ["-started_at"]
        constraints = [
            # Exactly one pending/active sub per player per season
            models.UniqueConstraint(
                fields=["player", "season"],
                condition=models.Q(status__in=["pending", "active"]),
                name="uniq_player_season_active_sub",
            ),
        ]

    def __str__(self):
        return f"{self.player} → {self.product.name} ({self.product.season}) [{self.get_status_display()}]"

    def clean(self):
        from django.core.exceptions import ValidationError
        # Enforce plan requirement if applicable
        if self.product.requires_plan and self.plan is None:
            raise ValidationError("This product requires a payment plan.")
        # Enforce season alignment
        if self.season_id and self.season_id != self.product.season_id:
            raise ValidationError("Subscription season must match product season.")

    def save(self, *args, **kwargs):
        # Always align denormalised season before saving
        self.season = self.product.season
        super().save(*args, **kwargs)


# === Helper ===
def resolve_match_fee_for(product: MembershipProduct):
    """Find the most specific match fee: product > category > season default."""
    prod_fee = product.match_fees.filter(active=True).first()
    if prod_fee:
        return prod_fee
    cat_fee = product.category.match_fees.filter(active=True).first()
    if cat_fee:
        return cat_fee
    season_default = product.season.match_fees.filter(
        active=True, category__isnull=True, product__isnull=True, is_default=True
    ).first()
    return season_default
