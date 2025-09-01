# tasks/urls.py
from django.urls import path
from . import views

app_name = "tasks"
urlpatterns = [
    path("", views.MyTaskListView.as_view(), name="my_list"),
    path("all/", views.AllTaskListView.as_view(), name="all_list"),
    path("<int:pk>/complete/", views.complete_task, name="complete"),
    path("<int:pk>/dismiss/", views.dismiss_task, name="dismiss"),
]
