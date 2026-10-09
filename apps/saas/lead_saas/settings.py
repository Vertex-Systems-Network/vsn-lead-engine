"""Opt-in SaaS settings. No production collector stores or credentials are used."""

import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .web_origin import dashboard_return

BASE_DIR = Path(__file__).resolve().parent.parent
# Reuse the repository's pure SaaS policy contracts without importing collector services.
sys.path.insert(0, str(BASE_DIR.parent.parent / "src"))
DEBUG = os.environ.get("SAAS_DEBUG", "0") == "1"
SECRET_KEY = os.environ.get("SAAS_SECRET_KEY", "")
if not SECRET_KEY:
    raise ImproperlyConfigured("SAAS_SECRET_KEY is required")
ALLOWED_HOSTS = os.environ.get("SAAS_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "core",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "lead_saas.urls"
WSGI_APPLICATION = "lead_saas.wsgi.application"
AUTH_USER_MODEL = "core.User"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("SAAS_DB_NAME", "lead_saas"),
        "USER": os.environ.get("SAAS_DB_USER", "lead_saas"),
        "PASSWORD": os.environ.get("SAAS_DB_PASSWORD", ""),
        "HOST": os.environ.get("SAAS_DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("SAAS_DB_PORT", "5432"),
        "CONN_MAX_AGE": 0,
    }
}
# Explicit disposable local smoke mode; never row-lock/concurrency certification.
if os.environ.get("SAAS_SQLITE_SMOKE", "0") == "1":
    if not DEBUG:
        raise ImproperlyConfigured("SQLite smoke mode requires SAAS_DEBUG=1")
    DATABASES = {
        "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "smoke.sqlite3"}
    }
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_PAGINATION_CLASS": "core.pagination.BoundedPagination",
    "PAGE_SIZE": 25,
}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
DATA_UPLOAD_MAX_MEMORY_SIZE = 65536
LOGIN_URL = "/accounts/login/"
WEB_DASHBOARD_URL = dashboard_return(os.environ.get("SAAS_WEB_ORIGIN", ""), debug=DEBUG)
CSRF_TRUSTED_ORIGINS = [WEB_DASHBOARD_URL.removesuffix("/dashboard")] if WEB_DASHBOARD_URL else []
LOGIN_REDIRECT_URL = WEB_DASHBOARD_URL or "/"
LOGOUT_REDIRECT_URL = WEB_DASHBOARD_URL or "/accounts/login/"
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_TZ = True
STATIC_URL = "/static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Internal verifier registry is empty by default. Provision only through trusted
# server settings after provider-specific review; no environment/HTTP key input.
SAAS_RECEIPT_VERIFIERS = {}
# Separate, internal-only candidate evidence. No provider or ingestion is enabled.
SAAS_RESULT_VERIFIERS = {}
# Independent source receipt and isolated R2/qualification attestation authorities.
# No provider, registry signer or payload intake is activated by these empty maps.
SAAS_ACCEPTANCE_VERIFIERS = {}
SAAS_DEDUPE_VERIFIERS = {}
# Separate normalized billing-event adapter authority; no webhook/payment enabled.
SAAS_BILLING_VERIFIERS = {}

# Internal reconciliation stays disabled until external provider/operational review.
SAAS_BILLING_RECONCILIATION_ENABLED = False
# Future v3 batch proof authorities remain separate, empty and without a consumer.
SAAS_BATCH_VERIFIERS = {}
SAAS_BATCH_DEDUPE_VERIFIERS = {}
# Separate source-final authority; empty by default and no intake service enabled.
SAAS_BATCH_TERMINAL_VERIFIERS = {}
# Separate authoritative zero-effect source keys; no provider is enrolled.
SAAS_BATCH_NOEFFECT_VERIFIERS = {}

# Enrollment only; batch dispatch/intake remain unavailable even when locally enabled.
SAAS_BATCH_ENROLLMENT_ENABLED = False
SAAS_BATCH_ENROLLMENT_SOURCES = frozenset()

# Quarantined allocation primitive; ordinary dispatch still refuses v3 jobs.
SAAS_BATCH_ALLOCATION_ENABLED = False

# Pure candidate-batch proof authority; no intake consumer is enabled.
SAAS_BATCH_CANDIDATE_VERIFIERS = {}

# Internal redacted evidence only; consumer and accepted payload intake remain off.
SAAS_BATCH_CANDIDATE_EVENTS_ENABLED = False

# Internal v3 payload intake stays unreachable until signer, R2 and terminal
# accounting gates are independently verified. No HTTP route enables this flag.
SAAS_BATCH_ACCEPTANCE_ENABLED = False

# Source-final metadata remains internal and default-off. Whole-job accounting
# and no-effect proof are separate capabilities, never implied by this flag.
SAAS_BATCH_TERMINAL_EVENTS_ENABLED = False

# Entire-job positive-result accounting is internal and separately disabled.
# Unknown/no-effect recovery and settled-state replay are not activated.
SAAS_BATCH_SETTLEMENT_ENABLED = False
SAAS_BATCH_SETTLED_REPLAY_ENABLED = False

# Future v3 page continuation uses an independent key; empty disables issuance.
# It does not turn on a result route or weaken current-rights checks.
SAAS_BATCH_PAGE_SIGNING_KEY = ""
SAAS_BATCH_PAGE_READ_ENABLED = False
