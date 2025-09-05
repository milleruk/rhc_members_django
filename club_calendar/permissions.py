# hockey_club/calendar/permissions.py


def user_team_ids(user):
    """
    Returns a set of team IDs the current user is tied to via Player.
    Adjust if your Player <-> User relation differs.
    """
    try:
        player = user.player  # e.g. OneToOne from Player to User
        return set(player.teams.values_list("id", flat=True))
    except Exception:
        return set()


def filter_events_for_user(qs, user):
    """
    Visibility logic:
      - Public (no groups and no teams set) => visible to all with view perms
      - Groups-restricted => user must be in at least one of those groups
      - Teams-restricted  => user must be in at least one of those teams
      - If both are set on an event, user must match at least one of the sets
        (group OR team) to see it.
    """
    if user.is_superuser:
        return qs

    user_group_ids = set(user.groups.values_list("id", flat=True))
    u_team_ids = user_team_ids(user)

    # Break into cases:
    public_qs = qs.filter(visible_to_groups__isnull=True, visible_to_teams__isnull=True)

    group_qs = (
        qs.filter(visible_to_groups__in=user_group_ids).distinct() if user_group_ids else qs.none()
    )
    team_qs = qs.filter(visible_to_teams__in=u_team_ids).distinct() if u_team_ids else qs.none()

    return (public_qs | group_qs | team_qs).distinct()
