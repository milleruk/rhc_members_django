# conftest.py
import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture(autouse=True)
def disable_consent_gate(settings):
    """
    Disable the accounts consent middleware during tests.
    Prevents redirects to /accounts/consents/ breaking client flows.
    """
    settings.ACCOUNTS_REQUIRE_CONSENT = False


@pytest.fixture(autouse=True)
def ensure_static_and_media_dirs(settings, tmp_path):
    """
    Ensure STATIC_ROOT and MEDIA_ROOT are writable during tests.
    Avoids warnings about missing staticfiles/ directories in CI.
    """
    static_dir = tmp_path / "static"
    media_dir = tmp_path / "media"
    static_dir.mkdir(exist_ok=True)
    media_dir.mkdir(exist_ok=True)
    settings.STATIC_ROOT = str(static_dir)
    settings.MEDIA_ROOT = str(media_dir)


@pytest.fixture
def consent_user():
    """
    Helper: mark a given user as 'consented'.
    Usage: consent_user(user)
    """

    def _consent(user):
        profile = getattr(user, "profile", None)
        if profile and hasattr(profile, "consented"):
            profile.consented = True
            profile.save(update_fields=["consented"])
        elif hasattr(user, "consented"):
            # fallback if stored directly on user
            user.consented = True
            user.save(update_fields=["consented"])

    return _consent


@pytest.fixture
def admin_user(db):
    """
    Create and return a superuser for tests.
    """
    return User.objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password="password123",
    )
