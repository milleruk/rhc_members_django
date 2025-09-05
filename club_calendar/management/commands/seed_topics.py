# club_calendar/management/commands/seed_topics.py
from django.core.management.base import BaseCommand

from club_calendar.models import Topic

DEFAULT_TOPICS = [
    ("Training", "#007bff"),
    ("Club Event", "#6f42c1"),
    ("Match", "#dc3545"),
    ("Social", "#fd7e14"),
    ("Meetings", "#28a745"),
    ("Fundraising", "#20c997"),
    ("Junior Development", "#17a2b8"),
    ("Volunteer Duty", "#ffc107"),
    ("Tournament", "#6610f2"),
    ("Other", "#6c757d"),
]


class Command(BaseCommand):
    help = "Seed default Topics for the club calendar"

    def handle(self, *args, **options):
        created_count = 0
        for name, color in DEFAULT_TOPICS:
            topic, created = Topic.objects.get_or_create(
                name=name, defaults={"color": color, "active": True}
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"Created topic: {name}"))
            else:
                self.stdout.write(self.style.WARNING(f"Topic already exists: {name}"))

        self.stdout.write(
            self.style.SUCCESS(f"Seeding complete. {created_count} new topics created.")
        )
