from django.contrib.auth.models import Group

# Adjust to your project rules.
def can_manage_player(user, player) -> bool:
    if not user.is_authenticated:
        return False
    if getattr(player, "created_by_id", None) == user.id:
        return True
    # Coach/Captain groups are allowed
    return user.groups.filter(name__in=["Coach", "Captain", "Club Admin"]).exists() or user.is_superuser
