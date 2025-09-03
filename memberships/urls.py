from django.urls import path

from . import views

app_name = "memberships"

urlpatterns = [
    path("choose/<int:player_id>/", views.choose_product, name="choose"),
    path("plan/<int:player_id>/<int:product_id>/", views.choose_plan, name="choose_plan"),
    path("confirm/<int:player_id>/<int:plan_id>/", views.confirm, name="confirm"),
    path("mine/", views.my_memberships, name="mine"),
    path(
        "subscription/<int:sub_id>/cancel/",
        views.subscription_cancel,
        name="subscription_cancel",
    ),
    path(
        "subscription/<int:sub_id>/delete/",
        views.subscription_delete,
        name="subscription_delete",
    ),
]
