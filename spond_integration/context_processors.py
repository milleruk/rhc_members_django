# spond_integration/context_processors.py
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.db.models import Exists, OuterRef
from django.urls import reverse
from django.utils.timezone import localdate


def navbar_spond_unlinked(request):
    """
    Exposes:
      - spond_unlinked_count (int)
      - spond_unlinked_players (list of dicts for dropdown)
    Players who:
      * have an ACTIVE subscription in the current/selectable Season, and
      * do NOT have any active PlayerSpondLink.
    """
    user = getattr(request, "user", None)
    if not user or isinstance(user, AnonymousUser):
        return {}

    # Gate to staff users who can work with Spond area (tweak permission to your scheme)
    if not (user.is_staff or user.has_perm("members.view_staff_area")):
        return {}

    try:
        from members.models import Player
        from memberships.models import Season, Subscription
        from spond_integration.models import PlayerSpondLink  # adjust module if needed
    except Exception:
        return {}

    today = localdate()
    season = Season.objects.selectable(today) or Season.objects.filter(is_active=True).first()

    cache_key = f"spond_unlinked_nav:{user.pk}:{season.pk if season else 'none'}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # Subquery: this player has an active Spond link
    has_active_spond_link = Exists(
        PlayerSpondLink.objects.filter(player=OuterRef("pk"), active=True)
    )

    # Subquery: this player has an ACTIVE subscription in this season
    active_sub_in_season = Exists(
        Subscription.objects.filter(
            player_id=OuterRef("pk"),
            status="active",
            **({"season": season} if season else {}),
        )
    )

    # Base queryset: players who meet both conditions (active sub) AND lack any active link
    qs = (
        Player.objects.filter(active_sub_in_season)
        .annotate(_has_link=has_active_spond_link)
        .filter(_has_link=False)
        .order_by("last_name", "first_name")
        .select_related()  # no-op for Player, fine to leave
    )

    count = qs.count()

    # Provide a small list for a dropdown (or use only the count if you prefer)
    LIMIT = 6
    items = []
    for p in qs[:LIMIT]:
        # Make the destinations fit your app:
        # - A "link this player" action on your Spond dashboard, or
        # - Player detail page in staff
        items.append(
            {
                "url": reverse("spond:dashboard") + f"#player-{p.pk}",  # or a staff player detail
                "player": getattr(p, "full_name", str(p)),
                "player_id": p.pk,
            }
        )

    data = {
        "spond_unlinked_count": count,
        "spond_unlinked_players": items,
    }
    cache.set(cache_key, data, 30)  # brief cache
    return data
