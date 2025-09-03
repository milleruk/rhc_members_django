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


def _get_task_model():
    try:
        from tasks.models import Task

        return Task
    except Exception:
        return None


def _create_team_review_tasks(incident):
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

    # Preferred M2M path
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

    # Fallback single-assignee path
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


class IncidentListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "incidents.view_incident"
    template_name = "incidents/incident_list.html"
    context_object_name = "incidents"
    paginate_by = 25

    def get_queryset(self):
        u = self.request.user
        qs = Incident.objects.all()

        # If user lacks 'view_sensitive', hide others' sensitive items.
        if not u.has_perm("incidents.view_sensitive"):
            qs = (
                qs.exclude(is_sensitive=True)
                .union(Incident.objects.filter(is_sensitive=True, reported_by=u))
                .union(Incident.objects.filter(is_sensitive=True, assigned_to=u))
            )

        # Non-assigners cannot see incidents they didn't report or aren't assigned to?
        # (Optional) leave list permission to govern visibility only via sensitive filter above.

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
    permission_required = "incidents.view_incident"
    model = Incident
    template_name = "incidents/incident_detail.html"
    context_object_name = "incident"

    def get_queryset(self):
        u = self.request.user
        qs = super().get_queryset()
        if not u.has_perm("incidents.view_sensitive"):
            qs = (
                qs.exclude(is_sensitive=True)
                .union(
                    Incident.objects.filter(pk=self.kwargs["pk"], is_sensitive=True, reported_by=u)
                )
                .union(
                    Incident.objects.filter(pk=self.kwargs["pk"], is_sensitive=True, assigned_to=u)
                )
            )
        return qs


class IncidentCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = "incidents.submit_incident"
    model = Incident
    form_class = IncidentForm
    template_name = "incidents/incident_form.html"
    success_url = reverse_lazy("incidents:list")

    def form_valid(self, form):
        form.instance.reported_by = self.request.user
        # Enforce default status
        form.instance.status = Incident.Status.SUBMITTED
        res = super().form_valid(form)
        # Ensure review tasks are created even if signals aren’t wired
        _create_team_review_tasks(self.object)
        messages.success(self.request, "Incident submitted and routed to reviewers.")
        return res


class IncidentUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = "incidents.submit_incident"
    model = Incident
    form_class = IncidentForm
    template_name = "incidents/incident_form.html"

    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        # block edits on closed
        if obj.status == Incident.Status.CLOSED:
            return HttpResponseForbidden("Closed incidents cannot be edited.")
        # if assigned, only assignee may edit (even if can_action_incident)
        if (
            obj.status in (Incident.Status.ASSIGNED, Incident.Status.ACTION_REQUIRED)
            and obj.assigned_to_id
        ):
            if obj.assigned_to_id != request.user.id:
                return HttpResponseForbidden("Only the assignee can edit this incident.")
        return super().dispatch(request, *args, **kwargs)


class IncidentActionView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """For reviewers/safeguarding officers to move workflow forward."""

    permission_required = "incidents.can_action_incident"
    model = Incident
    form_class = IncidentActionForm
    template_name = "incidents/incident_action.html"

    def form_valid(self, form):
        messages.success(self.request, "Incident actioned.")
        return super().form_valid(form)


class AssignToMeView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "incidents.assign_incident"

    def post(self, request, pk):
        incident = get_object_or_404(Incident, pk=pk)
        # Only allow assignment if not already closed
        if incident.status == Incident.Status.CLOSED:
            messages.warning(request, "Incident is already closed.")
            return redirect(incident.get_absolute_url())

        incident.assigned_to = request.user
        incident.assigned_at = timezone.now()
        incident.status = Incident.Status.ASSIGNED
        incident.save(update_fields=["assigned_to", "assigned_at", "status", "last_updated"])
        messages.success(request, "You are now assigned to this incident.")
        return redirect(incident.get_absolute_url())


class MarkActionRequiredView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "incidents.complete_review"

    def post(self, request, pk):
        incident = get_object_or_404(Incident, pk=pk)
        if incident.status == Incident.Status.CLOSED:
            messages.warning(request, "Incident is already closed.")
            return redirect(incident.get_absolute_url())

        if not incident.assigned_to:
            incident.assigned_to = request.user
            incident.assigned_at = timezone.now()

        incident.status = Incident.Status.ACTION_REQUIRED
        incident.save(update_fields=["assigned_to", "assigned_at", "status", "last_updated"])
        messages.info(request, "Incident marked as Action Required.")
        return redirect(incident.get_absolute_url())


class CloseIncidentView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "incidents.complete_review"

    def post(self, request, pk):
        incident = get_object_or_404(Incident, pk=pk)
        incident.status = Incident.Status.CLOSED
        incident.save(update_fields=["status", "last_updated"])
        messages.success(request, "Incident closed.")
        return redirect(incident.get_absolute_url())


class UnassignView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "incidents.assign_incident"

    def post(self, request, pk):
        incident = get_object_or_404(Incident, pk=pk)
        if incident.status == Incident.Status.CLOSED:
            messages.warning(request, "Incident is closed.")
            return redirect(incident.get_absolute_url())

        # Only current assignee (or someone with permission) can unassign; prefer self-unassign
        if incident.assigned_to_id and incident.assigned_to_id != request.user.id:
            # strict: block non-assignee from unassigning
            return HttpResponseForbidden("Only the current assignee can unassign.")

        # Close their personal review/action tasks and return to queue
        Task = _get_task_model()
        if Task:
            # close any personal tasks for this incident by simple title match
            for tag in ("[REVIEW (Assigned)]", "[ACTION NEEDED]"):
                qs = Task.objects.all()
                if hasattr(Task, "is_complete"):
                    qs = qs.filter(is_complete=False)
                title_like = f"{tag} Incident #{incident.pk}"
                for t in qs:
                    if title_like in t.title:
                        if hasattr(t, "is_complete"):
                            t.is_complete = True
                            t.save(update_fields=["is_complete"])
                        elif hasattr(t, "completed_at"):
                            t.completed_at = timezone.now()
                            t.save(update_fields=["completed_at"])
                        else:
                            t.delete()

        incident.assigned_to = None
        incident.assigned_at = None
        incident.status = Incident.Status.SUBMITTED
        incident.save(update_fields=["assigned_to", "assigned_at", "status", "last_updated"])
        # Recreate team review tasks
        _create_team_review_tasks(incident)

        messages.info(request, "Incident returned to the review queue.")
        return redirect(incident.get_absolute_url())
