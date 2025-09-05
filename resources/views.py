from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView

from .models import Document, Policy


class PolicyListView(LoginRequiredMixin, ListView):
    model = Policy
    template_name = "resources/policy_list.html"
    context_object_name = "policies"

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(is_active=True)


class DocumentListView(LoginRequiredMixin, ListView):
    model = Document
    template_name = "resources/document_list.html"
    context_object_name = "documents"

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(is_active=True)
