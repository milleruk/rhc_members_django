from django.urls import path
from . import views
from django.views.generic import TemplateView

urlpatterns = [
    path("policies/", views.PolicyListView.as_view(), name="policy_list"),
    path("documents/", views.DocumentListView.as_view(), name="document_list"),
    path("links/", TemplateView.as_view(template_name="resources/links.html"), name="links"),
]
