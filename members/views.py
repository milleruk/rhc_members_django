# members/views.py

# ──────────────────────────────────────────────────────────────────────────────
# Standard library
# ──────────────────────────────────────────────────────────────────────────────
from datetime import timedelta
from collections import OrderedDict

# ──────────────────────────────────────────────────────────────────────────────
# Django
# ──────────────────────────────────────────────────────────────────────────────
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import (
    LoginRequiredMixin,
    UserPassesTestMixin,
    PermissionRequiredMixin,
)
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import transaction
from django.db.models import Count, OuterRef, Subquery, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.timezone import now
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

# ──────────────────────────────────────────────────────────────────────────────
# Local apps
# ──────────────────────────────────────────────────────────────────────────────
from .forms import DynamicAnswerForm, PlayerForm, TeamAssignmentForm, PlayerEditForm
from .models import (
    DynamicQuestion,
    Player,
    PlayerAnswer,
    PlayerType,
    TeamMembership,
    PlayerAccessLog,
)

from club.models import ClubNotice, QuickLink
from memberships.models import Subscription
from tasks.events import emit

# If you reference these elsewhere (kept for clarity)
from .models import Team  # used in admin list view helpers


# =============================================================================
# Constants / Group access
# =============================================================================

ALLOWED_GROUPS = ["Full Access", "Committee", "Captain", "Coach", "Helper"]
COACH_GROUPS = ["Full Access", "Committee", "Coach"]


class InGroupsRequiredMixin(UserPassesTestMixin):
    """
    Require authenticated users to be in one of the allowed groups (or be superuser).
    Override `allowed_groups` per-view where needed.
    """
    allowed_groups = ALLOWED_GROUPS

    def test_func(self):
        u = self.request.user
        if not u.is_authenticated:
            return False
        if u.is_superuser:
            return True
        return u.groups.filter(name__in=self.allowed_groups).exists()


# =============================================================================
# Utilities / helpers
# =============================================================================

def _profile_is_complete(player) -> bool:
    """Return True if all required active questions (for the player's type) are answered."""
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


def get_owned_player_or_404(user, **kwargs) -> Player:
    """
    Fetch a player owned by `user` (created_by=user), or 404.
    Centralizes the ownership check to prevent accidental leaks.
    """
    return get_object_or_404(
        Player.objects.select_related("player_type"),
        created_by=user,
        **kwargs,
    )


# =============================================================================
# Member-facing views (owner-only)
# =============================================================================

@login_required
def dashboard(request):
    """Show current user's players + tasks panel."""
    players = (
        request.user.players
        .select_related("player_type")
        .prefetch_related("team_memberships__team")
        .all()
    )

    # Try to pull "open" tasks for this user (best-effort across varying schemas)
    pending_tasks = []
    user = request.user
    try:
        from tasks.models import Task  # import here to avoid hard dependency at import time

        # detect assignee field
        assignee_field = None
        for candidate in ("assignee", "assigned_to", "user", "owner", "created_for"):
            if hasattr(Task, candidate):
                assignee_field = candidate
                break

        qs = Task.objects.all()
        base_q = Q(**{assignee_field: user}) if assignee_field else Q()

        # open / pending
        open_states = ["open", "todo", "pending", "in_progress", "new"]
        if hasattr(Task, "status"):
            qs = qs.filter(base_q, status__in=open_states)
        elif hasattr(Task, "is_done"):
            qs = qs.filter(base_q, is_done=False)
        elif hasattr(Task, "completed_at"):
            qs = qs.filter(base_q, completed_at__isnull=True)
        else:
            qs = qs.filter(base_q)

        qs = qs.order_by("due_at", "-created_at")[:10]

        # attach URLs if missing (derive from known patterns)
        player_pub_ids = {p.id: p.public_id for p in players}
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

            setattr(t, "url", url)  # transient attribute for templates
            pending.append(t)

        pending_tasks = pending

    except Exception:
        pending_tasks = []

    # Fallback "virtual" tasks if none present
    if not pending_tasks:
        for p in players:
            answers_complete = None
            try:
                answers_complete = p.answers_complete() if callable(getattr(p, "answers_complete", None)) else getattr(p, "answers_complete", None)
            except Exception:
                pass

            if answers_complete is False:
                pending_tasks.append(type("T", (), {
                    "title": f"Complete answers for {p.first_name} {p.last_name}",
                    "due_at": None,
                    "url": reverse("answer", args=[p.public_id]),
                })())

            has_active_membership = None
            try:
                ham = getattr(p, "has_active_membership", None)
                has_active_membership = ham() if callable(ham) else ham
            except Exception:
                pass

            if has_active_membership is False:
                pending_tasks.append(type("T", (), {
                    "title": f"Choose membership for {p.first_name} {p.last_name}",
                    "due_at": None,
                    "url": reverse("memberships:choose", args=[p.id]),
                })())

        pending_tasks = pending_tasks[:10]

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


