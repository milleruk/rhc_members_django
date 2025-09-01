# tasks/views.py
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import ListView

from .models import Task, TaskStatus


class MyTaskListView(LoginRequiredMixin, ListView):
    model = Task
    template_name = "tasks/my_list.html"
    context_object_name = "tasks"
    paginate_by = 18  # optional; tweak to taste

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
        # annotate per-object flag the template can read (can’t call methods with args in templates)
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

        # Optional filters: q, status, assignee, due
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
        # Admins can always complete manually (per can_manual_complete logic)
        for t in items:
            t.can_complete = t.can_manual_complete(self.request.user)
        ctx["tasks"] = items
        ctx["status_choices"] = Task._meta.get_field("status").choices
        return ctx


@login_required
def complete_task(request, pk):
    task = get_object_or_404(Task, pk=pk)
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
    # Optional: if you also want to restrict dismissing system tasks, add a similar guard here.
    task.status = TaskStatus.DISMISSED
    task.save(update_fields=["status", "updated_at"])
    messages.success(request, "Task dismissed.")
    return redirect(request.GET.get("next") or "tasks:my_list")
