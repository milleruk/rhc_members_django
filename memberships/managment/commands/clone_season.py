from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from memberships.models import AddOnFee, MembershipProduct, PaymentPlan, Season


class Command(BaseCommand):
    help = "Clone products/plans/addons from one season to a new season."

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
            help="Target season name (must exist)",
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        src = Season.objects.filter(name=opts["from_name"]).first()
        dst = Season.objects.filter(name=opts["to_name"]).first()
        if not src or not dst:
            raise CommandError("Both source and target seasons must exist.")

        # Map categories (by code) — assume categories are global (not season-specific)
        self.stdout.write(f"Cloning from {src} to {dst}...")
        count_products = 0
        count_plans = 0

        for prod in MembershipProduct.objects.filter(season=src):
            new_prod, created = MembershipProduct.objects.get_or_create(
                season=dst,
                sku=prod.sku,
                defaults=dict(
                    category=prod.category,
                    name=prod.name,
                    list_price_gbp=prod.list_price_gbp,
                    active=prod.active,
                    notes=prod.notes,
                ),
            )
            if created:
                count_products += 1

            for plan in prod.plans.all():
                PaymentPlan.objects.get_or_create(
                    product=new_prod,
                    label=plan.label,
                    defaults=dict(
                        instalment_amount_gbp=plan.instalment_amount_gbp,
                        instalment_count=plan.instalment_count,
                        frequency=plan.frequency,
                        includes_match_fees=plan.includes_match_fees,
                        active=plan.active,
                        display_order=plan.display_order,
                    ),
                )
                count_plans += 1

        for addon in AddOnFee.objects.filter(season=src):
            AddOnFee.objects.get_or_create(
                season=dst,
                name=addon.name,
                defaults=dict(amount_gbp=addon.amount_gbp, active=addon.active),
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. New products: {count_products}, plans cloned: {count_plans}."
            )
        )
