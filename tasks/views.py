# tasks/views.py
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import ListView, CreateView, FormView
from django.urls import reverse_lazy
from django.db import transaction
from django.apps import apps

from .models import Task, TaskStatus
from .forms import TaskCreateForm, TaskBulkGenerateForm


class MyTaskListView(LoginRequiredMixin, ListView):
    model = Task
    template_name = "tasks/my_list.html"
    context_object_name = "tasks"
    paginate_by = 18

    def get_queryset(self):
        qs = Task.objects.filter(assigned_to=self.request.user)

        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))

        status = self.request.GET.get("status")
        valid_statuses = {choice[0] for choice in Task._meta.get_field("status").choices}
        if status in valid_statuses:
            qs = qs.filter(status=status)

        due = self.request.GET.get("due")
        now = timezone.now()
        if due == "overdue":
            qs = qs.filter(status=TaskStatus.OPEN, due_at__lt=now)
        elif due == "week":
            qs = qs.filter(due_at__gte=now, due_at__lte=now + timedelta(days=7))
        elif due == "future":
            qs = qs.filter(due_at__gt=now + timedelta(days=7))
        elif due == "none":
            qs = qs.filter(due_at__isnull=True)

        return qs.order_by("status", "due_at", "-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        items = list(ctx["tasks"])
        for t in items:
            t.can_complete = t.can_manual_complete(self.request.user)
        ctx["tasks"] = items
        ctx["status_choices"] = Task._meta.get_field("status").choices
        return ctx


class AllTaskListView(PermissionRequiredMixin, ListView):
    permission_required = "tasks.view_all_tasks"
    model = Task
    template_name = "tasks/all_list.html"
    context_object_name = "tasks"
    paginate_by = 24

    def get_queryset(self):
        qs = Task.objects.all()

        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))

        status = self.request.GET.get("status")
        valid_statuses = {choice[0] for choice in Task._meta.get_field("status").choices}
        if status in valid_statuses:
            qs = qs.filter(status=status)

        assignee_id = self.request.GET.get("assignee")
        if assignee_id:
            qs = qs.filter(assigned_to_id=assignee_id)

        due = self.request.GET.get("due")
        now = timezone.now()
        if due == "overdue":
            qs = qs.filter(status=TaskStatus.OPEN, due_at__lt=now)
        elif due == "week":
            qs = qs.filter(due_at__gte=now, due_at__lte=now + timedelta(days=7))
        elif due == "future":
            qs = qs.filter(due_at__gt=now + timedelta(days=7))
        elif due == "none":
            qs = qs.filter(due_at__isnull=True)

        return qs.order_by("status", "due_at", "-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        items = list(ctx["tasks"])
        for t in items:
            t.can_complete = t.can_manual_complete(self.request.user)
        ctx["tasks"] = items
        ctx["status_choices"] = Task._meta.get_field("status").choices
        return ctx


@login_required
def complete_task(request, pk):
    task = get_object_or_404(Task, pk=pk)

    # Optional belt-and-braces: block front-end completion for system tasks unless privileged
    if not task.allow_manual_complete and not (
        request.user.is_superuser or request.user.has_perm("tasks.view_all_tasks")
    ):
        messages.error(request, "This task auto-completes and can’t be manually completed.")
        return redirect(request.GET.get("next") or "tasks:my_list")

    if not task.can_manual_complete(request.user):
        messages.error(request, "You can’t manually complete this task.")
        return redirect(request.GET.get("next") or "tasks:my_list")

    task.status = TaskStatus.DONE
    task.save(update_fields=["status", "updated_at"])
    messages.success(request, "Task marked as done.")
    return redirect(request.GET.get("next") or "tasks:my_list")


@login_required
def dismiss_task(request, pk):
    task = get_object_or_404(Task, pk=pk)
    task.status = TaskStatus.DISMISSED
    task.save(update_fields=["status", "updated_at"])
    messages.success(request, "Task dismissed.")
    return redirect(request.GET.get("next") or "tasks:my_list")


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
        title = data["title"]
        description = data.get("description", "")
        due_at = data.get("due_at")
        complete_on = data.get("complete_on", "")
        allow_manual_complete = data.get("allow_manual_complete", True)

        assign_to_creator = data.get("assign_to_creator", True)
        fallback_assignee = data.get("fallback_assignee")

        player_types = data.get("player_types")
        teams = data.get("teams")
        products = data.get("products")
        season = data.get("season")
        only_without_subscription = data.get("only_without_subscription")

        Player = apps.get_model("members", "Player")
        TeamMembership = apps.get_model("members", "TeamMembership")
        Subscription = apps.get_model("memberships", "Subscription")

        # Build union of players matching selectors
        player_ids = set()

        if player_types and player_types.exists():
            ids = Player.objects.filter(player_type__in=player_types).values_list("id", flat=True)
            player_ids.update(ids)

        if teams and teams.exists():
            tm_qs = TeamMembership.objects.filter(team__in=teams).values_list("player_id", flat=True)
            player_ids.update(tm_qs)

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
            Player.objects.filter(id__in=player_ids).select_related("created_by").order_by("last_name", "first_name")
        )

        to_create = []
        missing_creator_count = 0

        for p in players:
            assignee = None
            if assign_to_creator:
                assignee = getattr(p, "created_by", None)
                if assignee is None and fallback_assignee:
                    assignee = fallback_assignee
                if assignee is None:
                    missing_creator_count += 1
            else:
                assignee = fallback_assignee  # could still be None

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
            note += f" {missing_creator_count} player(s) had no creator; tasks left unassigned"
            if fallback_assignee:
                note += " (or assigned to fallback)."
            else:
                note += "."
        messages.success(self.request, note)
        return super().form_valid(form)
