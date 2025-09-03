from datetime import date

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_senior_player_sees_only_senior_products(
    client, user, player_senior, product_senior_current, product_junior_current, monkeypatch
):
    client.login(username="alice", password="pw")

    # Force today's selection inside current season
    monkeypatch.setattr("memberships.views.localdate", lambda: date(2024, 12, 1))

    url = reverse("memberships:choose", args=[player_senior.id])
    resp = client.get(url)
    assert resp.status_code == 200

    products = list(resp.context["products"])
    names = {p.name for p in products}
    assert "Senior Full" in names
    assert "Junior" not in names  # filtered by category applies_to


@pytest.mark.django_db
def test_junior_player_sees_only_junior_products(
    client, user, player_junior, product_senior_current, product_junior_current, monkeypatch
):
    client.login(username="alice", password="pw")
    monkeypatch.setattr("memberships.views.localdate", lambda: date(2024, 12, 1))

    url = reverse("memberships:choose", args=[player_junior.id])
    resp = client.get(url)
    assert resp.status_code == 200

    products = list(resp.context["products"])
    names = {p.name for p in products}
    assert "Junior" in names
    assert "Senior Full" not in names
