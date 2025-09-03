from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from members.models import DynamicQuestion, PlayerType

GROUPS = ["Full Access", "Committee", "Captain", "Coach", "Helper"]


class Command(BaseCommand):
    help = "Create default Groups and Player Types"

    def handle(self, *args, **options):
        for g in GROUPS:
            Group.objects.get_or_create(name=g)
        self.stdout.write(self.style.SUCCESS("Groups ensured."))

        senior, _ = PlayerType.objects.get_or_create(name="Senior")
        junior, _ = PlayerType.objects.get_or_create(name="Junior")
        self.stdout.write(self.style.SUCCESS("Player types ensured."))

        # Example question (boolean with detail)
        q, created = DynamicQuestion.objects.get_or_create(
            code="medical_conditions",
            defaults={
                "label": "Any medical conditions we should know about?",
                "question_type": "boolean",
                "required": False,
                "requires_detail_if_yes": True,
                "display_order": 10,
                "active": True,
            },
        )
        if created:
            q.applies_to.set([senior, junior])
            q.save()
            # Make it visible to Committee and Coach by default
            q.visible_to_groups.set(
                Group.objects.filter(name__in=["Full Access", "Committee", "Coach"])
            )
            q.save()
            self.stdout.write(self.style.SUCCESS("Example question created."))
        else:
            self.stdout.write("Example question already exists.")
