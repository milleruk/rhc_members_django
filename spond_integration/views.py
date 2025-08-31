# spond/views.py
from django.contrib.auth.decorators import permission_required
from django.db.models import Count, Q, Prefetch
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.utils.timezone import now
from django.views.generic import TemplateView
from django.utils.decorators import method_decorator
from django.core.paginator import Paginator
from django.conf import settings

from .models import SpondMember, PlayerSpondLink, SpondGroup, SpondEvent
from members.models import Player


import json
from datetime import datetime, timedelta
from .services import SpondClient, run_async, fetch_events_between

try:
    from .models import SpondAttendance  # event, member, status
    HAS_ATTENDANCE = True
except Exception:
    SpondAttendance = None
    HAS_ATTENDANCE = False


ATTENDED_STATUSES = getattr(
    settings,
    "SPOND_ATTENDED_STATUSES",
    ["attended", "present", "checked_in", "yes", "confirmed", "going"],  # customise as you like
)

PERM = "spond_integration.access_spond_app"

def _bool(request, name):
    v = (request.GET.get(name) or "").strip().lower()
    return v in {"1", "true", "yes", "y", "on"}



@require_GET
def can_access(request):
    return JsonResponse({"has_access": request.user.has_perm(PERM)})

@require_GET
@permission_required(PERM, raise_exception=True)
def search_members(request):
    q = (request.GET.get("q") or "").strip()
    qs = SpondMember.objects.all()
    if q:
        qs = qs.filter(Q(full_name__icontains=q) | Q(email__icontains=q))
    results = [
        {
            "id": m.id,
            "spond_member_id": m.spond_member_id,
            "name": m.full_name,
            "email": m.email,
        }
        for m in qs.order_by("full_name")[:25]
    ]
    return JsonResponse({"results": results})

@require_POST
@permission_required(PERM, raise_exception=True)
def link_player(request, player_id: int):
    try:
        player = Player.objects.get(pk=player_id)
    except Player.DoesNotExist:
        return HttpResponseBadRequest("Invalid player")

    try:
        spond_pk = int(request.POST.get("spond_member_pk"))
        sm = SpondMember.objects.get(pk=spond_pk)
    except Exception:
        return HttpResponseBadRequest("Invalid Spond member")

    link, _ = PlayerSpondLink.objects.update_or_create(
        player=player, spond_member=sm, defaults={"linked_by": request.user, "active": True}
    )
    return JsonResponse({"ok": True, "link_id": link.id})

@require_POST
@permission_required(PERM, raise_exception=True)
def unlink_player(request, player_id: int, link_id: int):
    try:
        link = PlayerSpondLink.objects.get(pk=link_id, player_id=player_id)
    except PlayerSpondLink.DoesNotExist:
        return HttpResponseBadRequest("Invalid link")
    link.active = False
    link.save(update_fields=["active"])
    return JsonResponse({"ok": True})


@method_decorator(require_GET, name="dispatch")
class SpondDashboardView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = "spond_integration/dashboard.html"
    permission_required = "spond_integration.access_spond_app"
    raise_exception = True
    PAGE_SIZE = 25

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        q = self.request.GET.get("q", "").strip()
        group_id = self.request.GET.get("group")
        page = self.request.GET.get("page", 1)

        # Groups list + counts
        groups_qs = SpondGroup.objects.all().annotate(member_count=Count("members"))
        if group_id:
            groups_qs = groups_qs.filter(id=group_id)

        # Member filter
        member_filter = Q()
        if q:
            member_filter &= (Q(full_name__icontains=q) | Q(email__icontains=q))
        if group_id:
            member_filter &= Q(groups__id=group_id)

        # Prefetch links
        link_qs = PlayerSpondLink.objects.select_related("player", "spond_member")

        members_qs = (
            SpondMember.objects.filter(member_filter)
            .prefetch_related("groups")
            .prefetch_related(Prefetch("player_links", queryset=link_qs))
            .order_by("full_name")
            .distinct()
        )

        # Optional events (use group/subgroups and start_at/end_at)
        has_events = False
        events_qs = []
        try:
            from .models import SpondEvent  # has fields: start_at, end_at, meetup_at; relations: group (FK), subgroups (M2M)
            events_qs = (
                SpondEvent.objects.all()
                .select_related("group")
                .prefetch_related("subgroups")
                .order_by("start_at")
            )
            if group_id and str(group_id).isdigit():
                gid = int(group_id)
                events_qs = events_qs.filter(Q(group_id=gid) | Q(subgroups__id=gid))
            has_events = True
            upcoming_events = events_qs.filter(start_at__gte=now()).count()
        except Exception:
            has_events = False
            upcoming_events = 0

        # KPIs
        total_groups = SpondGroup.objects.count()
        total_members = SpondMember.objects.count()
        linked_members = SpondMember.objects.filter(player_links__isnull=False).distinct().count()
        unlinked_members = total_members - linked_members

        # Pagination
        paginator = Paginator(members_qs, self.PAGE_SIZE)
        members_page = paginator.get_page(page)

        ctx.update(
            {
                "groups": groups_qs.order_by("name"),
                "members_page": members_page,
                "members_total": total_members,
                "events": events_qs,
                "has_events": has_events,
                "q": q,
                "selected_group": int(group_id) if group_id and str(group_id).isdigit() else None,
                "kpi": {
                    "total_groups": total_groups,
                    "total_members": total_members,
                    "linked_members": linked_members,
                    "unlinked_members": unlinked_members,
                    "upcoming_events": upcoming_events,
                },
                "now": now(),
            }
        )
        return ctx
    

