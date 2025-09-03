# Example: when a Player is created, create two generic tasks tied to that Player.
# tasks/signals.py
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from members.models import Player

from .models import Task, TaskStatus


@receiver(post_save, sender=Player)
def create_starter_tasks_for_player(sender, instance: Player, created: bool, **kwargs):
    if not created:
        return
    assigned = getattr(instance, "created_by", None)

    def _create():
        Task.objects.bulk_create(
            [
                Task(
                    title="Complete player profile",
                    description="Please complete the player profile answers for this player.",
                    subject=instance,
                    created_by=assigned,
                    assigned_to=assigned,
                    status=TaskStatus.OPEN,
                    complete_on="profile.completed",
                    allow_manual_complete=False,  # 🔒 system task
                ),
                Task(
                    title="Choose a membership",
                    description="Select and confirm the appropriate membership for this player.",
                    subject=instance,
                    created_by=assigned,
                    assigned_to=assigned,
                    status=TaskStatus.OPEN,
                    complete_on="membership.confirmed",
                    allow_manual_complete=False,  # 🔒 system task
                ),
            ]
        )

    transaction.on_commit(_create)
