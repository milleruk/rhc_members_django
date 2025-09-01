# tasks/views.py
from __future__ import annotations

from datetime import timedelta
from typing import Iterable, Set

from django.apps import apps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db import transaction
from django.db.models import Q, QuerySet
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, FormView, ListView

from .forms import TaskBulkGenerateForm, TaskCreateForm
from .models import Task, TaskStatus


# ---------------------------
# Shared filtering for lists
# ---------------------------

class TaskListFilterMixin:
    """
    Mixin that applies common filtering/sorting for Task list views.

    Supports GET params:
      - q: search in title/description
      - status: one of TaskStatus choices
      - due: overdue | week | future | none
      - assignee: user id (All view only typically)
    """

    def _valid_statuses(self) -> Set[str]:
        return {choice[0] for choice in Task._meta.get_field("status").choices}

    def _apply_common_filters(self, qs: QuerySet[Task]) -> QuerySet[Task]:
        request = self.request
        now = timezone.now()

        # Text search
        q = (request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))

        # Status
        status = request.GET.get("status")
        if status in self._valid_statuses():
            qs = qs.filter(status=status)

        # Due window
        due = request.GET.get("due")
        if due == "overdue":
            qs = qs.filter(status=TaskStatus.OPEN, due_at__lt=now)
        elif due == "week":
            qs = qs.filter(due_at__gte=now, due_at__lte=now + timedelta(days=7))
        elif due == "future":
            qs = qs.filter(due_at__gt=now + timedelta(days=7))
        elif due == "none":
            qs = qs.filter(due_at__isnull=True)

        # Optional assignee (for admin list pages)
        assignee_id = request.GET.get("assignee")
        if assignee_id:
            try:
                qs = qs.filter(assigned_to_id=int(assignee_id))
            except (TypeError, ValueError):
                # ignore bad input rather than 500
                pass

        # Consistent ordering: status, due soonest, newest created last
        return qs.order_by("status", "due_at", "-created_at")


# ---------------------------
# My tasks
# ---------------------------

