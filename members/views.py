from datetime import timedelta
from collections import OrderedDict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin, PermissionRequiredMixin
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Count, OuterRef, Subquery, Prefetch, Q, Exists
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.timezone import now
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, TemplateView
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from django.apps import apps
from django.db import transaction

from .forms import DynamicAnswerForm, PlayerForm, TeamAssignmentForm
from .models import (
    DynamicQuestion,
    Player,
    PlayerAnswer,
    PlayerType as PT,
    PlayerType,
    TeamMembership,
    PlayerAccessLog,
    Team,

)

from club.models import ClubNotice, QuickLink

from tasks.models import Task
from memberships.models import Subscription
from spond_integration.models import PlayerSpondLink
from tasks.events import emit



# ------------------------------------------------------
# Constants / mixins
# ------------------------------------------------------
ALLOWED_GROUPS = ["Full Access", "Committee", "Captain", "Coach", "Helper"]
COACH_GROUPS = ["Full Access", "Committee", "Coach"]


def _profile_is_complete(player) -> bool:
    req_q_ids = list(
        DynamicQuestion.objects.filter(
            active=True, required=True, applies_to=player.player_type
        ).values_list("id", flat=True)
    )
    if not req_q_ids:
        return True
    answered_ids = set(
        PlayerAnswer.objects.filter(
            player=player, question_id__in=req_q_ids
        ).values_list("question_id", flat=True)
    )
    return set(req_q_ids).issubset(answered_ids)

class InGroupsRequiredMixin(UserPassesTestMixin):
    """Require authenticated users to be in one of the allowed groups (or be superuser)."""

    allowed_groups = ALLOWED_GROUPS  # can be overridden per-view

    def test_func(self):
        u = self.request.user
        if not u.is_authenticated:
            return False
        if u.is_superuser:
            return True
        return u.groups.filter(name__in=self.allowed_groups).exists()


# ------------------------------------------------------
# Utilities (owner gating helpers)
# ------------------------------------------------------
def get_owned_player_or_404(user, **kwargs) -> Player:
    """
    Fetch a player owned by `user`, or 404.
    Centralises the ownership check to prevent accidental leaks.
    """
    return get_object_or_404(Player.objects.select_related("player_type"), created_by=user, **kwargs)


# ------------------------------------------------------
# Member-facing views (strictly owner-only)
# ------------------------------------------------------
@login_required
def dashboard(request):
    """Show current user's players + tasks panel."""
    players = (
        request.user.players
        .select_related("player_type")
        .prefetch_related("team_memberships__team")
        .all()
    )

    pending_tasks = []
    user = request.user

    # --- Try to load real tasks from your tasks app (robust to field names) ---
    try:
        from tasks.models import Task  # adjust if your app label differs

        # 1) detect assignee field
        assignee_field = None
        for candidate in ("assignee", "assigned_to", "user", "owner", "created_for"):
            if hasattr(Task, candidate):
                assignee_field = candidate
                break

        # 2) build base queryset for "my tasks"
        if assignee_field:
            base_q = Q(**{assignee_field: user})
        else:
            base_q = Q()  # fallback: no filter (uncommon)

        qs = Task.objects.all()

        # 3) open filter: status or done flags
        open_states = ["open", "todo", "pending", "in_progress", "new"]
        if hasattr(Task, "status"):
            qs = qs.filter(base_q, status__in=open_states)
        elif hasattr(Task, "is_done"):
            qs = qs.filter(base_q, is_done=False)
        elif hasattr(Task, "completed_at"):
            qs = qs.filter(base_q, completed_at__isnull=True)
        else:
            qs = qs.filter(base_q)  # last resort

        qs = qs.order_by("due_at", "-created_at")[:10]

        # 4) attach URLs if missing (adjust kinds to yours)
        player_pub_ids = {
            p.id: p.public_id for p in players
        }
        pending = []
        for t in qs:
            url = getattr(t, "url", None)
            kind = getattr(t, "kind", "")
            player_id = getattr(t, "player_id", None)

            if not url:
                if kind == "complete_answers" and player_id in player_pub_ids:
                    url = reverse("answer", args=[player_pub_ids[player_id]])
                elif kind == "choose_membership" and player_id:
                    url = reverse("memberships:choose", args=[player_id])
                elif hasattr(t, "get_absolute_url"):
                    try:
                        url = t.get_absolute_url()
                    except Exception:
                        pass
            # attach a transient .url attribute for the template
            setattr(t, "url", url)
            pending.append(t)

        pending_tasks = pending

    except Exception:
        # tasks app not available or schema unexpected
        pending_tasks = []

    # --- Optional: derive "virtual" tasks if none found (non-persistent) ---
    if not pending_tasks:
        # Example heuristics — tweak to your schema/methods
        for p in players:
            try:
                answers_complete = getattr(p, "answers_complete", None)
                if callable(answers_complete):
                    answers_complete = answers_complete()
            except Exception:
                answers_complete = None

            if answers_complete is False:
                pending_tasks.append(type("T", (), {
                    "title": f"Complete answers for {p.first_name} {p.last_name}",
                    "due_at": None,
                    "url": reverse("answer", args=[p.public_id]),
                })())

            # Example: no active membership => prompt
            try:
                has_active_membership = getattr(p, "has_active_membership", None)
                if callable(has_active_membership):
                    has_active_membership = has_active_membership()
            except Exception:
                has_active_membership = None

            if has_active_membership is False:
                pending_tasks.append(type("T", (), {
                    "title": f"Choose membership for {p.first_name} {p.last_name}",
                    "due_at": None,
                    "url": reverse("memberships:choose", args=[p.id]),
                })())

        # limit to 10 visual items
        pending_tasks = pending_tasks[:10]

    # ✅ Always define notices and quick_links
    notices = ClubNotice.objects.filter(active=True)
    quick_links = QuickLink.objects.filter(active=True)

    return render(
        request,
        "members/dashboard.html",
        {
            "players": players,
            "pending_tasks": pending_tasks,
            "notices": notices,
            "quick_links": quick_links,
        },
    )

