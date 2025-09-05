# hockey_club/staff/context_processors.py
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.db.models import Exists, OuterRef
from django.urls import reverse
from django.utils.timezone import localdate


def pending_subscriptions_badge(request):
    """
    Adds pending subscription info for staff navbar/sidebar.
    Returns:
      - pending_membership_count (int)
      - pending_subscriptions    (list of dicts for dropdown)
    """
    user = getattr(request, "user", None)
    if not user or isinstance(user, AnonymousUser):
        return {}

    # Permission gate
    if not (user.is_staff or user.has_perm("memberships.activate_subscription")):
        return {}

    try:
        from memberships.models import Season, Subscription
    except Exception:
        return {}

    today = localdate()
    season = Season.objects.selectable(today) or Season.objects.filter(is_active=True).first()

    cache_key = f"pending_subs_nav:{user.pk}:{season.pk if season else 'none'}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # Build queryset
    qs = Subscription.objects.filter(status="pending")
    if season:
        qs = qs.filter(season=season)
    qs = qs.select_related("player", "product").order_by("started_at")

    count = qs.count()

    # Limit to a handful of items for dropdown
    LIMIT = 6
    items = []
    for sub in qs[:LIMIT]:
        items.append(
            {
                "url": reverse("staff:memberships_list")
                + f"#sub-{sub.id}",  # or a detail URL if you have one
                "player": getattr(sub.player, "full_name", str(sub.player)),
                "product": str(sub.product),
                "season": str(sub.season),
                "started_at": sub.started_at,
            }
        )

    data = {
        "pending_membership_count": count,
        "pending_subscriptions": items,
    }
    cache.set(cache_key, data, 20)  # short cache
    return data


def memberships_overview_gaps(request):
    """
    Exposes:
      - missing_sub_count      (int)
      - missing_sub_players    (list[dict])
    Players who DO NOT have a current (pending or active) subscription for the current season.
    """
    user = getattr(request, "user", None)
    if not user or isinstance(user, AnonymousUser):
        return {}

    # Staff-only (adjust if you want a different perm)
    if not (user.is_staff or user.has_perm("members.view_staff_area")):
        return {}

    try:
        from members.models import Player
        from memberships.models import Season, Subscription
    except Exception:
        return {}

    today = localdate()
    # You asked for the "current active season" specifically:
    season = Season.objects.filter(is_active=True).first() or Season.objects.selectable(today)

    cache_key = f"missing_subs:{season.pk if season else 'none'}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # Players who have a PENDING or ACTIVE sub in the current season
    has_current_sub = Exists(
        Subscription.objects.filter(
            player_id=OuterRef("pk"),
            season=(
                season if season else OuterRef("season")
            ),  # if no season found, this becomes a no-op
            status__in=["pending", "active"],
        )
    )

    # Players with NO current sub
    qs = (
        Player.objects.annotate(_has_current_sub=has_current_sub)
        .filter(_has_current_sub=False)
        .order_by("last_name", "first_name")
    )

    count = qs.count()

    # Small list for overview (link wherever you start/assign a subscription)
    LIMIT = 8
    items = []
    for p in qs[:LIMIT]:
        items.append(
            {
                "url": reverse("staff:player_list")
                + f"#player-{p.pk}",  # or a staff player detail / start-sub page
                "player": getattr(p, "full_name", str(p)),
                "player_id": p.pk,
            }
        )

    data = {
        "missing_sub_count": count,
        "missing_sub_players": items,
    }
    cache.set(cache_key, data, 30)
    return data
