# staff/views.py
from collections import OrderedDict
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
from django.db.models import Count, OuterRef, Q, Subquery
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.utils.timezone import now
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView, TemplateView

from members.forms import TeamAssignmentForm
from members.models import (
    DynamicQuestion,
    Player,
    PlayerAccessLog,
    PlayerType,
    Team,
    TeamMembership,
)

# import from other apps (no circulars)
from memberships.models import Subscription

try:
    from memberships.models import Product, Season
except Exception:
    Product = None
    Season = None

COACH_GROUPS = [
    "Full Access",
    "Committee",
    "Coach",
]  # keep in one place if you share it


# ──────────────────────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _players_in_scope(request):
    """
    Players visible to this staff user.
    Superusers or users with `members.view_all_players` see all.
    Others only see players on teams where they are in Team.staff.
    """
    user = request.user
    players = Player.objects.select_related("player_type").prefetch_related(
        "team_memberships__team"
    )
    if user.is_superuser or user.has_perm("members.view_all_players"):
        return players
    team_ids = Team.objects.filter(staff=user).values_list("id", flat=True)
    return players.filter(team_memberships__team_id__in=team_ids).distinct()


def _current_subqs():
    """Subqueries to annotate a player's latest active/pending subscription."""
    current_qs = Subscription.objects.filter(
        player=OuterRef("pk"), status__in=["active", "pending"]
    ).order_by("-started_at")
    return {
        "curr_status": Subquery(current_qs.values("status")[:1]),
        "curr_product": Subquery(current_qs.values("product__name")[:1]),
        "curr_season": Subquery(current_qs.values("season__name")[:1]),
        "curr_started": Subquery(current_qs.values("started_at")[:1]),
        "curr_id": Subquery(current_qs.values("id")[:1]),
    }


def _season_product_options(players_qs):
    """
    Return lists of seasons and products visible within the staff user's scope,
    as [{'id': .., 'name': ..}, ...]. Uses Season/Product if available, otherwise
    derives distinct values from Subscription to avoid empty dropdowns.
    """
    base_subs = Subscription.objects.filter(player__in=players_qs)

    # Seasons
    try:
        if Season is not None:
            seasons = Season.objects.all().values("id", "name")
        else:
            raise Exception("Season model not available")
    except Exception:
        seasons = base_subs.values("season_id", "season__name").distinct().order_by("season__name")
        seasons = [
            {"id": row["season_id"], "name": row["season__name"] or "—"}
            for row in seasons
            if row["season_id"]
        ]

    # Products
    try:
        if Product is not None:
            products = Product.objects.all().values("id", "name")
        else:
            raise Exception("Product model not available")
    except Exception:
        products = (
            base_subs.values("product_id", "product__name").distinct().order_by("product__name")
        )
        products = [
            {"id": row["product_id"], "name": row["product__name"] or "—"}
            for row in products
            if row["product_id"]
        ]

    # Normalize to simple lists of dicts in both cases
    seasons = [{"id": s["id"], "name": s["name"]} for s in seasons]
    products = [{"id": p["id"], "name": p["name"]} for p in products]
    return seasons, products


def _update_subscription_status(sub, new_status, user):
    old_status = sub.status
    sub.status = new_status
    if new_status == "active" and not sub.started_at:
        sub.started_at = now()
    sub.save(update_fields=["status", "started_at"])
    return old_status, new_status


# ──────────────────────────────────────────────────────────────────────────────
# Admin/Staff: Player list
# ──────────────────────────────────────────────────────────────────────────────


class PlayerListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Player
    template_name = "staff/player_list.html"
    context_object_name = "players"
    permission_required = "members.view_staff_area"
    raise_exception = True

    def _base_qs(self):
        return (
            Player.objects.select_related("player_type", "created_by")
            .prefetch_related("team_memberships__team", "team_memberships__positions")
            .distinct()
        )

    def _get_user_team_ids(self, user):
        return list(Team.objects.filter(staff=user).values_list("id", flat=True))

    def get_queryset(self):
        qs = self._base_qs()
        user = self.request.user
        is_admin_all = user.has_perm("members.view_all_players")

        allowed_team_ids = None
        if not is_admin_all:
            allowed_team_ids = set(self._get_user_team_ids(user))
            if not allowed_team_ids:
                return qs.none()
            qs = qs.filter(team_memberships__team_id__in=allowed_team_ids)

        team_param = (self.request.GET.get("team") or "").strip()
        if team_param:
            if team_param == "none":
                qs = qs.filter(team_memberships__isnull=True) if is_admin_all else qs.none()
            else:
                try:
                    team_id = int(team_param)
                except ValueError:
                    team_id = None
                if team_id:
                    if is_admin_all or (team_id in (allowed_team_ids or set())):
                        qs = qs.filter(team_memberships__team_id=team_id)
                    else:
                        qs = qs.none()

        player_type_id = self.request.GET.get("player_type")
        if player_type_id:
            qs = qs.filter(player_type_id=player_type_id)

        sub_status = (self.request.GET.get("subscription_status") or "").strip().lower()
        if sub_status in {"active", "pending", "paused", "cancelled"}:
            qs = qs.filter(subscriptions__status=sub_status)
        elif sub_status == "none":
            qs = qs.exclude(subscriptions__status__in=["active", "pending"])

        active_sub_qs = Subscription.objects.filter(
            player=OuterRef("pk"), status__in=["active", "pending"]
        ).order_by("-started_at")
        qs = qs.annotate(
            active_sub_product=Subquery(active_sub_qs.values("product__name")[:1]),
            active_sub_status=Subquery(active_sub_qs.values("status")[:1]),
            active_sub_season=Subquery(active_sub_qs.values("season__name")[:1]),
        ).annotate(
            active_spond_count=Count(
                "spond_links", filter=Q(spond_links__active=True), distinct=True
            )
        )

        return qs.distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        players = ctx["players"]
        user = self.request.user
        is_admin_all = user.has_perm("members.view_all_players")
        today = now().date()

        if is_admin_all:
            ctx["teams"] = Team.objects.filter(active=True)
        else:
            team_ids = self._get_user_team_ids(user)
            ctx["teams"] = Team.objects.filter(id__in=team_ids, active=True)

        ctx["player_types"] = PlayerType.objects.all()

        twelve_months_ago = now() - timedelta(days=365)
        ctx["total_players"] = players.count()
        ctx["recent_updates"] = players.filter(updated_at__gte=twelve_months_ago).count()
        ctx["inactive_players"] = players.filter(updated_at__lt=twelve_months_ago).count()

        try:
            gender_map = dict(Player._meta.get_field("gender").flatchoices)
        except Exception:
            gender_map = {}
        raw_gender_counts = players.values("gender").annotate(total=Count("id")).order_by("gender")
        ctx["totals_by_gender"] = {
            (gender_map.get(row["gender"], row["gender"] or "Unspecified")): row["total"]
            for row in raw_gender_counts
        }

        ctx["totals_per_team"] = (
            players.filter(team_memberships__isnull=False)
            .values("team_memberships__team__name")
            .annotate(total=Count("id", distinct=True))
            .order_by("team_memberships__team__name")
        )

        membership_qs = (
            players.values("player_type__name")
            .annotate(total=Count("id"))
            .order_by("player_type__name")
        )
        ctx["membership_breakdown"] = {
            row["player_type__name"] or "Unspecified": row["total"] for row in membership_qs
        }
        ctx["membership_types"] = membership_qs

        age_ranges = {
            "U10": (0, 9),
            "U12": (10, 11),
            "U14": (12, 13),
            "U16": (14, 15),
            "Adults": (16, 200),
        }
        ctx["age_distribution"] = {
            label: sum(
                1 for p in players if getattr(p, "age", None) is not None and lo <= p.age <= hi
            )
            for label, (lo, hi) in age_ranges.items()
        }

        ctx["today_access_logs"] = PlayerAccessLog.objects.filter(accessed_at__date=today).count()

        total_players = ctx["total_players"]
        answered_players = players.filter(answers__isnull=False).distinct().count()
        ctx["questionnaire_completion"] = (
            round((answered_players / total_players) * 100, 1) if total_players else 0
        )

        debug_mode = self.request.GET.get("debug") == "1"
        ctx["debug_mode"] = debug_mode
        if debug_mode:
            team_ids = "ALL" if is_admin_all else list(self._get_user_team_ids(user))
            ctx["debug_global"] = {
                "is_admin_all": is_admin_all,
                "allowed_team_ids": team_ids,
                "visible_players_count": players.count(),
            }
            for p in players:
                tm_summary = []
                ids = set()
                for tm in p.team_memberships.all():
                    ids.add(tm.team_id)
                    tm_summary.append(
                        {
                            "team_id": tm.team_id,
                            "team_name": getattr(tm.team, "name", None),
                            "positions": [pos.name for pos in tm.positions.all()],
                        }
                    )
                user.is_flagged = True
                user.flag_reason = "manual"

        return ctx


