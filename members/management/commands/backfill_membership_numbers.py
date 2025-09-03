# members/management/commands/backfill_membership_numbers.py
from django.core.management.base import BaseCommand
from django.db import transaction

from members.models import Player


class Command(BaseCommand):
    help = (
        "Backfill membership_number for Players as zero-padded primary key, e.g. 00001. "
        "By default, only fills missing/blank values. Use --force to overwrite existing."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--digits",
            type=int,
            default=5,
            help="Number of digits for zero-padding (default: 5)",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Overwrite existing membership_number values to match the padded PK.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without writing to the database.",
        )

    def handle(self, *args, digits, force, dry_run, **kwargs):
        updated = 0
        to_update = []

        qs = Player.objects.all().only("id", "membership_number")
        if not force:
            # Only those missing or blank
            qs = qs.filter(membership_number__isnull=True) | qs.filter(membership_number="")

        for p in qs.iterator(chunk_size=1000):
            target = f"{p.pk:0{digits}d}"
            if force:
                if p.membership_number != target:
                    p.membership_number = target
                    to_update.append(p)
            else:
                # Fill only if empty
                if not p.membership_number:
                    p.membership_number = target
                    to_update.append(p)

        if not to_update:
            self.stdout.write(self.style.SUCCESS("Nothing to update."))
            return

        self.stdout.write(f"Prepared {len(to_update)} player(s) for update.")
        if dry_run:
            # Show a small sample for confirmation
            sample = to_update[:10]
            for s in sample:
                self.stdout.write(f"  id={s.pk} -> membership_number={s.membership_number}")
            if len(to_update) > 10:
                self.stdout.write(f"  ... and {len(to_update)-10} more")
            self.stdout.write(self.style.WARNING("Dry run: no changes written."))
            return

        with transaction.atomic():
            Player.objects.bulk_update(to_update, ["membership_number"], batch_size=1000)
            updated = len(to_update)

        self.stdout.write(self.style.SUCCESS(f"Updated {updated} player(s)."))