class PlayerCreateView(LoginRequiredMixin, CreateView):
    """Create a player profile that is automatically owned by the creator."""
    model = Player
    form_class = PlayerForm
    template_name = "members/player_form.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        if form.cleaned_data.get("relation") == "child":
            junior = PlayerType.objects.get(name__iexact="junior")
            form.instance.player_type = junior
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("answer", kwargs={"public_id": self.object.public_id})


@login_required
def answer_view(request, public_id):
    player = get_owned_player_or_404(request.user, public_id=public_id)

    if request.method == "POST":
        form = DynamicAnswerForm(request.POST, player=player)
        if form.is_valid():
            form.save()

            # ✅ If the profile is now complete, mark the task done via generic event
            if _profile_is_complete(player):
                transaction.on_commit(
                    lambda: emit("profile.completed", subject=player, actor=request.user)
                )

            messages.success(request, "Details saved.")
            return redirect("dashboard")
    else:
        form = DynamicAnswerForm(player=player)

    questions = (
        DynamicQuestion.objects.filter(active=True, applies_to=player.player_type)
        .select_related("category")
        .order_by("category__display_order", "category__name", "display_order", "id")
    )

    grouped_fields = OrderedDict()
    for q in questions:
        cat = q.category
        cat_key = cat.id if cat else "general"

        if cat_key not in grouped_fields:
            grouped_fields[cat_key] = {
                "name": cat.name if cat else "General",
                # handle both 'description' and the earlier 'discription' field name
                "description": (getattr(cat, "description", None) 
                                or getattr(cat, "discription", "") 
                                if cat else ""),
                "items": [],
            }

        main_name = q.get_field_name()
        detail_name = q.get_detail_field_name()
        main_bf = form[main_name] if main_name in form.fields else None
        detail_bf = form[detail_name] if q.requires_detail_if_yes and detail_name in form.fields else None

        grouped_fields[cat_key]["items"].append({"main": main_bf, "detail": detail_bf})

    memberships = (
        player.team_memberships.select_related("team").prefetch_related("positions").order_by("team__name")
    )

    return render(
        request,
        "members/answer_form.html",
        {
            "player": player,
            "form": form,
            "grouped_fields": grouped_fields,
            "team_memberships": memberships,
        },
    )

@login_required
def player_delete(request, public_id):
    """
    Owner-gated delete. Only the creator may delete their player.
    """
    player = get_owned_player_or_404(request.user, public_id=public_id) 

    if request.method == "POST":
        name = getattr(player, "full_name", str(player))
        player.delete()
        messages.success(request, f"Deleted player: {name}")
        return redirect("dashboard")

    return render(request, "members/player_confirm_delete.html", {"player": player})


# ------------------------------------------------------
# Staff (admin) views — group-gated using InGroupsRequiredMixin
# ------------------------------------------------------

class AdminPlayerListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """
    Staff dashboard for browsing players.

    Access:
      - Requires `members.view_staff_area`.
      - If user has `members.view_all_players` -> sees ALL players.
      - Else -> only players on teams where the user is in Team.staff (M2M).
    """
    model = Player
    template_name = "members/admin_player_list.html"
    context_object_name = "players"
    permission_required = "members.view_staff_area"
    raise_exception = True  # 403 instead of redirect

    # ---------- Helpers ----------

    def _base_qs(self):
        return (
            Player.objects
            .select_related("player_type", "created_by")
            .prefetch_related("team_memberships__team", "team_memberships__positions")
            .distinct()
        )

    def _get_user_team_ids(self, user):
        """Teams this user can manage/see via Team.staff M2M only."""
        from .models import Team
        return list(
            Team.objects.filter(staff=user).values_list("id", flat=True)
        )

    # ---------- Queryset ----------

    def get_queryset(self):
        qs = self._base_qs()

        user = self.request.user
        is_admin_all = user.has_perm("members.view_all_players")

        # Restrict by Team.staff for non-admins
        allowed_team_ids = None
        if not is_admin_all:
            allowed_team_ids = set(self._get_user_team_ids(user))
            if not allowed_team_ids:
                return qs.none()
            qs = qs.filter(team_memberships__team_id__in=allowed_team_ids)

        # Team filter (UI dropdown)
        team_param = (self.request.GET.get("team") or "").strip()
        if team_param:
            if team_param == "none":
                # Only admins can see unassigned
                if is_admin_all:
                    qs = qs.filter(team_memberships__isnull=True)
                else:
                    qs = qs.none()
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

        # Player type filter
        player_type_id = self.request.GET.get("player_type")
        if player_type_id:
            qs = qs.filter(player_type_id=player_type_id)

        # Membership subscription status filter
        sub_status = (self.request.GET.get("subscription_status") or "").strip().lower()
        if sub_status in {"active", "pending", "paused", "cancelled"}:
            qs = qs.filter(subscriptions__status=sub_status)
        elif sub_status == "none":
            qs = qs.exclude(subscriptions__status__in=["active", "pending"])

        # Latest active/pending subscription annotations
        active_sub_qs = (
            Subscription.objects
            .filter(player=OuterRef("pk"), status__in=["active", "pending"])
            .order_by("-started_at")
        )
        qs = qs.annotate(
            active_sub_product=Subquery(active_sub_qs.values("product__name")[:1]),
            active_sub_status=Subquery(active_sub_qs.values("status")[:1]),
            active_sub_season=Subquery(active_sub_qs.values("season__name")[:1]),
        )

        # Count of active Spond links
        qs = qs.annotate(
            active_spond_count=Count(
                "spond_links",
                filter=Q(spond_links__active=True),
                distinct=True,
            )
        )

        return qs.distinct()

    # ---------- Context ----------

    def get_context_data(self, **kwargs):
        from .models import Team, PlayerType as PT, PlayerAccessLog
        ctx = super().get_context_data(**kwargs)
        players = ctx["players"]
        user = self.request.user
        is_admin_all = user.has_perm("members.view_all_players")
        today = now().date()

        # Teams dropdown: admins see all; staff see only their teams
        if is_admin_all:
            ctx["teams"] = Team.objects.filter(active=True)
        else:
            team_ids = self._get_user_team_ids(user)
            ctx["teams"] = Team.objects.filter(id__in=team_ids, active=True)

        # Optional debug (add ?debug=1)
        debug_mode = (self.request.GET.get("debug") == "1")
        ctx["debug_mode"] = debug_mode
        if debug_mode:
            ctx["debug_global"] = {
                "is_admin_all": is_admin_all,
                "allowed_team_ids": "ALL" if is_admin_all else list(self._get_user_team_ids(user)),
                "visible_players_count": players.count(),
            }
            # Per-player quick view
            for p in players:
                tm_summary = []
                ids = set()
                for tm in p.team_memberships.all():
                    ids.add(tm.team_id)
                    tm_summary.append({
                        "team_id": tm.team_id,
                        "team_name": getattr(tm.team, "name", None),
                        "positions": [pos.name for pos in tm.positions.all()],
                    })
                setattr(p, "debug_teams", sorted(ids))
                setattr(p, "debug_memberships", tm_summary)

        # Player types
        ctx["player_types"] = PT.objects.all()

        # Top counters
        twelve_months_ago = now() - timedelta(days=365)
        ctx["total_players"] = players.count()
        ctx["recent_updates"] = players.filter(updated_at__gte=twelve_months_ago).count()
        ctx["inactive_players"] = players.filter(updated_at__lt=twelve_months_ago).count()

        # Gender breakdown
        try:
            gender_map = dict(Player._meta.get_field("gender").flatchoices)
        except Exception:
            gender_map = {}
        raw_gender_counts = players.values("gender").annotate(total=Count("id")).order_by("gender")
        ctx["totals_by_gender"] = {
            (gender_map.get(row["gender"], row["gender"] or "Unspecified")): row["total"]
            for row in raw_gender_counts
        }

        # Teams with players (within visibility)
        ctx["totals_per_team"] = (
            players.filter(team_memberships__isnull=False)
            .values("team_memberships__team__name")
            .annotate(total=Count("id", distinct=True))
            .order_by("team_memberships__team__name")
        )

        # Membership types breakdown
        membership_qs = (
            players.values("player_type__name")
            .annotate(total=Count("id"))
            .order_by("player_type__name")
        )
        ctx["membership_breakdown"] = {
            row["player_type__name"] or "Unspecified": row["total"] for row in membership_qs
        }
        ctx["membership_types"] = membership_qs

        # Age distribution (expects .age property)
        age_ranges = {"U10": (0, 9), "U12": (10, 11), "U14": (12, 13), "U16": (14, 15), "Adults": (16, 200)}
        ctx["age_distribution"] = {
            label: sum(1 for p in players if getattr(p, "age", None) is not None and lo <= p.age <= hi)
            for label, (lo, hi) in age_ranges.items()
        }

        # Access logs today
        ctx["today_access_logs"] = PlayerAccessLog.objects.filter(accessed_at__date=today).count()

        # Questionnaire completion
        total_players = ctx["total_players"]
        answered_players = players.filter(answers__isnull=False).distinct().count()
        ctx["questionnaire_completion"] = round((answered_players / total_players) * 100, 1) if total_players else 0

        # Upcoming birthdays (next 30 days)
        upcoming = []
        for p in players:
            dob = getattr(p, "date_of_birth", None)
            if not dob:
                continue
            try:
                next_bd = dob.replace(year=today.year)
            except ValueError:
                next_bd = dob.replace(year=today.year, day=1, month=3)
            if next_bd < today:
                try:
                    next_bd = dob.replace(year=today.year + 1)
                except ValueError:
                    next_bd = dob.replace(year=today.year + 1, day=1, month=3)
            if 0 <= (next_bd - today).days <= 30:
                upcoming.append(p)
        ctx["upcoming_birthdays"] = upcoming

        return ctx

class AdminPlayerDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    """
    Staff view of a single player with answers + team memberships.

    Access:
      - Requires `members.view_staff_area`.
      - If user has `members.view_all_players` -> can view any player.
      - Else -> only players on teams the user is associated with:
          * Team.staff M2M (if present), OR
          * Teams where the user assigned memberships (TeamMembership.assigned_by=user).
    """
    model = Player
    pk_url_kwarg = "player_id"
    template_name = "members/admin_player_detail.html"
    context_object_name = "player"
    permission_required = "members.view_staff_area"
    raise_exception = True  # 403 on missing global permission

    # ---- helpers ------------------------------------------------------------

    def _get_user_team_ids(self, user):
        """Return IDs of teams this user can manage/see."""
        from .models import Team, TeamMembership
        team_ids = set()

        # Optional future-proof: Team.staff (M2M to User)
        try:
            Team._meta.get_field("staff")
            team_ids.update(Team.objects.filter(staff=user).values_list("id", flat=True))
        except Exception:
            pass

        # Fallback: teams where this user assigned players
        team_ids.update(
            TeamMembership.objects.filter(assigned_by=user)
            .values_list("team_id", flat=True)
            .distinct()
        )
        return list(team_ids)

    @staticmethod
    def _parse_choices(choices_text: str):
        """Return {value: label} from 'value|Label' OR 'Label' lines."""
        mapping = {}
        text = choices_text or ""
        for line in [ln.strip() for ln in text.splitlines() if ln.strip()]:
            if "|" in line:
                val, lab = [p.strip() for p in line.split("|", 1)]
            else:
                val, lab = line, line
            mapping[val] = lab
        return mapping

    # ---- object-level permission -> 403 on fail -----------------------------

    def get_queryset(self):
        # Unrestricted base queryset; object-level check happens in get_object()
        return (
            Player.objects
            .select_related("player_type", "created_by")
            .prefetch_related("team_memberships__team", "team_memberships__positions")
        )

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        user = self.request.user

        # Full access -> allowed
        if user.has_perm("members.view_all_players"):
            return obj

        # Team-restricted access
        allowed_team_ids = self._get_user_team_ids(user)
        if allowed_team_ids and obj.team_memberships.filter(team_id__in=allowed_team_ids).exists():
            return obj

        # Not allowed -> 403 (shows your 403 denied page)
        raise PermissionDenied("You do not have access to this player.")

    # ---- GET with access logging -------------------------------------------

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)  # will raise PermissionDenied if blocked
        from .models import PlayerAccessLog
        PlayerAccessLog.objects.create(player=self.object, accessed_by=request.user)
        return response

    # ---- context ------------------------------------------------------------

    def get_context_data(self, **kwargs):
        from django.contrib.auth.models import Group as DGroup
        from .models import PlayerAnswer, DynamicQuestion
        from .forms import TeamAssignmentForm

        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        player: Player = ctx["player"]

        # --- Build READ-ONLY answers using the same question list the player gets ---
        questions = (
            DynamicQuestion.objects.filter(active=True, applies_to=player.player_type)
            .select_related("category")
            .order_by("category__display_order", "category__name", "display_order", "id")
        )
        existing = {
            a.question_id: a
            for a in PlayerAnswer.objects.filter(player=player)
            .select_related("question", "question__category")
        }

        grouped = OrderedDict()
        for q in questions:
            ans = existing.get(q.id)
            qtype = getattr(q, "question_type", "text")

            # --- compute display per type ---
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
                for name in ("number_answer", "numeric_answer", "int_answer", "float_answer", "text_answer"):
                    if ans is not None and hasattr(ans, name):
                        val = getattr(ans, name)
                        if val not in (None, ""):
                            break
                if val in (None, ""):
                    display = "—"
                else:
                    # ✅ preserve as string so leading zeros remain
                    display = str(val)

            elif qtype == "choice":
                mapping = self._parse_choices(getattr(q, "choices_text", "") or "")
                # prefer explicit choice value fields; fall back to text
                raw = None
                for name in ("choice_answer", "choice_value", "selected_value", "text_answer"):
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
                    "description": (getattr(cat, "description", None) or getattr(cat, "discription", "")) if cat else "",
                    "items": [],
                }

            grouped[key]["items"].append({
                "label": q.label,
                "description": getattr(q, "description", ""),
                "type": qtype,
                "display": display,
                "detail": detail,
            })

        # Expose read-only structure (use this in the template)
        ctx["readonly_answers"] = grouped

        # --- Team memberships + form ---
        ctx["memberships"] = player.team_memberships.select_related("team").all()
        ctx["team_form"] = TeamAssignmentForm(player=player)

        # --- Access logs (paginated) ---
        logs = player.access_logs.select_related("accessed_by").all()
        paginator = Paginator(logs, 10)
        ctx["log_page"] = paginator.get_page(self.request.GET.get("page"))

        # --- Spond: all attendances for the active link, newest first, paginated ---
        link = (
            player.spond_links.filter(active=True)
            .select_related("spond_member")
            .first()
        )
        ctx["spond_member"] = getattr(link, "spond_member", None)

        attendances_qs = None
        if ctx["spond_member"]:
            attendances_qs = (
                ctx["spond_member"]
                .attendances.select_related("event")
                .order_by("-event__start_at")
            )

        page_number = self.request.GET.get("spond_page", 1)
        if attendances_qs is not None:
            sp_paginator = Paginator(attendances_qs, 25)  # show 25 per page
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

    # ---- POST (assign team) -------------------------------------------------

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()  # respects object-level permissions
        from .forms import TeamAssignmentForm
        form = TeamAssignmentForm(request.POST, player=self.object)
        if form.is_valid():
            form.save(user=request.user)
            return redirect("admin_player_detail", player_id=self.object.id)
        ctx = self.get_context_data()
        ctx["team_form"] = form
        return self.render_to_response(ctx)

@login_required
@require_POST
def remove_membership(request, membership_id):
    membership = get_object_or_404(TeamMembership, id=membership_id)
    if not (
        request.user.is_superuser
        or request.user.groups.filter(name__in=COACH_GROUPS).exists()
    ):
        return HttpResponseForbidden("Not allowed")
    player_id = membership.player_id
    membership.delete()
    return redirect("admin_player_detail", player_id=player_id)


# ------------------------------------------------------
# Legal pages
# ------------------------------------------------------
class TermsView(TemplateView):
    template_name = "legal/terms.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["last_updated"] = timezone.now().date()
        return ctx


class PrivacyView(TemplateView):
    template_name = "legal/privacy.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["last_updated"] = timezone.now().date()
        return ctx