# ──────────────────────────────────────────────────────────────────────────────
# Admin/Staff: Player detail
# ──────────────────────────────────────────────────────────────────────────────


# class PlayerDetailView(RequireMFAMixin, LoginRequiredMixin, PermissionRequiredMixin, DetailView):
#
#    def dispatch(self, request, *args, **kwargs):
#        # Debug: see what MFA check returns for this user
#        print("MFA CHECK:", self.user_has_mfa(request.user))
#        return super().dispatch(request, *args, **kwargs)
#
class PlayerDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Player
    pk_url_kwarg = "player_id"
    template_name = "staff/player_detail.html"
    context_object_name = "player"
    permission_required = "members.view_staff_area"
    raise_exception = True

    def _get_user_team_ids(self, user):
        team_ids = set()
        try:
            Team._meta.get_field("staff")
            team_ids.update(Team.objects.filter(staff=user).values_list("id", flat=True))
        except Exception:
            pass
        team_ids.update(
            TeamMembership.objects.filter(assigned_by=user)
            .values_list("team_id", flat=True)
            .distinct()
        )
        return list(team_ids)

    @staticmethod
    def _parse_choices(choices_text: str):
        mapping = {}
        text = choices_text or ""
        for line in [ln.strip() for ln in text.splitlines() if ln.strip()]:
            if "|" in line:
                val, lab = [p.strip() for p in line.split("|", 1)]
            else:
                val, lab = line, line
            mapping[val] = lab
        return mapping

    def get_queryset(self):
        return Player.objects.select_related("player_type", "created_by").prefetch_related(
            "team_memberships__team", "team_memberships__positions"
        )

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        user = self.request.user

        if user.is_superuser or user.has_perm("members.view_all_players"):
            return obj

        allowed_team_ids = self._get_user_team_ids(user)
        if allowed_team_ids and obj.team_memberships.filter(team_id__in=allowed_team_ids).exists():
            return obj

        raise PermissionDenied("You do not have access to this player.")

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        PlayerAccessLog.objects.create(player=self.object, accessed_by=request.user)
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        player: Player = ctx["player"]

        is_super = user.is_superuser
        ctx.update(
            {
                "can_edit_player": is_super,
                "can_delete_player": is_super,
                "show_team_actions": is_super,
                "can_hijack": is_super,
                "player_created_by": getattr(player, "created_by", None),
            }
        )

        active_subs_qs = (
            Subscription.objects.filter(player=player, status="active")
            .select_related("product", "season")
            .order_by("-started_at")
        )

        # Who is allowed to see subs? (set to True if anyone who can view this page may see them)
        can_view_subs = (
            user.is_superuser
            or user.has_perm("memberships.view_subscription")
            or True  # <-- keep True to allow all; remove if you want to gate by perm
        )

        ctx["can_view_subs"] = can_view_subs
        ctx["active_subs"] = active_subs_qs if can_view_subs else Subscription.objects.none()
        ctx["has_active_subs"] = can_view_subs and active_subs_qs.exists()

        questions = (
            DynamicQuestion.objects.filter(active=True, applies_to=player.player_type)
            .select_related("category")
            .order_by("category__display_order", "category__name", "display_order", "id")
        )
        existing = {
            a.question_id: a
            for a in player.answers.select_related("question", "question__category").all()
        }

        grouped = OrderedDict()
        for q in questions:
            ans = existing.get(q.id)
            qtype = getattr(q, "question_type", "text")
            display = "—"
            detail = getattr(ans, "detail_text", "") if ans else ""

            if qtype == "text":
                display = (getattr(ans, "text_answer", None) or "").strip() or "—"
            elif qtype == "boolean":
                bv = getattr(ans, "boolean_answer", None)
                if bv is None and ans is not None:
                    s = str(getattr(ans, "text_answer", "")).strip().lower()
                    bv = s in {"1", "true", "yes", "on", "y"}
                display = "Yes" if bv else "No"
            elif qtype == "number":
                val = None
                for name in (
                    "number_answer",
                    "numeric_answer",
                    "int_answer",
                    "float_answer",
                    "text_answer",
                ):
                    if ans is not None and hasattr(ans, name):
                        val = getattr(ans, name)
                        if val not in (None, ""):
                            break
                display = "—" if val in (None, "") else str(val)
            elif qtype == "choice":
                mapping = self._parse_choices(getattr(q, "choices_text", "") or "")
                raw = None
                for name in (
                    "choice_answer",
                    "choice_value",
                    "selected_value",
                    "text_answer",
                ):
                    if ans is not None and hasattr(ans, name):
                        raw = getattr(ans, name)
                        if raw not in (None, ""):
                            break
                raw_s = "" if raw in (None, "") else str(raw)
                display = mapping.get(raw_s, raw_s or "—")
            else:
                display = (getattr(ans, "text_answer", None) or "").strip() or "—"

            cat = q.category
            key = cat.id if cat else "general"
            if key not in grouped:
                grouped[key] = {
                    "name": cat.name if cat else "General",
                    "description": (
                        (getattr(cat, "description", None) or getattr(cat, "discription", ""))
                        if cat
                        else ""
                    ),
                    "items": [],
                }
            grouped[key]["items"].append(
                {
                    "label": q.label,
                    "description": getattr(q, "description", ""),
                    "type": qtype,
                    "display": display,
                    "detail": detail,
                }
            )

        ctx["readonly_answers"] = grouped
        ctx["memberships"] = player.team_memberships.select_related("team").all()
        ctx["team_form"] = TeamAssignmentForm(player=player)

        logs = player.access_logs.select_related("accessed_by").all()
        paginator = Paginator(logs, 10)
        ctx["log_page"] = paginator.get_page(self.request.GET.get("page"))

        link = player.spond_links.filter(active=True).select_related("spond_member").first()
        ctx["spond_member"] = getattr(link, "spond_member", None)

        attendances_qs = None
        if ctx["spond_member"]:
            attendances_qs = (
                ctx["spond_member"].attendances.select_related("event").order_by("-event__start_at")
            )

        page_number = self.request.GET.get("spond_page", 1)
        if attendances_qs is not None:
            sp_paginator = Paginator(attendances_qs, 25)
            try:
                sp_page_obj = sp_paginator.page(page_number)
            except PageNotAnInteger:
                sp_page_obj = sp_paginator.page(1)
            except EmptyPage:
                sp_page_obj = sp_paginator.page(sp_paginator.num_pages)
        else:
            sp_page_obj = None

        ctx["spond_attendances_page"] = sp_page_obj
        return ctx

    def post(self, request, *args, **kwargs):
        """
        Handle TeamAssignmentForm submissions on the same URL to avoid 405.
        """
        self.object = self.get_object()  # ensures permission checks run
        form = TeamAssignmentForm(request.POST, player=self.object)

        if form.is_valid():
            membership = form.save(commit=False)
            membership.player = self.object
            if hasattr(membership, "assigned_by_id"):
                membership.assigned_by = request.user
            membership.save()
            # save M2M (e.g., positions)
            if hasattr(form, "save_m2m"):
                form.save_m2m()

            messages.success(request, "Team assignment saved.")
            return redirect("staff:player_detail", player_id=self.object.id)

        messages.error(request, "Please fix the errors below.")
        context = self.get_context_data()
        context["team_form"] = form
        return self.render_to_response(context)


