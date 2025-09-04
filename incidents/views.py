# incidents/views.py

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import IncidentActionForm, IncidentForm
from .models import Incident, IncidentRouting

# -----------------------------
# Task helpers (defensive: only use fields your Task model actually has)
# -----------------------------


def _get_task_model():
    try:
        from tasks.models import Task

        return Task
    except Exception:
        return None


def _create_team_review_tasks(incident):
    """
    Create initial REVIEW tasks to the active routing reviewers.
    Tasks are flagged as auto and not manually completable when supported.
    """
    Task = _get_task_model()
    if not Task:
        return

    reviewer_ids = IncidentRouting.objects.filter(is_active=True).values_list(
        "reviewers__id", flat=True
    )
    reviewers = get_user_model().objects.filter(id__in=reviewer_ids).distinct()
    if not reviewers:
        return

    title = f"[REVIEW] Incident #{incident.pk}: {incident.summary[:60]}"
    desc = (
        "A new incident has been submitted and needs review.\n\n"
        f"Location: {incident.location}\n"
        f"Date/Time: {incident.incident_datetime:%Y-%m-%d %H:%M}\n"
        f"Open: {incident.get_absolute_url()}"
    )

    # Preferred M2M assignees path
    if hasattr(Task, "assignees"):
        t = Task.objects.create(
            title=title,
            description=desc,
            **({"allow_manual_complete": False} if hasattr(Task, "allow_manual_complete") else {}),
            **({"is_auto": True} if hasattr(Task, "is_auto") else {}),
            **({"task_type": "incident_review"} if hasattr(Task, "task_type") else {}),
        )
        t.assignees.add(*list(reviewers))
        return

    # Fallback: one task per reviewer
    for u in reviewers:
        kwargs = dict(
            title=title,
            description=desc,
        )
        if hasattr(Task, "assigned_to"):
            kwargs["assigned_to"] = u
        if hasattr(Task, "allow_manual_complete"):
            kwargs["allow_manual_complete"] = False
        if hasattr(Task, "is_auto"):
            kwargs["is_auto"] = True
        if hasattr(Task, "task_type"):
            kwargs["task_type"] = "incident_review"
        Task.objects.create(**kwargs)


def _close_open_tasks_for_incident_by_tag(tag_prefix, incident):
    """
    Soft-close tasks for this incident by matching a tag prefix in the title.
    If your Task model has a FK to Incident later, replace this with a direct filter.
    """
    Task = _get_task_model()
    if not Task:
        return
    title_like = f"{tag_prefix} Incident #{incident.pk}"
    qs = Task.objects.all()
    # narrow cheaply if there is a title field index; otherwise iterate
    for t in qs:
        title = getattr(t, "title", "") or ""
        if title_like in title:
            # prefer marking complete over deletion unless your policy is hard delete
            if hasattr(t, "is_complete"):
                t.is_complete = True
                t.save(update_fields=["is_complete"])
            elif hasattr(t, "completed_at"):
                t.completed_at = timezone.now()
                t.save(update_fields=["completed_at"])
            else:
                try:
                    t.delete()
                except Exception:
                    # ignore if cannot delete
                    pass


# -----------------------------
# Query helpers
# -----------------------------


def _apply_sensitive_visibility_filter(qs, user):
    """
    If user lacks 'incidents.view_sensitive', hide others' sensitive items:
      show (not sensitive) OR (sensitive & (reported_by=user OR assigned_to=user))
    """
    if user.has_perm("incidents.view_sensitive"):
        return qs
    return qs.filter(
        Q(is_sensitive=False)
        | Q(is_sensitive=True, reported_by=user)
        | Q(is_sensitive=True, assigned_to=user)
    )


# -----------------------------
# List / Detail
# -----------------------------


class IncidentListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """
    Requires:
      - incidents.access_app
      - incidents.view_incident  (Django default view permission)
      - incidents.view_list
    """

    permission_required = ("incidents.access_app", "incidents.view_incident", "incidents.view_list")
    template_name = "incidents/incident_list.html"
    context_object_name = "incidents"
    paginate_by = 25

    def get_queryset(self):
        u = self.request.user
        qs = Incident.objects.all()
        qs = _apply_sensitive_visibility_filter(qs, u)

        search = self.request.GET.get("q")
        status = self.request.GET.get("status")
        if search:
            qs = qs.filter(
                Q(summary__icontains=search)
                | Q(description__icontains=search)
                | Q(location__icontains=search)
            )
        if status:
            qs = qs.filter(status=status)
        return qs.select_related("team", "primary_player", "reported_by", "assigned_to")


class IncidentDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = ("incidents.access_app", "incidents.view_incident")
    model = Incident
    template_name = "incidents/incident_detail.html"
    context_object_name = "incident"

    def get_queryset(self):
        u = self.request.user
        qs = super().get_queryset()
        qs = _apply_sensitive_visibility_filter(qs, u)
        return qs


# -----------------------------
# Create / Update (edit guards inside dispatch)
# -----------------------------


class IncidentCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = ("incidents.access_app", "incidents.submit_incident")
    model = Incident
    form_class = IncidentForm
    template_name = "incidents/incident_form.html"
    success_url = reverse_lazy("incidents:list")

    def form_valid(self, form):
        # Default status: Submitted (internal)
        form.instance.reported_by = self.request.user
        form.instance.status = Incident.Status.SUBMITTED
        res = super().form_valid(form)
        # Ensure initial review tasks are created even if signals are not wired
        _create_team_review_tasks(self.object)
        messages.success(self.request, "Incident submitted and routed to reviewers.")
        return res


class IncidentUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = ("incidents.access_app", "incidents.change_incident")
    model = Incident
    form_class = IncidentForm
    template_name = "incidents/incident_form.html"

    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        # Closed incidents are immutable
        if obj.status == Incident.Status.CLOSED:
            return HttpResponseForbidden("Closed incidents cannot be edited.")
        # While assigned / action_required, only assignee may edit
        if (
            obj.status in (Incident.Status.ASSIGNED, Incident.Status.ACTION_REQUIRED)
            and obj.assigned_to_id
        ):
            if obj.assigned_to_id != request.user.id:
                return HttpResponseForbidden("Only the assignee can edit this incident.")
        return super().dispatch(request, *args, **kwargs)


# -----------------------------
# Action/Review form (review-only fields)
# -----------------------------


class IncidentActionView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """
    Review form for safeguarding/EH fields; status transitions are button-driven.
    Only assignee may update when assigned/action_required.
    """

    permission_required = ("incidents.access_app", "incidents.complete_review")
    model = Incident
    form_class = IncidentActionForm
    template_name = "incidents/incident_action.html"

    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        # Closed incidents are immutable
        if obj.status == Incident.Status.CLOSED:
            return HttpResponseForbidden("Closed incidents cannot be edited.")
        # Only assignee can use review form while assigned/action_required
        if (
            obj.status in (Incident.Status.ASSIGNED, Incident.Status.ACTION_REQUIRED)
            and obj.assigned_to_id
        ):
            if obj.assigned_to_id != request.user.id:
                return HttpResponseForbidden("Only the assignee can update this incident.")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, "Incident updated.")
        return super().form_valid(form)


# -----------------------------
# Workflow endpoints
# -----------------------------


class AssignToMeView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = ("incidents.access_app", "incidents.assign_incident")

    def post(self, request, pk):
        incident = get_object_or_404(Incident, pk=pk)

        if incident.status == Incident.Status.CLOSED:
            messages.warning(request, "Incident is already closed.")
            return redirect(incident.get_absolute_url())

        if incident.assigned_to_id:
            messages.info(request, "Incident is already assigned.")
            return redirect(incident.get_absolute_url())

        incident.assigned_to = request.user
        incident.assigned_at = timezone.now()
        incident.status = Incident.Status.ASSIGNED
        incident.save(update_fields=["assigned_to", "assigned_at", "status", "last_updated"])

        # Team review tasks will be auto-closed & personal review task created by signals.
        messages.success(request, "You are now assigned to this incident.")
        return redirect(incident.get_absolute_url())


class UnassignView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = ("incidents.access_app", "incidents.assign_incident")

    def post(self, request, pk):
        incident = get_object_or_404(Incident, pk=pk)

        if incident.status == Incident.Status.CLOSED:
            messages.warning(request, "Incident is closed.")
            return redirect(incident.get_absolute_url())

        # Only current assignee can unassign
        if incident.assigned_to_id and incident.assigned_to_id != request.user.id:
            return HttpResponseForbidden("Only the current assignee can unassign this incident.")

        # Close personal tasks for this incident (REVIEW (Assigned), ACTION NEEDED)
        _close_open_tasks_for_incident_by_tag("[REVIEW (Assigned)]", incident)
        _close_open_tasks_for_incident_by_tag("[ACTION NEEDED]", incident)

        # Return to queue
        incident.assigned_to = None
        incident.assigned_at = None
        incident.status = Incident.Status.SUBMITTED
        incident.save(update_fields=["assigned_to", "assigned_at", "status", "last_updated"])

        # Recreate team review tasks so others see it
        _create_team_review_tasks(incident)

        messages.info(request, "Incident returned to the review queue.")
        return redirect(incident.get_absolute_url())


class MarkActionRequiredView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = ("incidents.access_app", "incidents.complete_review")

    def post(self, request, pk):
        incident = get_object_or_404(Incident, pk=pk)

        if incident.status == Incident.Status.CLOSED:
            messages.warning(request, "Incident is already closed.")
            return redirect(incident.get_absolute_url())

        # Ensure an assignee exists (self-assign if needed)
        if not incident.assigned_to_id:
            incident.assigned_to = request.user
            incident.assigned_at = timezone.now()

        incident.status = Incident.Status.ACTION_REQUIRED
        incident.save(update_fields=["assigned_to", "assigned_at", "status", "last_updated"])

        # Signals handle closing personal REVIEW task and creating ACTION NEEDED task
        messages.info(request, "Incident marked as Action Required.")
        return redirect(incident.get_absolute_url())


class CloseIncidentView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = ("incidents.access_app", "incidents.complete_review")

    def post(self, request, pk):
        incident = get_object_or_404(Incident, pk=pk)
        if incident.status == Incident.Status.CLOSED:
            messages.info(request, "Incident already closed.")
            return redirect(incident.get_absolute_url())

        incident.status = Incident.Status.CLOSED
        incident.save(update_fields=["status", "last_updated"])

        # Signals will auto-complete any open tasks for this incident
        messages.success(request, "Incident closed.")
        return redirect(incident.get_absolute_url())
