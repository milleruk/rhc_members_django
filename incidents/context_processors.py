# incidents/context_processors.py
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.urls import reverse


def navbar_incidents(request):
    """
    Exposes:
      - incidents_open_count        (int)
      - incident_notifications      (list of dicts for dropdown)
    Both derived from the same queryset.
    """
    user = getattr(request, "user", None)
    if not user or isinstance(user, AnonymousUser):
        return {}

    if not user.has_perm("incidents.access_app"):
        return {}

    cache_key = f"inc_nav:{user.pk}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    from incidents.models import Incident  # your model

    # Define "open" statuses for your app
    open_statuses = ["new", "open", "review", "assigned"]  # adjust if needed

    # ✅ Use assigned_to, and order by last_updated
    qs = Incident.objects.filter(status__in=open_statuses, assigned_to=user).order_by(
        "-last_updated", "-id"
    )

    LIMIT = 6
    items = []
    for inc in qs[:LIMIT]:
        items.append(
            {
                "url": reverse("incidents:detail", args=[inc.pk]),
                "number": inc.id,
                "title": getattr(inc, "summary", f"Incident #{inc.id}"),
                "status": inc.status,
                "severity": getattr(inc, "treatment_level", None),  # optional mapping
                "subject": getattr(inc, "team", None) or getattr(inc, "primary_player", None),
                "assignee": (
                    getattr(inc.assigned_to, "get_full_name", lambda: None)()
                    if inc.assigned_to
                    else None
                ),
                "updated_at": inc.last_updated,  # we'll render with naturaltime
            }
        )

    data = {
        "incidents_open_count": qs.count(),
        "incident_notifications": items,
    }
    cache.set(cache_key, data, 20)
    return data