# ──────────────────────────────────────────────────────────────────────────────
# Mutations
# ──────────────────────────────────────────────────────────────────────────────


@login_required
@require_POST
def remove_membership(request, membership_id):
    """Remove a team membership — allowed for superusers and select coach groups."""
    membership = get_object_or_404(TeamMembership, id=membership_id)

    if not (
        request.user.is_superuser or request.user.groups.filter(name__in=COACH_GROUPS).exists()
    ):
        return HttpResponseForbidden("Not allowed")

    player_id = membership.player_id
    membership.delete()
    messages.success(request, "Removed from team.")
    return redirect("staff:player_detail", player_id=player_id)


class StaffHomeView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    """
    Lightweight staff dashboard. Keeps dependencies minimal so it won't explode
    if optional apps aren't installed.
    """

    permission_required = "members.view_staff_area"
    raise_exception = True
    template_name = "staff/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        is_admin_all = user.has_perm("members.view_all_players")

        # Scope players
        players = Player.objects.select_related("player_type").prefetch_related(
            "team_memberships__team"
        )
        if not is_admin_all:
            # visible via Team.staff
            team_ids = Team.objects.filter(staff=user).values_list("id", flat=True)
            players = players.filter(team_memberships__team_id__in=team_ids).distinct()

        # Headline metrics
        # last_30 = now() - timedelta(days=30)
        twelve_months = now() - timedelta(days=365)

        total_players = players.count()
        recent_updates = players.filter(updated_at__gte=twelve_months).count()
        inactive_players = players.filter(updated_at__lt=twelve_months).count()

        # Questionnaire completion
        answered_players = players.filter(answers__isnull=False).distinct().count()
        questionnaire_completion = (
            round((answered_players / total_players) * 100, 1) if total_players else 0
        )

        # Subscriptions snapshot (only if memberships app hooked up)
        sub_breakdown = (
            Subscription.objects.filter(player__in=players)
            .values("status")
            .annotate(total=Count("id"))
            .order_by("status")
        )
        subs = {row["status"] or "unknown": row["total"] for row in sub_breakdown}
        active_subs = subs.get("active", 0)
        pending_subs = subs.get("pending", 0)

        # Players by type
        by_type = (
            players.values("player_type__name")
            .annotate(total=Count("id"))
            .order_by("player_type__name")
        )
        player_types = {row["player_type__name"] or "Unspecified": row["total"] for row in by_type}

        # Teams with counts (within visibility)
        teams_with_counts = (
            players.filter(team_memberships__isnull=False)
            .values("team_memberships__team__name")
            .annotate(total=Count("id", distinct=True))
            .order_by("team_memberships__team__name")
        )

        # Recent access logs (today)
        today = now().date()
        today_access_logs = PlayerAccessLog.objects.filter(accessed_at__date=today).count()

        # Upcoming birthdays (next 30 days)
        upcoming = []
        for p in players:
            dob = getattr(p, "date_of_birth", None)
            if not dob:
                continue
            try:
                next_bd = dob.replace(year=today.year)
            except ValueError:
                # handle Feb 29
                next_bd = dob.replace(year=today.year, month=3, day=1)
            if next_bd < today:
                try:
                    next_bd = dob.replace(year=today.year + 1)
                except ValueError:
                    next_bd = dob.replace(year=today.year + 1, month=3, day=1)
            days = (next_bd - today).days
            if 0 <= days <= 30:
                upcoming.append((p, next_bd))
        upcoming = sorted(upcoming, key=lambda t: t[1])[:10]

        ctx.update(
            {
                "is_admin_all": is_admin_all,
                "total_players": total_players,
                "recent_updates": recent_updates,
                "inactive_players": inactive_players,
                "questionnaire_completion": questionnaire_completion,
                "active_subs": active_subs,
                "pending_subs": pending_subs,
                "player_types": player_types,
                "teams_with_counts": teams_with_counts,
                "today_access_logs": today_access_logs,
                "upcoming_birthdays": upcoming,
            }
        )
        return ctx


