from django.conf import settings
from django.core.management.base import BaseCommand

# Import the helpers that build + send the emails
# (create emailing.py as below if you haven't yet)
from tasks.emailing import _build_user_task_map, _send_digest


class Command(BaseCommand):
    help = "Send daily task digest emails to users with open tasks."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Build digests but do not send emails.",
        )

    def handle(self, *args, **options):
        if not getattr(settings, "TASKS_DIGEST_ENABLED", True):
            self.stdout.write(self.style.WARNING("TASKS_DIGEST_ENABLED is False — skipping."))
            return

        dry = options["dry_run"]
        user_map = _build_user_task_map()
        if not user_map:
            self.stdout.write("No users with open tasks. Nothing to send.")
            return

        sent = 0
        for user, tasks in user_map.items():
            if dry:
                self.stdout.write(f"[DRY] Would send {len(tasks)} task(s) to {user} <{user.email}>")
            else:
                sent += _send_digest(user, tasks)

        if dry:
            self.stdout.write(
                self.style.SUCCESS(f"[DRY] Built digests for {len(user_map)} user(s).")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Sent {sent} email(s) to {len(user_map)} user(s).")
            )