@method_decorator(require_GET, name="dispatch")
class SpondEventsDashboardView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    """
    AdminLTE dashboard listing Spond events with filters & KPIs (using start_at/end_at).
    """
    template_name = "spond_integration/events_dashboard.html"
    permission_required = "spond_integration.access_spond_app"
    raise_exception = True
    PAGE_SIZE = 20

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        q = self.request.GET.get("q", "").strip()
        group_id = self.request.GET.get("group")  # main group or any subgroup
        kind = (self.request.GET.get("kind", "") or "").upper()  # "MATCH" | "EVENT" | ""
        when = self.request.GET.get("when", "upcoming")  # upcoming | past | all
        page = self.request.GET.get("page", 1)
        now_dt = now()

        # Base queryset
        events = (
            SpondEvent.objects.all()
            .select_related("group")
            .prefetch_related("subgroups")
            .order_by("-start_at")
        )

        # Group/Subgroup filter
        if group_id:
            try:
                gid = int(group_id)
                events = events.filter(Q(group_id=gid) | Q(subgroups__id=gid))
            except ValueError:
                pass

        # Title search
        if q:
            events = events.filter(title__icontains=q)

        # Kind filter (MATCH | EVENT)
        if kind in {"MATCH", "EVENT"}:
            events = events.filter(kind=kind)

        # Time filter on start_at
        if when == "upcoming":
            events = events.filter(start_at__gte=now_dt)
        elif when == "past":
            events = events.filter(start_at__lt=now_dt)
        # "all" -> no time filter

        # Attendance prefetch (optional)
        if HAS_ATTENDANCE:
            attendance_prefetch = Prefetch(
                "attendances",
                queryset=(
                    SpondAttendance.objects
                    .select_related("member")
                    .filter(
                        Q(checked_in_at__isnull=False) | Q(status__in=ATTENDED_STATUSES)
                    )
                    .prefetch_related(
                        Prefetch(
                            "member__player_links",
                            queryset=PlayerSpondLink.objects.select_related("player", "spond_member"),
                        )
                    )
                ),
                to_attr="attended_list",   # only *attended* rows
            )
            events = events.prefetch_related(attendance_prefetch)

        # KPIs
        total_events = SpondEvent.objects.count()
        upcoming_events = SpondEvent.objects.filter(start_at__gte=now_dt).count()
        past_events = SpondEvent.objects.filter(start_at__lt=now_dt).count()

        total_attendances = None
        if HAS_ATTENDANCE:
            total_attendances = (
                SpondEvent.objects.annotate(att_count=Count("attendances"))
                .aggregate(c=Count("attendances"))
                .get("c") or 0
            )

        # Pagination
        paginator = Paginator(events.distinct(), self.PAGE_SIZE)
        page_obj = paginator.get_page(page)

        ctx.update(
            {
                "q": q,
                "when": when,
                "selected_group": int(group_id) if group_id and group_id.isdigit() else None,
                "selected_kind": kind if kind in {"MATCH", "EVENT"} else "",
                "groups": SpondGroup.objects.all().annotate(member_count=Count("members")).order_by("name"),
                "events_page": page_obj,
                "HAS_ATTENDANCE": HAS_ATTENDANCE,
                "kpi": {
                    "total_events": total_events,
                    "upcoming_events": upcoming_events,
                    "past_events": past_events,
                    "total_attendances": total_attendances,
                },
                "now": now_dt,
            }
        )
        return ctx
    
