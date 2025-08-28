from datetime import timedelta
from collections import OrderedDict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator
from django.db.models import Count, OuterRef, Subquery, Prefetch
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.timezone import now
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, TemplateView
from django.utils import timezone


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
class AdminPlayerListView(LoginRequiredMixin, InGroupsRequiredMixin, ListView):
    """
    Staff dashboard for browsing players.
    Group-gated; NOT owner-gated by design.
    """
    model = Player
    template_name = "members/admin_player_list.html"
    context_object_name = "players"
    raise_exception = True  # raise 403 instead of redirect when blocked

    def get_queryset(self):
        qs = (
            Player.objects
            .select_related("player_type", "created_by")
            .prefetch_related("team_memberships__team", "team_memberships__positions")
        )

        # Team filter, including "none" for unassigned
        team_param = self.request.GET.get("team")
        if team_param:
            if team_param == "none":
                qs = qs.filter(team_memberships__isnull=True)
            else:
                qs = qs.filter(team_memberships__team_id=team_param)

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

        # Annotations for the most recent active/pending sub
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

        return qs.distinct()

    def get_context_data(self, **kwargs):
        from .models import Team, PlayerType as PT

        ctx = super().get_context_data(**kwargs)
        players = self.get_queryset()
        today = now().date()

        # Filters
        ctx["teams"] = Team.objects.filter(active=True)
        ctx["player_types"] = PT.objects.all()

        # Time windows
        twelve_months_ago = now() - timedelta(days=365)

        # Top counters
        ctx["total_players"] = players.count()
        ctx["recent_updates"] = players.filter(updated_at__gte=twelve_months_ago).count()
        ctx["inactive_players"] = players.filter(updated_at__lt=twelve_months_ago).count()

        # Gender breakdown
        try:
            gender_map = dict(Player._meta.get_field("gender").flatchoices)
        except Exception:
            gender_map = {}

        raw_gender_counts = players.values("gender").annotate(total=Count("id")).order_by("gender")
        totals_by_gender = {}
        for row in raw_gender_counts:
            code = row["gender"]
            label = gender_map.get(code, code or "Unspecified")
            totals_by_gender[label] = row["total"]
        ctx["totals_by_gender"] = totals_by_gender

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

        # Age distribution (uses p.age property if present)
        age_ranges = {"U10": (0, 9), "U12": (10, 11), "U14": (12, 13), "U16": (14, 15), "Adults": (16, 200)}
        age_distribution = {}
        for label, (min_age, max_age) in age_ranges.items():
            count = sum(
                1
                for p in players
                if getattr(p, "age", None) is not None and min_age <= p.age <= max_age
            )
            age_distribution[label] = count
        ctx["age_distribution"] = age_distribution

        # Access logs today
        ctx["today_access_logs"] = PlayerAccessLog.objects.filter(accessed_at__date=today).count()

        # Questionnaire completion
        total_players = ctx["total_players"]
        answered_players = players.filter(answers__isnull=False).distinct().count()
        ctx["questionnaire_completion"] = round((answered_players / total_players) * 100, 1) if total_players else 0

        # Upcoming birthdays (next 30 days)
        upcoming_birthdays = []
        for p in players:
            dob = getattr(p, "date_of_birth", None)
            if not dob:
                continue
            try:
                next_bd = dob.replace(year=today.year)
            except ValueError:
                next_bd = dob.replace(year=today.year, day=1, month=3)  # handle Feb 29
            if next_bd < today:
                try:
                    next_bd = dob.replace(year=today.year + 1)
                except ValueError:
                    next_bd = dob.replace(year=today.year + 1, day=1, month=3)
            delta = (next_bd - today).days
            if 0 <= delta <= 30:
                upcoming_birthdays.append(p)
        ctx["upcoming_birthdays"] = upcoming_birthdays

        return ctx


class AdminPlayerDetailView(LoginRequiredMixin, InGroupsRequiredMixin, DetailView):
    """
    Staff view of a single player with answers + team memberships.
    """
    model = Player
    pk_url_kwarg = "player_id"
    template_name = "members/admin_player_detail.html"
    context_object_name = "player"
    raise_exception = True

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        PlayerAccessLog.objects.create(player=self.object, accessed_by=request.user)
        return response

    def get_context_data(self, **kwargs):
        from django.contrib.auth.models import Group as DGroup

        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        player: Player = ctx["player"]

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

        logs = player.access_logs.select_related("accessed_by").all()
        paginator = Paginator(logs, 10)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        ctx["log_page"] = page_obj

        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
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
