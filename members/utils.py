# members/utils.py
from .models import Team


def get_user_team_ids(user):
    """
    Return team IDs the user is allowed for.
    Update this to match your real relation, e.g.:
      Team.objects.filter(staff_roles__user=user)
      Team.objects.filter(coaches=user)
      user.profile.teams.values_list("id", flat=True)
    """
    return Team.objects.filter(staff_roles__user=user).values_list("id", flat=True)