class MyTaskListView(LoginRequiredMixin, TaskListFilterMixin, ListView):
    model = Task
    template_name = "tasks/my_list.html"
    context_object_name = "tasks"
    paginate_by = 18

    def get_queryset(self) -> QuerySet[Task]:
        qs = (
            Task.objects.filter(assigned_to=self.request.user)
            .select_related("assigned_to", "created_by")
        )
        return self._apply_common_filters(qs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        items: Iterable[Task] = list(ctx["tasks"])
        for t in items:
            t.can_complete = t.can_manual_complete(self.request.user)
        ctx["tasks"] = items
        ctx["status_choices"] = Task._meta.get_field("status").choices
        return ctx


# ---------------------------
# All tasks (admin/staff)
# ---------------------------

class AllTaskListView(LoginRequiredMixin, PermissionRequiredMixin, TaskListFilterMixin, ListView):
    permission_required = "tasks.view_all_tasks"
    model = Task
    template_name = "tasks/all_list.html"
    context_object_name = "tasks"
    paginate_by = 24

    def get_queryset(self) -> QuerySet[Task]:
        qs = Task.objects.all().select_related("assigned_to", "created_by")
        return self._apply_common_filters(qs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        items: Iterable[Task] = list(ctx["tasks"])
        for t in items:
            t.can_complete = t.can_manual_complete(self.request.user)
        ctx["tasks"] = items
        ctx["status_choices"] = Task._meta.get_field("status").choices
        return ctx


# ---------------------------
# State changes
# ---------------------------

@login_required
@require_POST
def complete_task(request, pk):
    """
    Mark a task as DONE. POST only to avoid accidental state changes via GET.
    """
    task = get_object_or_404(Task, pk=pk)

    # Respect allow_manual_complete unless privileged
    if not task.allow_manual_complete and not (
        request.user.is_superuser or request.user.has_perm("tasks.view_all_tasks")
    ):
        messages.error(request, "This task auto-completes and can’t be manually completed.")
        return redirect(request.POST.get("next") or "tasks:my_list")

    if not task.can_manual_complete(request.user):
        messages.error(request, "You can’t manually complete this task.")
        return redirect(request.POST.get("next") or "tasks:my_list")

    task.status = TaskStatus.DONE
    task.save(update_fields=["status", "updated_at"])
    messages.success(request, "Task marked as done.")
    return redirect(request.POST.get("next") or "tasks:my_list")


@login_required
@require_POST
def dismiss_task(request, pk):
    """
    Dismiss a task (e.g., not applicable). POST only.
    """
    task = get_object_or_404(Task, pk=pk)
    task.status = TaskStatus.DISMISSED
    task.save(update_fields=["status", "updated_at"])
    messages.success(request, "Task dismissed.")
    return redirect(request.POST.get("next") or "tasks:my_list")


# ---------------------------
# Create / Bulk-generate
# ---------------------------

class TaskCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = "tasks.add_task"
    model = Task
    form_class = TaskCreateForm
    template_name = "tasks/create.html"
    success_url = reverse_lazy("tasks:my_list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class TaskBulkGenerateView(LoginRequiredMixin, PermissionRequiredMixin, FormView):
    """
    Bulk-create tasks targeting players by Player Types / Teams / Products (season),
    and auto-assign each task to the player's creator (with optional fallback).
    """
    permission_required = "tasks.add_task"
    template_name = "tasks/bulk_generate.html"
    form_class = TaskBulkGenerateForm
    success_url = reverse_lazy("tasks:my_list")

    def form_valid(self, form):
        data = form.cleaned_data
        title: str = data["title"]
        description: str = data.get("description", "")
        due_at = data.get("due_at")
        complete_on = data.get("complete_on", "")
        allow_manual_complete: bool = data.get("allow_manual_complete", True)

        assign_to_creator: bool = data.get("assign_to_creator", True)
        fallback_assignee = data.get("fallback_assignee")

        player_types = data.get("player_types")
        teams = data.get("teams")
        products = data.get("products")  # used as a selector sentinel below
        season = data.get("season")
        only_without_subscription: bool = data.get("only_without_subscription")

        Player = apps.get_model("members", "Player")
        TeamMembership = apps.get_model("members", "TeamMembership")
        Subscription = apps.get_model("memberships", "Subscription")

        # Build union of players matching selectors
        player_ids: Set[int] = set()

        if player_types and player_types.exists():
            ids = Player.objects.filter(player_type__in=player_types).values_list("id", flat=True)
            player_ids.update(ids)

        if teams and teams.exists():
            tm_qs = TeamMembership.objects.filter(team__in=teams).values_list("player_id", flat=True)
            player_ids.update(tm_qs)

        # Products alone do not resolve players *unless* used with "season + only_without_subscription"
        if products and products.exists():
            if season and only_without_subscription and Subscription is not None:
                subscribed_ids = set(
                    Subscription.objects.filter(
                        season=season, status__in=["pending", "active"]
                    ).values_list("player_id", flat=True)
                )
                if not player_ids:
                    all_ids = set(Player.objects.values_list("id", flat=True))
                    player_ids.update(all_ids)
                player_ids.difference_update(subscribed_ids)
            else:
                if not player_ids:
                    messages.warning(
                        self.request,
                        "No player types/teams selected; products alone do not select players."
                    )
                    return super().form_invalid(form)

        if not player_ids:
            messages.error(self.request, "No players matched your selection.")
            return super().form_invalid(form)

        players = list(
            Player.objects.filter(id__in=player_ids)
            .select_related("created_by")
            .order_by("last_name", "first_name")
        )

        to_create = []
        missing_creator_count = 0

        for p in players:
            # Determine assignee
            assignee = None
            if assign_to_creator:
                assignee = getattr(p, "created_by", None) or fallback_assignee
                if assignee is None:
                    missing_creator_count += 1
            else:
                assignee = fallback_assignee  # may still be None

            to_create.append(Task(
                title=title,
                description=description,
                created_by=self.request.user,
                assigned_to=assignee,
                status=TaskStatus.OPEN,
                due_at=due_at,
                subject=p,                      # GenericForeignKey: attach to Player
                complete_on=complete_on,
                allow_manual_complete=allow_manual_complete,
            ))

        with transaction.atomic():
            Task.objects.bulk_create(to_create, batch_size=500)

        note = f"Created {len(to_create)} task(s)."
        if assign_to_creator and missing_creator_count:
            if fallback_assignee:
                note += f" {missing_creator_count} player(s) had no creator; assigned to fallback."
            else:
                note += f" {missing_creator_count} player(s) had no creator; tasks left unassigned."
        messages.success(self.request, note)
        return super().form_valid(form)
