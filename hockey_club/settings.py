# settings.py
import os
from pathlib import Path

import environ
from celery.schedules import crontab
from django.contrib.messages import constants as messages

# ---------------------------------------------------------------------
# Base paths & environment
# ---------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    # Toggles & flags
    DEBUG=(bool, False),
    DISPLAY_DEBUG=(bool, False),
    # Core secrets
    SECRET_KEY=(str, ""),
    # Hosts
    ALLOWED_HOSTS=(list, []),
    CSRF_TRUSTED_ORIGINS=(list, []),
    # Email / SMTP
    EMAIL_BACKEND=(str, "django.core.mail.backends.smtp.EmailBackend"),
    EMAIL_HOST=(str, ""),
    EMAIL_PORT=(int, 587),
    EMAIL_USE_TLS=(bool, True),
    EMAIL_USE_SSL=(bool, False),
    EMAIL_HOST_USER=(str, ""),
    EMAIL_HOST_PASSWORD=(str, ""),
    DEFAULT_FROM_EMAIL=(str, "Redditch Hockey Club <noreply@example.com>"),
    ACCOUNT_EMAIL_SUBJECT_PREFIX=(str, "[Redditch HC] "),
    ACCOUNT_DEFAULT_HTTP_PROTOCOL=(str, "https"),
    # Database (supports DATABASE_URL)
    DATABASE_URL=(str, ""),  # e.g. mysql://user:pass@host:3306/db
    # Redis / Celery
    REDIS_URL=(str, "redis://localhost:6379/0"),
    # Allauth social providers
    SOCIAL_GOOGLE_CLIENT_ID=(str, ""),
    SOCIAL_GOOGLE_SECRET=(str, ""),
    SOCIAL_GITHUB_CLIENT_ID=(str, ""),
    SOCIAL_GITHUB_SECRET=(str, ""),
    SOCIAL_APPLE_CLIENT_ID=(str, ""),
    SOCIAL_APPLE_SECRET=(str, ""),
    SOCIAL_FACEBOOK_CLIENT_ID=(str, ""),
    SOCIAL_FACEBOOK_SECRET=(str, ""),
    # SPOND credentials
    SPOND_USERNAME=(str, ""),
    SPOND_PASSWORD=(str, ""),
    # Wallet / PassKit
    WALLET_APPLE_ENABLED=(bool, False),
    WALLETPASS_CERT_PATH=(str, ""),
    WALLETPASS_KEY_PATH=(str, ""),
    WALLETPASS_KEY_PASSWORD=(str, ""),
    WALLETPASS_PASS_TYPE_ID=(str, "pass.uk.yourclub.membership"),
    WALLETPASS_TEAM_ID=(str, "ABCDE12345"),
    WALLETPASS_SERVICE_URL=(str, "https://yourdomain.tld/api/passes/"),
    # Security flags
    SECURE_SSL_REDIRECT=(bool, False),  # default set after DEBUG is known
    SESSION_COOKIE_SECURE=(bool, False),
    CSRF_COOKIE_SECURE=(bool, False),
    SECURE_HSTS_SECONDS=(int, 0),
    SECURE_HSTS_INCLUDE_SUBDOMAINS=(bool, False),
    SECURE_HSTS_PRELOAD=(bool, False),
    SECURE_REFERRER_POLICY=(str, "strict-origin-when-cross-origin"),
    # Portal meta
    PORTAL_VERSION=(str, "v0.1.0"),
    PORTAL_BUILD=(str, "beta"),
    # MFA
    MFA_DEBUG=(bool, False),
)

environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

PORTAL_VERSION = env("PORTAL_VERSION")
PORTAL_BUILD = env("PORTAL_BUILD")

# ---------------------------------------------------------------------
# Core Django
# ---------------------------------------------------------------------
SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
DISPLAY_DEBUG = env("DISPLAY_DEBUG")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS")

SITE_ID = 1