@require_GET
@permission_required(PERM, raise_exception=True)
def debug_spond_events_json(request):
    """
    Returns raw events JSON from Spond (no DB writes).
    Query params:
      - days_back (int, default 14)
      - days_forward (int, default 60)
      - limit (int, default 100)
      - only_matches (bool: '1'/'true' to filter events with matchEvent true)
      - pretty (bool: '1'/'true' → pretty-printed response as text/json)
      - keys_only (bool: '1'/'true' → just return union of top-level keys)
    """
    user = getattr(settings, "SPOND_USERNAME", "")
    pwd  = getattr(settings, "SPOND_PASSWORD", "")
    if not user or not pwd:
        return JsonResponse({"error": "SPOND creds missing"}, status=400)

    def _bool(param):
        v = (request.GET.get(param) or "").strip().lower()
        return v in {"1", "true", "yes", "y", "on"}

    try:
        days_back = int(request.GET.get("days_back", 14))
        days_fwd  = int(request.GET.get("days_forward", 60))
    except ValueError:
        return JsonResponse({"error": "Invalid days_back/days_forward"}, status=400)

    try:
        limit = int(request.GET.get("limit", 100))
    except ValueError:
        limit = 100

    only_matches = _bool("only_matches")
    pretty       = _bool("pretty")
    keys_only    = _bool("keys_only")

    start = datetime.now() - timedelta(days=days_back)
    end   = datetime.now() + timedelta(days=days_fwd)

    async def _fetch():
        async with SpondClient(user, pwd) as session:
            return await fetch_events_between(session, start, end) or []

    try:
        events = run_async(_fetch())
    except Exception as e:
        return JsonResponse({"error": f"fetch failed: {e!r}"}, status=500)

    # Optional filter: only events that look like matches
    if only_matches:
        events = [ev for ev in events if ev.get("matchEvent") or ev.get("matchInfo")]

    # Limit results
    events = events[:max(1, limit)]

    # keys_only mode: show union of top-level keys + a quick count
    if keys_only:
        keyset = set()
        for ev in events:
            keyset |= set(ev.keys())
        payload = {
            "count": len(events),
            "top_level_keys": sorted(keyset),
            "sample_first_event_keys": sorted(events[0].keys()) if events else [],
        }
    else:
        # Provide some helpful metadata + sample
        payload = {
            "count": len(events),
            "meta": {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "only_matches": only_matches,
            },
            "items": events,
        }

    if pretty:
        # Pretty text response to make it easy to eyeball in browser
        return HttpResponse(
            json.dumps(payload, indent=2, ensure_ascii=False),
            content_type="application/json; charset=utf-8",
        )
    return JsonResponse(payload, safe=False)

def debug_spond_methods(request):
    """
    Introspect the underlying Spond client: list public callables and probe a few.
    """
    user = getattr(settings, "SPOND_USERNAME", "")
    pwd  = getattr(settings, "SPOND_PASSWORD", "")
    if not user or not pwd:
        return JsonResponse({"error": "SPOND creds missing"}, status=400)

    async def _probe():
        async with SpondClient(user, pwd) as session:
            # Underlying raw client object:
            raw = session._session  # OK in debug
            # List public methods
            methods = []
            for name in sorted(dir(raw)):
                if name.startswith("_"):
                    continue
                attr = getattr(raw, name, None)
                if callable(attr):
                    methods.append(name)

            # Try a few likely event/match methods without arguments
            tried = {}
            for cand in (
                "get_events", "list_events", "fetch_events", "get_calendar",
                "get_matches", "list_matches", "fetch_matches", "fixtures", "get_fixtures",
            ):
                fn = getattr(raw, cand, None)
                if callable(fn):
                    try:
                        res = await fn()
                        count = len(res) if isinstance(res, (list, tuple)) else (len(res or {}) if isinstance(res, dict) else 1)
                        tried[cand] = {"ok": True, "count": count, "type": type(res).__name__}
                    except TypeError as e:
                        tried[cand] = {"ok": False, "error": f"TypeError: {e}"}
                    except Exception as e:
                        tried[cand] = {"ok": False, "error": repr(e)}

            return {"methods": methods, "probe": tried}

    out = run_async(_probe())
    pretty = _bool(request, "pretty")
    if pretty:
        return HttpResponse(json.dumps(out, indent=2, ensure_ascii=False), content_type="application/json; charset=utf-8")
    return JsonResponse(out)


@require_GET
@permission_required(PERM, raise_exception=True)
def debug_spond_call(request):
    """
    Generic passthrough GET: call SpondClient.get_json(path, params)
    Example:
      /spond/debug/call.json?path=/events&pretty=1
      /spond/debug/call.json?path=/calendar&start=...&end=...
    All query params except 'path' and 'pretty' are forwarded as ?params.
    """
    user = getattr(settings, "SPOND_USERNAME", "")
    pwd  = getattr(settings, "SPOND_PASSWORD", "")
    if not user or not pwd:
        return JsonResponse({"error": "SPOND creds missing"}, status=400)

    path = (request.GET.get("path") or "").strip()
    if not path:
        return HttpResponseBadRequest("Missing ?path=/some/endpoint")
    pretty = _bool(request, "pretty")

    # Forward all other query params
    forward = {k: v for k, v in request.GET.items() if k not in {"path", "pretty"}}

    async def _fetch():
        async with SpondClient(user, pwd) as session:
            return await session.get_json(path, params=forward)

    try:
        data = run_async(_fetch())
    except Exception as e:
        return JsonResponse({"error": f"fetch failed: {e!r}", "path": path, "params": forward}, status=500)

    payload = {"path": path, "params": forward, "type": type(data).__name__, "data": data}
    if pretty:
        return HttpResponse(json.dumps(payload, indent=2, ensure_ascii=False), content_type="application/json; charset=utf-8")
    return JsonResponse(payload, safe=False)