# =============================================================================
# Create / Update / Delete (member-facing)
# =============================================================================

class PlayerCreateView(LoginRequiredMixin, CreateView):
    """Create a player profile that is automatically owned by the creator."""
    model = Player
    form_class = PlayerForm
    template_name = "members/player_form.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        # Optional: auto-assign Junior when relation is child
        try:
            if form.cleaned_data.get("relation") == "child":
                junior = PlayerType.objects.get(name__iexact="junior")
                form.instance.player_type = junior
        except PlayerType.DoesNotExist:
            pass
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("answer", kwargs={"public_id": self.object.public_id})


class PlayerUpdateView(LoginRequiredMixin, UpdateView):
    """Edit an existing player (owner/guardian/staff or superuser)."""
    model = Player
    form_class = PlayerEditForm
    template_name = "members/player_edit.html"
    context_object_name = "player"
    slug_field = "public_id"
    slug_url_kwarg = "public_id"

    def get_queryset(self):
        """
        Limit to players the user is allowed to edit:
          - staff/superuser/perms -> all
          - else: created_by=user OR guardians contains user (if field exists)
        """
        qs = super().get_queryset()
        u = self.request.user
        if u.is_superuser or u.is_staff or u.has_perm("members.change_player"):
            return qs

        f = Q()
        # created_by
        if any(fld.name == "created_by" for fld in qs.model._meta.get_fields()):
            f |= Q(created_by=u)
        # guardians (if present)
        if hasattr(qs.model, "guardians"):
            f |= Q(guardians=u)

        return qs.filter(f) if f else qs.none()

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        obj = getattr(self, "object", None)
        if obj is not None:
            allowed = obj.can_edit(request.user) if hasattr(obj, "can_edit") else (
                request.user.is_staff or request.user.has_perm("members.change_player")
            )
            if not allowed:
                messages.error(request, "You don’t have permission to edit this player.")
                return redirect("dashboard")
        return response

    def form_valid(self, form):
        if hasattr(form.instance, "updated_by_id"):
            form.instance.updated_by = self.request.user
        messages.success(self.request, "Player details updated.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("answer", kwargs={"public_id": self.object.public_id})


@login_required
def answer_view(request, public_id):
    """Owner flow for answering dynamic questions for a player."""
    player = get_owned_player_or_404(request.user, public_id=public_id)

    if request.method == "POST":
        form = DynamicAnswerForm(request.POST, player=player)
        if form.is_valid():
            form.save()

            # Mark profile complete → emit event
            if _profile_is_complete(player):
                transaction.on_commit(lambda: emit("profile.completed", subject=player, actor=request.user))

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
                # support both 'description' and legacy 'discription'
                "description": (getattr(cat, "description", None) or getattr(cat, "discription", "")) if cat else "",
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
    """Owner-gated delete. Only the creator may delete their player."""
    player = get_owned_player_or_404(request.user, public_id=public_id)

    if request.method == "POST":
        name = getattr(player, "full_name", str(player))
        player.delete()
        messages.success(request, f"Deleted player: {name}")
        return redirect("dashboard")

    return render(request, "members/player_confirm_delete.html", {"player": player})

# =============================================================================
# Legal pages
# =============================================================================

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
