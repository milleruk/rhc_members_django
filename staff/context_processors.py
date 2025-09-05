# hockey_club/staff/context_processors.py
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
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
