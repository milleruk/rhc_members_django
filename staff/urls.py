# staff/urls.py
from django.urls import path

from . import views
from .views import (
    MembershipOverviewView,
    SubscriptionListView,
    activate_subscription,
    cancel_subscription,
    set_pending_subscription,
)

app_name = "staff"

urlpatterns = [
    path("", views.StaffHomeView.as_view(), name="home"),
    path("players/", views.PlayerListView.as_view(), name="player_list"),
    path("players/<int:player_id>/", views.PlayerDetailView.as_view(), name="player_detail"),
    path(
        "memberships/<int:membership_id>/remove/", views.remove_membership, name="remove_membership"
    ),
    # Memberships
    path("memberships/", MembershipOverviewView.as_view(), name="memberships_overview"),
    path("memberships/list/", SubscriptionListView.as_view(), name="memberships_list"),
    path(
        "memberships/<int:subscription_id>/activate/",
        activate_subscription,
        name="activate_subscription",
    ),
    path(
        "memberships/<int:subscription_id>/set_pending/",
        set_pending_subscription,
        name="set_pending_subscription",
    ),
    path(
        "memberships/<int:subscription_id>/cancel/", cancel_subscription, name="cancel_subscription"
    ),
]
