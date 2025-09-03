import pytest
from datetime import date
from django.urls import reverse

from memberships.forms import ConfirmSubscriptionForm
from memberships.models import Subscription


@pytest.mark.django_db
def test_confirm_requires_terms_checkbox():
    # Form-level validation
    form = ConfirmSubscriptionForm(data={})
    assert not form.is_valid()
    assert "accept_terms" in form.errors

    form2 = ConfirmSubscriptionForm(data={"accept_terms": True})
    assert form2.is_valid()


@pytest.mark.django_db
def test_confirm_creates_pending_subscription(client, user, player_senior, product_senior_current, monkeypatch):
    client.login(username="alice", password="pw")
    monkeypatch.setattr("memberships.views.localdate", lambda: date(2024, 12, 1))

    # No plan needed -> confirm with plan_id=0 + product query param
    url = reverse("memberships:confirm", args=[player_senior.id, 0]) + f"?product={product_senior_current.id}"
    resp = client.post(url, data={"accept_terms": True}, follow=True)
    assert resp.status_code == 200
    sub = Subscription.objects.get(player=player_senior)
    assert sub.status == "pending"
    assert sub.product_id == product_senior_current.id
    assert sub.season_id == product_senior_current.season_id  # denormalised season set in save()


@pytest.mark.django_db
def test_duplicate_membership_blocked_by_unique_constraint(client, user, player_senior, product_senior_current, monkeypatch):
    client.login(username="alice", password="pw")
    monkeypatch.setattr("memberships.views.localdate", lambda: date(2024, 12, 1))

    # First create
    url = reverse("memberships:confirm", args=[player_senior.id, 0]) + f"?product={product_senior_current.id}"
    client.post(url, data={"accept_terms": True}, follow=True)

    # Attempt duplicate
    resp = client.post(url, data={"accept_terms": True}, follow=True)
    assert resp.status_code == 200
    assert Subscription.objects.filter(player=player_senior).count() == 1
