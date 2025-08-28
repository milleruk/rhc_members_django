from datetime import timedelta
from collections import OrderedDict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin, PermissionRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Count, OuterRef, Subquery, Prefetch
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.timezone import now
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, TemplateView
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from django.apps import apps


from .forms import DynamicAnswerForm, PlayerForm, TeamAssignmentForm
from .models import (
    DynamicQuestion,
    Player,
    PlayerAnswer,
    PlayerType,
    TeamMembership,
    PlayerAccessLog,
    
)
from memberships.models import Subscription


# ------------------------------------------------------
# Constants / mixins
# ------------------------------------------------------
ALLOWED_GROUPS = ["Full Access", "Committee", "Captain", "Coach", "Helper"]
COACH_GROUPS = ["Full Access", "Committee", "Coach"]


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
    """Show only the current user's players."""
    players = (
        request.user.players.select_related("player_type")
        .prefetch_related("team_memberships__team")
        .all()
    )
    return render(request, "members/dashboard.html", {"players": players})


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
    """
    Owner-gated dynamic Q&A form.
    Only the user who created the player can view/update their answers.
    """
    player = get_owned_player_or_404(request.user, public_id=public_id)

    if request.method == "POST":
        form = DynamicAnswerForm(request.POST, player=player)
        if form.is_valid():
            form.save()
            messages.success(request, "Details saved.")
            return redirect("dashboard")
    else:
        form = DynamicAnswerForm(player=player)

    questions = (
        DynamicQuestion.objects.filter(active=True, applies_to=player.player_type)
        .select_related("category")
        .order_by("category__display_order", "category__name", "display_order", "id")
    )

    # Build groups of BoundFields for the template
    grouped_fields = OrderedDict()
    for q in questions:
        cat_name = q.category.name if q.category else "General"
        grouped_fields.setdefault(cat_name, [])

        main_name = q.get_field_name()
        detail_name = q.get_detail_field_name()

        main_bf = form[main_name] if main_name in form.fields else None
        detail_bf = form[detail_name] if q.requires_detail_if_yes and detail_name in form.fields else None

        grouped_fields[cat_name].append({"main": main_bf, "detail": detail_bf})

    # NEW: use TeamMembership to fetch teams + positions
    memberships = (
        player.team_memberships
        .select_related("team")
        .prefetch_related("positions")
        .order_by("team__name")
    )

    return render(
        request,
        "members/answer_form.html",
        {
            "player": player,
            "form": form,
            "grouped_fields": grouped_fields,
            "team_memberships": memberships,  # <-- pass to template
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

class AdminPlayerListView(LoginRequiredMixin, PermissionRequiredMixin, InGroupsRequiredMixin, ListView):
    """
    Staff dashboard for browsing players.

    Access:
      - Requires `members.view_staff_area`.
      - If user has `members.view_all_players` -> sees all players.
      - Else -> only players on teams the user is associated with, determined by:
          1) Team.staff M2M (if present), OR
          2) Teams where the user has created memberships (TeamMembership.assigned_by = user).
    """
    model = Player
    template_name = "members/admin_player_list.html"
    context_object_name = "players"
    permission_required = "members.view_staff_area"
    raise_exception = True  # 403 instead of redirect

    # --- Helpers -------------------------------------------------------------

    def _base_qs(self):
        return (
            Player.objects
            .select_related("player_type", "created_by")
            .prefetch_related("team_memberships__team", "team_memberships__positions")
            .distinct()
        )

    def _get_user_team_ids(self, user):
        """Return IDs of teams this user can manage/see."""
        from .models import Team, TeamMembership
        team_ids = set()

        # 1) If Team has an M2M field 'staff' to User (future-proof)
        try:
            Team._meta.get_field("staff")
            team_ids.update(
                Team.objects.filter(staff=user).values_list("id", flat=True)
            )
        except Exception:
            pass

        # 2) Fallback: teams where this user assigned players
        team_ids.update(
            TeamMembership.objects.filter(assigned_by=user)
            .values_list("team_id", flat=True)
            .distinct()
        )

        return list(team_ids)

    def _restrict_to_user_teams(self, qs):
        user = self.request.user
        if user.has_perm("members.view_all_players"):
            return qs, None  # unrestricted
        team_ids = self._get_user_team_ids(user)
        if not team_ids:
            # No teams -> show nothing (but allow page load)
            return qs.none(), set()
        return qs.filter(team_memberships__team_id__in=team_ids).distinct(), set(team_ids)

    # --- Queryset ------------------------------------------------------------

    def get_queryset(self):
        qs = self._base_qs()

        # Enforce data-level permission first
        qs, allowed_team_ids = self._restrict_to_user_teams(qs)

        # Team filter (respect restriction)
        team_param = (self.request.GET.get("team") or "").strip()
        if team_param:
            if team_param == "none":
                # Only admins (view_all_players) may see unassigned
                if self.request.user.has_perm("members.view_all_players"):
                    qs = qs.filter(team_memberships__isnull=True)
                else:
                    qs = qs.none()
            else:
                try:
                    team_id = int(team_param)
                except ValueError:
                    team_id = None
                if team_id:
                    if (allowed_team_ids is None) or (team_id in allowed_team_ids):
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

        # Annotations for latest active/pending sub
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

        return qs

    # --- Context -------------------------------------------------------------

    def get_context_data(self, **kwargs):
        from .models import Team, PlayerType as PT, PlayerAccessLog
        ctx = super().get_context_data(**kwargs)
        players = ctx["players"]  # already restricted
        today = now().date()

        # Team dropdown: only teams the user can see (admins see all)
        if self.request.user.has_perm("members.view_all_players"):
            ctx["teams"] = Team.objects.filter(active=True)
        else:
            ctx["teams"] = Team.objects.filter(
                id__in=self._get_user_team_ids(self.request.user),
                active=True,
            )

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

        # Teams with players
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

        # Age distribution (expects a .age property)
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
                next_bd = dob.replace(year=today.year, day=1, month=3)  # 29 Feb → 1 Mar
            if next_bd < today:
                try:
                    next_bd = dob.replace(year=today.year + 1)
                except ValueError:
                    next_bd = dob.replace(year=today.year + 1, day=1, month=3)
            if 0 <= (next_bd - today).days <= 30:
                upcoming.append(p)
        ctx["upcoming_birthdays"] = upcoming

        return ctx


class AdminPlayerDetailView(LoginRequiredMixin, PermissionRequiredMixin, InGroupsRequiredMixin, DetailView):
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
        from .models import PlayerAnswer
        from .forms import TeamAssignmentForm

        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        player: Player = ctx["player"]

        # Answers visibility by group
        if user.is_superuser or user.groups.filter(name="Full Access").exists():
            answers = (
                PlayerAnswer.objects.filter(player=player)
                .select_related("question")
                .order_by("question__display_order", "question_id")
            )
        else:
            user_groups = DGroup.objects.filter(user=user)
            answers = (
                PlayerAnswer.objects.filter(
                    player=player, question__visible_to_groups__in=user_groups
                )
                .select_related("question")
                .distinct()
                .order_by("question__display_order", "question_id")
            )

        ctx["answers"] = answers
        ctx["memberships"] = player.team_memberships.select_related("team").all()
        ctx["team_form"] = TeamAssignmentForm(player=player)

        # Access logs (paginated)
        logs = player.access_logs.select_related("accessed_by").all()
        paginator = Paginator(logs, 10)
        ctx["log_page"] = paginator.get_page(self.request.GET.get("page"))

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
