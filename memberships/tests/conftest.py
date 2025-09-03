# tests/conftest.py
import pytest
from datetime import date
from django.contrib.auth import get_user_model

from members.models import Player, PlayerType
from memberships.models import (
    Season, MembershipCategory, MembershipProduct, PaymentPlan
)

User = get_user_model()


@pytest.fixture
def user(db):
    # ✅ unique email
    return User.objects.create_user(
        username="alice",
        email="alice@example.test",
        password="pw"
    )


@pytest.fixture
def admin_user(db):
    # ✅ unique email & superuser
    return User.objects.create_superuser(
        username="admin",
        email="admin@example.test",
        password="pw"
    )


@pytest.fixture
def senior_type(db):
    return PlayerType.objects.create(name="Senior")


@pytest.fixture
def junior_type(db):
    return PlayerType.objects.create(name="Junior")


@pytest.fixture
def player_senior(db, user, senior_type):
    # ✅ date_of_birth is REQUIRED by your model
    # Senior: make them clearly over 18
    return Player.objects.create(
        first_name="Sam",
        last_name="Smith",
        player_type=senior_type,
        created_by=user,
        date_of_birth=date(1990, 1, 1),
        gender="other",  # adjust to a valid choice for your model
    )


@pytest.fixture
def player_junior(db, user, junior_type):
    # Junior: clearly under 18 (example DOB)
    return Player.objects.create(
        first_name="Jack",
        last_name="Jones",
        player_type=junior_type,
        created_by=user,
        date_of_birth=date(2012, 6, 15),
        gender="other",  # adjust to a valid choice for your model
    )


@pytest.fixture
def season_current(db):
    # 2024/25
    return Season.objects.create(
        name="2024/25",
        start=date(2024, 10, 1),
        end=date(2025, 3, 31),
        is_active=True,  # not used by selection logic, ok to set
    )


@pytest.fixture
def season_next(db):
    # 2025/26
    return Season.objects.create(
        name="2025/26",
        start=date(2025, 10, 1),
        end=date(2026, 3, 31),
        is_active=False,
    )


@pytest.fixture
def cat_senior(db, senior_type):
    c = MembershipCategory.objects.create(code="senior", label="Senior")
    c.applies_to.add(senior_type)
    return c


@pytest.fixture
def cat_junior(db, junior_type):
    c = MembershipCategory.objects.create(code="junior", label="Junior")
    c.applies_to.add(junior_type)
    return c


@pytest.fixture
def product_senior_current(db, cat_senior, season_current):
    return MembershipProduct.objects.create(
        season=season_current,
        category=cat_senior,
        name="Senior Full",
        sku="senior-full",
        list_price_gbp=120,
        active=True,
        requires_plan=False,
    )


@pytest.fixture
def product_junior_current(db, cat_junior, season_current):
    return MembershipProduct.objects.create(
        season=season_current,
        category=cat_junior,
        name="Junior",
        sku="junior",
        list_price_gbp=60,
        active=True,
        requires_plan=False,
    )


@pytest.fixture
def product_senior_next(db, cat_senior, season_next):
    return MembershipProduct.objects.create(
        season=season_next,
        category=cat_senior,
        name="Senior Full (Next)",
        sku="senior-full-next",
        list_price_gbp=130,
        active=True,
        requires_plan=False,
    )


@pytest.fixture
def plan_monthly(db, product_senior_current):
    return PaymentPlan.objects.create(
        product=product_senior_current,
        label="£10 x 12",
        instalment_amount_gbp=10,
        instalment_count=12,
        frequency="monthly",
        includes_match_fees=True,
        active=True,
        display_order=1,
    )
