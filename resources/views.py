from django.contrib.auth.mixins import PermissionRequiredMixin, LoginRequiredMixin
from django.views.generic import ListView
from .models import Policy, Document, Task


class PolicyListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Policy
    template_name = "resources/policy_list.html"
    context_object_name = "policies"
    permission_required = "resources.view_policy"
    raise_exception = True  # trigger 403 -> your denied page

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(is_active=True)


class DocumentListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Document
    template_name = "resources/document_list.html"
    context_object_name = "documents"
    permission_required = "resources.view_document"
    raise_exception = True

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(is_active=True)


class TaskListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Task
    template_name = "resources/task_list.html"
    context_object_name = "tasks"
    permission_required = "resources.view_task"
    raise_exception = True

    def get_queryset(self):
        qs = super().get_queryset().select_related("assigned_to")
        # Example: show all tasks to staff; otherwise show user’s tasks
        if self.request.user.is_staff or self.request.user.is_superuser:
            return qs
        return qs.filter(assigned_to=self.request.user)
