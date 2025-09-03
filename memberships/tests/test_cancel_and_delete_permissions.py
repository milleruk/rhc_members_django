import pytest
from datetime import date
from django.urls import reverse

from memberships.models import Subscription


@pytest.mark.django_db
def test_non_admin_cannot_cancel_active(client, user, player_senior, product_senior_current):
    client.login(username="alice", password="pw")

    sub = Subscription.objects.create(
        player=player_senior,
        product=product_senior_current,
        plan=None,
        status="active",
        season=product_senior_current.season,
        created_by=user,
    )

    url = reverse("memberships:subscription_cancel", args=[sub.id])
    resp = client.post(url, follow=True)
    sub.refresh_from_db()
    assert sub.status == "active"  # unchanged
    # message added; response ok
    assert resp.status_code == 200


@pytest.mark.django_db
def test_admin_can_cancel_active(client, admin_user, player_senior, product_senior_current):
    client.login(username="admin", password="pw")

    sub = Subscription.objects.create(
        player=player_senior,
        product=product_senior_current,
        plan=None,
        status="active",
        season=product_senior_current.season,
        created_by=admin_user,
    )

    url = reverse("memberships:subscription_cancel", args=[sub.id])
    resp = client.post(url, follow=True)
    sub.refresh_from_db()
    assert sub.status == "cancelled"
    assert resp.status_code == 200
