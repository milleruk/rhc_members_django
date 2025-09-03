import pytest
from datetime import date
from django.urls import reverse

from memberships.models import Subscription


@pytest.mark.django_db
def test_my_memberships_annotation_has_sub_this_season(client, user, player_senior, product_senior_current, monkeypatch):
    client.login(username="alice", password="pw")
    monkeypatch.setattr("memberships.views.localdate", lambda: date(2024, 12, 1))

    # No sub yet -> has_sub_this_season should be Falsey
    url = reverse("memberships:mine")
    resp = client.get(url)
    assert resp.status_code == 200
    players = list(resp.context["players"])
    p = next(pp for pp in players if pp.id == player_senior.id)
    assert not getattr(p, "has_sub_this_season", False)

    # Create sub -> should annotate True
    Subscription.objects.create(player=player_senior, product=product_senior_current, plan=None, status="pending", season=product_senior_current.season)
    resp2 = client.get(url)
    players2 = list(resp2.context["players"])
    p2 = next(pp for pp in players2 if pp.id == player_senior.id)
    assert getattr(p2, "has_sub_this_season", False)
