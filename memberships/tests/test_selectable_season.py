from datetime import date

import pytest

from memberships.views import _get_selectable_season


@pytest.mark.django_db
def test_selectable_season_returns_current(season_current, season_next):
    # A date inside current season should return current
    sel = _get_selectable_season(today=date(2024, 12, 1))
    assert sel.name == "2024/25"


@pytest.mark.django_db
def test_selectable_season_returns_next_if_past(season_current, season_next):
    # After current season end -> returns earliest upcoming (season_next)
    sel = _get_selectable_season(today=date(2025, 4, 1))
    assert sel.name == "2025/26"
