from datetime import date

import pytest
from django.core.exceptions import ValidationError

from memberships.models import Season


@pytest.mark.django_db
def test_season_overlap_blocked():
    Season.objects.create(
        name="2024/25", start=date(2024, 10, 1), end=date(2025, 3, 31), is_active=False
    )

    s = Season(
        name="2025/Overlap",
        start=date(2025, 3, 15),
        end=date(2025, 10, 1),
        is_active=False,
    )
    with pytest.raises(ValidationError):
        s.full_clean()  # triggers Season.clean()