INSTALLED_APPS = [
    # 3rd-party admin UI / tooling
    "jazzmin",
    "widget_tweaks",
    "rest_framework",
    # Django
    "django_celery_beat",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "django.contrib.humanize",
    # Allauth
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.socialaccount.providers.github",
    "allauth.socialaccount.providers.apple",
    "allauth.socialaccount.providers.facebook",
    "allauth.mfa",
    # Project apps
    "accounts",
    "members",
    "staff",
    "resources",
    "memberships",
    "spond_integration",
    "tasks",
    "club",
    "incidents",
    # Hijack (must be after members so the admin override is visible)
    "hijack",
    "hijack.contrib.admin",
    # Forms
    "crispy_forms",
    "crispy_bootstrap4",
]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "dashboard"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "hockey_club.middleware.LoginRequiredMiddleware",
    "hijack.middleware.HijackUserMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "hockey_club.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",  # required by allauth
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "members.context_processors.user_groups",
                "tasks.context_processors.task_counts",
                "tasks.context_processors.task_header",
                "hockey_club.context_processors.portal_meta",
                "hockey_club.context_processors.portal_breadcrumbs",
                "incidents.context_processors.navbar_incidents",
                "staff.context_processors.pending_subscriptions_badge",
            ],
        },
    },
]

WSGI_APPLICATION = "hockey_club.wsgi.application"

# ---------------------------------------------------------------------
# Database (DATABASE_URL or SQLite fallback)
# ---------------------------------------------------------------------
DATABASE_URL = env("DATABASE_URL")
if DATABASE_URL:
    DATABASES = {"default": env.db("DATABASE_URL")}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            "OPTIONS": {"timeout": 20},
        }
    }

# ---------------------------------------------------------------------
# Password validators
# ---------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------
# I18N / TZ
# ---------------------------------------------------------------------
LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Europe/London"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
if (BASE_DIR / "static").exists():
    STATICFILES_DIRS = [BASE_DIR / "static"]
else:
    STATICFILES_DIRS = []

# ---------------------------------------------------------------------
# Email / SMTP
# ---------------------------------------------------------------------
EMAIL_BACKEND = env("EMAIL_BACKEND")
EMAIL_HOST = env("EMAIL_HOST")
EMAIL_PORT = env.int("EMAIL_PORT")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS")
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL")
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")
ACCOUNT_EMAIL_SUBJECT_PREFIX = env("ACCOUNT_EMAIL_SUBJECT_PREFIX")

# Optional: adjust default port if SSL is explicitly chosen
if EMAIL_USE_SSL and EMAIL_PORT == 587:
    EMAIL_PORT = 465

# ---------------------------------------------------------------------
# Django-Allauth
# ---------------------------------------------------------------------
ACCOUNT_LOGOUT_REDIRECT_URL = "account_login"
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_CONFIRM_EMAIL_ON_GET = True
ACCOUNT_USER_MODEL_EMAIL_FIELD = "email"
ACCOUNT_SESSION_REMEMBER = None
ACCOUNT_DEFAULT_HTTP_PROTOCOL = env("ACCOUNT_DEFAULT_HTTP_PROTOCOL")

ACCOUNT_RATE_LIMITS = {"login_failed": "5/15m"}

ACCOUNT_FORMS = {
    "signup": "accounts.forms.AllauthSignupForm",
    "login": "accounts.forms.AllauthLoginForm",
    "reset_password": "accounts.forms.AllauthResetPasswordForm",
    "reset_password_from_key": "accounts.forms.AllauthResetPasswordKeyForm",
}

# Force username = email via adapter
ACCOUNT_ADAPTER = "accounts.adapter.RHCAccountAdapter"

# Optional custom whitelist for login-exempt URLs
LOGIN_EXEMPT_URLS = [
    r"^accounts/",
    r"^accounts/mfa/",
    r"^terms/$",
    r"^privacy/$",
    r"^static/",
    r"^media/",
]

# MFA
MFA_ADAPTER = "allauth.mfa.adapter.DefaultMFAAdapter"
MFA_DEBUG = env.bool("MFA_DEBUG", default=False)

SOCIALACCOUNT_ONLY = False
SOCIALACCOUNT_LOGIN_ON_GET = True

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APP": {
            "client_id": env("SOCIAL_GOOGLE_CLIENT_ID"),
            "secret": env("SOCIAL_GOOGLE_SECRET"),
            "key": "",
        },
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
    },
}

