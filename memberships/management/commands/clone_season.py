from __future__ import annotations

import datetime as dt

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Prefetch

from memberships.models import (
    AddOnFee,
    MatchFeeTariff,
    MembershipProduct,
    PaymentPlan,
    Season,
)


def _shift_year(d: dt.date, years: int = 1) -> dt.date:
    """Shift date by whole years, handling Feb 29 gracefully."""
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        # 29 Feb → 28 Feb if next year not leap
        return d.replace(month=2, day=28, year=d.year + years)


class Command(BaseCommand):
    help = (
        "Clone a season's products, payment plans, add-on fees, and match fee tariffs to another season.\n"
        "By default, creates any missing rows in the target. Use --overwrite to update existing rows.\n"
        "Use --dry-run to preview changes without writing. Use --create-target to auto-create the target season."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--from",
            dest="from_name",
            required=True,
            help="Source season name (e.g. 2024/25)",
        )
        parser.add_argument(
            "--to",
            dest="to_name",
            required=True,
            help="Target season name (must exist unless --create-target is used)",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Update existing target rows to match source values (default: leave them).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview what would be created/updated without saving.",
        )
        parser.add_argument(
            "--create-target",
            action="store_true",
            help="Auto-create the target season using source dates shifted by +1 year and is_active=False.",
        )
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help="Also clone inactive plans/add-ons/fees. (Products are always cloned regardless of active.)",
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        from_name = opts["from_name"]
        to_name = opts["to_name"]
        overwrite = opts["overwrite"]
        dry_run = opts["dry_run"]
        create_target = opts["create_target"]
        include_inactive = opts["include_inactive"]

        src = Season.objects.filter(name=from_name).first()
        if not src:
            raise CommandError(f"Source season '{from_name}' not found.")

        dst = Season.objects.filter(name=to_name).first()
        if not dst:
            if not create_target:
                raise CommandError(
                    f"Target season '{to_name}' not found. "
                    f"Create it first or pass --create-target."
                )
            # Create target with dates shifted by +1 year from source
            dst = Season.objects.create(
                name=to_name,
                start=_shift_year(src.start, 1),
                end=_shift_year(src.end, 1),
                is_active=False,
            )
            self.stdout.write(
                self.style.NOTICE(
                    f"Created target season '{to_name}' "
                    f"({dst.start} → {dst.end}, is_active=False)."
                )
            )

        self.stdout.write(f"Cloning from {src.name} → {dst.name}...")
        created_products = updated_products = 0
        created_plans = updated_plans = 0
        created_addons = updated_addons = 0
        created_fees = updated_fees = 0

        # --------- PRODUCTS + PLANS ----------
        prod_qs = (
            MembershipProduct.objects.filter(season=src)
            .select_related("category")
            .prefetch_related(
                Prefetch("plans", queryset=PaymentPlan.objects.order_by("display_order", "id"))
            )
            .order_by("id")
        )

        for prod in prod_qs:
            prod_defaults = dict(
                category=prod.category,
                name=prod.name,
                list_price_gbp=prod.list_price_gbp,
                active=prod.active,
                notes=prod.notes,
                requires_plan=getattr(prod, "requires_plan", True),
                pay_per_match=getattr(prod, "pay_per_match", False),
            )

            tgt_prod, created = MembershipProduct.objects.get_or_create(
                season=dst,
                sku=prod.sku,
                defaults=prod_defaults,
            )
            if created:
                created_products += 1
            else:
                if overwrite:
                    for k, v in prod_defaults.items():
                        setattr(tgt_prod, k, v)
                    tgt_prod.save()
                    updated_products += 1

            # Payment plans
            for plan in prod.plans.all():
                if not include_inactive and not plan.active:
                    # keep behavior simple: still clone inactive by default; uncomment to skip:
                    # continue
                    pass
                plan_defaults = dict(
                    instalment_amount_gbp=plan.instalment_amount_gbp,
                    instalment_count=plan.instalment_count,
                    frequency=plan.frequency,
                    includes_match_fees=plan.includes_match_fees,
                    active=plan.active,
                    display_order=plan.display_order,
                )
                tgt_plan, plan_created = PaymentPlan.objects.get_or_create(
                    product=tgt_prod,
                    label=plan.label,
                    defaults=plan_defaults,
                )
                if plan_created:
                    created_plans += 1
                else:
                    if overwrite:
                        for k, v in plan_defaults.items():
                            setattr(tgt_plan, k, v)
                        tgt_plan.save()
                        updated_plans += 1

        # --------- ADD-ON FEES ----------
        addon_qs = AddOnFee.objects.filter(season=src).order_by("id")
        # If you truly want to skip inactive by default, filter(active=True) here.
        for addon in addon_qs:
            if not include_inactive and not addon.active:
                # same note as plans; currently we still clone
                pass
            addon_defaults = dict(
                amount_gbp=addon.amount_gbp,
                active=addon.active,
            )
            tgt_addon, created = AddOnFee.objects.get_or_create(
                season=dst,
                name=addon.name,
                defaults=addon_defaults,
            )
            if created:
                created_addons += 1
            else:
                if overwrite:
                    for k, v in addon_defaults.items():
                        setattr(tgt_addon, k, v)
                    tgt_addon.save()
                    updated_addons += 1

        # --------- MATCH FEE TARIFFS ----------
        fee_qs = (
            MatchFeeTariff.objects.filter(season=src)
            .select_related("category", "product")
            .order_by("id")
        )
        for fee in fee_qs:
            if not include_inactive and not fee.active:
                # same note; currently still clone
                pass

            tgt_product = None
            if fee.product_id:
                tgt_product = MembershipProduct.objects.filter(
                    season=dst, sku=fee.product.sku
                ).first()
                if not tgt_product:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Skipping match fee '{fee.name}' scoped to product '{fee.product.sku}' "
                            f"(no target product in {dst.name})."
                        )
                    )
                    continue

            tgt_category = fee.category if fee.category_id else None  # categories are global

            fee_defaults = dict(
                amount_gbp=fee.amount_gbp,
                is_default=fee.is_default,
                active=fee.active,
            )
            tgt_fee, created = MatchFeeTariff.objects.get_or_create(
                season=dst,
                name=fee.name,
                category=tgt_category,
                product=tgt_product,
                defaults=fee_defaults,
            )
            if created:
                created_fees += 1
            else:
                if overwrite:
                    for k, v in fee_defaults.items():
                        setattr(tgt_fee, k, v)
                    tgt_fee.save()
                    updated_fees += 1

        # --------- SUMMARY ----------
        summary = (
            "Clone complete.\n"
            f"- Products:  +{created_products}"
            + (f", updated {updated_products}" if overwrite else "")
            + "\n"
            f"- Plans:     +{created_plans}"
            + (f", updated {updated_plans}" if overwrite else "")
            + "\n"
            f"- Add-ons:   +{created_addons}"
            + (f", updated {updated_addons}" if overwrite else "")
            + "\n"
            f"- MatchFees: +{created_fees}" + (f", updated {updated_fees}" if overwrite else "")
        )
        if dry_run:
            # rollback the transaction while still printing a nice “dry-run complete” as a CommandError
            raise CommandError("DRY RUN — NO CHANGES WRITTEN\n\n" + summary)

        self.stdout.write(self.style.SUCCESS(summary))