class MembershipOverviewView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = "members.view_staff_area"
    raise_exception = True
    template_name = "staff/memberships/overview.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        players = _players_in_scope(self.request)

        season_id = self.request.GET.get("season")
        product_id = self.request.GET.get("product")

        sub_filter = Q(player__in=players)
        if season_id and season_id.isdigit():
            sub_filter &= Q(season_id=int(season_id))
        if product_id and product_id.isdigit():
            sub_filter &= Q(product_id=int(product_id))

        subs = Subscription.objects.filter(sub_filter)

        status_counts = subs.values("status").annotate(total=Count("id")).order_by("status")
        kpi = {row["status"] or "unknown": row["total"] for row in status_counts}
        ctx["kpi"] = {
            "active": kpi.get("active", 0),
            "pending": kpi.get("pending", 0),
            "paused": kpi.get("paused", 0),
            "cancelled": kpi.get("cancelled", 0),
        }

        ctx["by_product"] = (
            subs.values("product__name").annotate(total=Count("id")).order_by("product__name")
        )
        ctx["by_season"] = (
            subs.values("season__name").annotate(total=Count("id")).order_by("season__name")
        )

        players_annotated = players.annotate(**_current_subqs())
        if season_id and season_id.isdigit():
            season_filtered_current = Subscription.objects.filter(
                player=OuterRef("pk"),
                status__in=["active", "pending"],
                season_id=int(season_id),
            ).order_by("-started_at")
            players_annotated = players.annotate(
                curr_status=Subquery(season_filtered_current.values("status")[:1]),
                curr_product=Subquery(season_filtered_current.values("product__name")[:1]),
                curr_season=Subquery(season_filtered_current.values("season__name")[:1]),
                curr_started=Subquery(season_filtered_current.values("started_at")[:1]),
                curr_id=Subquery(season_filtered_current.values("id")[:1]),
            )

        no_current = players_annotated.filter(
            Q(curr_status__isnull=True) | ~Q(curr_status__in=["active", "pending"])
        )
        ctx["no_current_count"] = no_current.count()
        ctx["no_current_players"] = no_current.order_by("last_name", "first_name")[:25]

        ctx["seasons"], ctx["products"] = _season_product_options(players)
        ctx["selected_season"] = int(season_id) if season_id and season_id.isdigit() else None
        ctx["selected_product"] = int(product_id) if product_id and product_id.isdigit() else None

        return ctx


class SubscriptionListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "members.view_staff_area"
    raise_exception = True
    template_name = "staff/memberships/list.html"
    paginate_by = 25
    context_object_name = "subscriptions"

    def get_queryset(self):
        players = _players_in_scope(self.request)

        qs = (
            Subscription.objects.select_related(
                "player", "player__player_type", "product", "season"
            )
            .filter(player__in=players)
            .order_by("-started_at", "-id")  # ← replace "-created_at" with "-id"
        )

        status = (self.request.GET.get("status") or "").strip().lower()
        if status in {"active", "pending", "paused", "cancelled"}:
            qs = qs.filter(status=status)

        season_id = self.request.GET.get("season")
        if season_id and season_id.isdigit():
            qs = qs.filter(season_id=int(season_id))

        product_id = self.request.GET.get("product")
        if product_id and product_id.isdigit():
            qs = qs.filter(product_id=int(product_id))

        team_id = self.request.GET.get("team")
        if team_id and team_id.isdigit():
            qs = qs.filter(player__team_memberships__team_id=int(team_id))

        player_type_id = self.request.GET.get("player_type")
        if player_type_id and player_type_id.isdigit():
            qs = qs.filter(player__player_type_id=int(player_type_id))

        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(player__first_name__icontains=q)
                | Q(player__last_name__icontains=q)
                | Q(product__name__icontains=q)
            ).distinct()

        return qs.distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["statuses"] = ["active", "pending", "paused", "cancelled"]
        ctx["seasons"], ctx["products"] = _season_product_options(_players_in_scope(self.request))
        ctx["teams"] = Team.objects.filter(active=True)
        ctx["player_types"] = PlayerType.objects.all()

        g = self.request.GET
        ctx["values"] = {
            "q": g.get("q", ""),
            "status": g.get("status", ""),
            "season": g.get("season", ""),
            "product": g.get("product", ""),
            "team": g.get("team", ""),
            "player_type": g.get("player_type", ""),
        }
        return ctx


# ──────────────────────────────────────────────────────────────────────────────
# Subscription status mutations
# ──────────────────────────────────────────────────────────────────────────────


@login_required
@permission_required("memberships.activate_subscription", raise_exception=True)
@require_POST
@transaction.atomic
def activate_subscription(request, subscription_id):
    sub = get_object_or_404(Subscription.objects.select_for_update(), id=subscription_id)

    if sub.status != "pending":
        messages.warning(request, "Only pending subscriptions can be activated.")
    else:
        _update_subscription_status(sub, "active", request.user)
        messages.success(request, f"Subscription #{sub.id} activated.")

    return redirect(request.META.get("HTTP_REFERER") or "staff:memberships_list")


@login_required
@permission_required("memberships.set_pending_subscription", raise_exception=True)
@require_POST
@transaction.atomic
def set_pending_subscription(request, subscription_id):
    sub = get_object_or_404(Subscription.objects.select_for_update(), id=subscription_id)

    if sub.status == "cancelled":
        messages.warning(request, "Cancelled subscriptions cannot be set back to pending.")
    else:
        _update_subscription_status(sub, "pending", request.user)
        messages.success(request, f"Subscription #{sub.id} set back to pending.")

    return redirect(request.META.get("HTTP_REFERER") or "staff:memberships_list")


@login_required
@permission_required("memberships.cancel_subscription", raise_exception=True)
@require_POST
@transaction.atomic
def cancel_subscription(request, subscription_id):
    sub = get_object_or_404(Subscription.objects.select_for_update(), id=subscription_id)

    if sub.status == "cancelled":
        messages.info(request, "Subscription already cancelled.")
    else:
        _update_subscription_status(sub, "cancelled", request.user)
        messages.success(request, f"Subscription #{sub.id} cancelled.")

    return redirect(request.META.get("HTTP_REFERER") or "staff:memberships_list")