# ---------------------------------------------------------------------
# Security & misc
# ---------------------------------------------------------------------
X_FRAME_OPTIONS = "SAMEORIGIN"
SILENCED_SYSTEM_CHECKS = ["security.W019"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"

MESSAGE_TAGS = {
    messages.DEBUG: "secondary",
    messages.INFO: "info",
    messages.SUCCESS: "success",
    messages.WARNING: "warning",
    messages.ERROR: "danger",
}

# Env-driven security (defaults tighten automatically when not DEBUG)
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=not DEBUG)
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=not DEBUG)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=not DEBUG)
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0 if DEBUG else 31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=not DEBUG)
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)
SECURE_REFERRER_POLICY = env("SECURE_REFERRER_POLICY", default="strict-origin-when-cross-origin")

# ---------------------------------------------------------------------
# Crispy Forms
# ---------------------------------------------------------------------
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap4"
CRISPY_TEMPLATE_PACK = "bootstrap4"

# ---------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------
CELERY_BROKER_URL = env("REDIS_URL")
CELERY_RESULT_BACKEND = env("REDIS_URL")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
HOCKEYCLUB_BEAT_PREFIX = "settings:"

CELERY_BEAT_SCHEDULE = {
    # Send Email for Tasks
    "send-daily-task-digest": {
        "task": "tasks.tasks.send_daily_task_digest",
        "schedule": crontab(minute=0, hour=8),
    },
    "sync-spond-members-hourly": {
        "task": "spond_integration.tasks.sync_spond_members",
        "schedule": crontab(minute=0),
    },
    "sync-spond-events-6h": {
        "task": "spond_integration.tasks.sync_spond_events",
        "schedule": crontab(minute=0, hour="*/6"),
    },
}

# ---------------------------------------------------------------------
# Third-party creds
# ---------------------------------------------------------------------
SPOND_USERNAME = env("SPOND_USERNAME")
SPOND_PASSWORD = env("SPOND_PASSWORD")

# ---------------------------------------------------------------------
# Wallet / PassKit (compat with both dict & legacy flat settings)
# ---------------------------------------------------------------------
WALLET_APPLE_ENABLED = env.bool("WALLET_APPLE_ENABLED", default=False)
WALLETPASS = {
    "CERT_PATH": env("WALLETPASS_CERT_PATH", default=""),
    "KEY_PATH": env("WALLETPASS_KEY_PATH", default=""),
    "KEY_PASSWORD": (env("WALLETPASS_KEY_PASSWORD", default="") or None),
    "PASS_TYPE_ID": env("WALLETPASS_PASS_TYPE_ID", default="pass.uk.yourclub.membership"),
    "TEAM_ID": env("WALLETPASS_TEAM_ID", default="ABCDE12345"),
    "SERVICE_URL": env("WALLETPASS_SERVICE_URL", default="https://yourdomain.tld/api/passes/"),
    # Optional APNs (token-based) if you use it later:
    # "PUSH_AUTH_STRATEGY": "token",
    # "TOKEN_AUTH_KEY_PATH": env("WALLETPASS_TOKEN_KEY_P8", default=""),
    # "TOKEN_AUTH_KEY_ID": env("WALLETPASS_TOKEN_KEY_ID", default=""),
}
# Legacy aliases some code expects:
WALLETPASS_CERT = WALLETPASS["CERT_PATH"]
WALLETPASS_CERT_KEY = WALLETPASS["KEY_PATH"]

# Auto-enable django_walletpass only when explicitly enabled AND certs are present
if WALLET_APPLE_ENABLED and WALLETPASS["CERT_PATH"] and WALLETPASS["KEY_PATH"]:
    INSTALLED_APPS.append("django_walletpass")

# ---------------------------------------------------------------------
# Optional: prevent prod boot with missing envs
# ---------------------------------------------------------------------
if not DEBUG:
    required_env = ["SECRET_KEY", "ALLOWED_HOSTS"]
    missing = [k for k in required_env if not env(k, default="")]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables in production: {', '.join(missing)}"
        )
