"""Django settings for the insurance policy management application."""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext_lazy as _
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def require_env(name: str) -> str:
    """Return a required environment variable with a non-empty value."""
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise ImproperlyConfigured(
            f"{name} environment variable is required and must be non-empty."
        )
    return value


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def env_positive_int(name: str, *, default: int) -> int:
    """Return a positive integer from the environment, or the default if unset."""
    if name not in os.environ:
        return default
    raw = os.environ[name]
    if not raw.strip():
        raise ImproperlyConfigured(
            f"{name} environment variable must be a positive integer."
        )
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise ImproperlyConfigured(
            f"{name} environment variable must be a positive integer."
        ) from exc
    if value <= 0:
        raise ImproperlyConfigured(
            f"{name} environment variable must be a positive integer."
        )
    return value


SECRET_KEY = require_env("DJANGO_SECRET_KEY")

DEBUG = env_bool("DJANGO_DEBUG", default=False)

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", default="localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "axes",
    "accounts",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
]

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

ROOT_URLCONF = "config.urls"

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
            ],
        },
    },
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

# Session lifetime for an internal office application.
# Idle timeout defaults to 8 hours, refreshed on activity; browser-close ends
# the cookie as well. Override age with DJANGO_SESSION_COOKIE_AGE (seconds).
SESSION_COOKIE_AGE = env_positive_int(
    "DJANGO_SESSION_COOKIE_AGE",
    default=8 * 60 * 60,
)
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "ubezpieczenia"),
        "USER": os.environ.get("POSTGRES_USER", "ubezpieczenia"),
        "PASSWORD": require_env("POSTGRES_PASSWORD"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

AUTH_USER_MODEL = "accounts.User"

LANGUAGE_CODE = "pl-pl"
TIME_ZONE = "Europe/Warsaw"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Login attempt protection (django-axes). State is stored in PostgreSQL so it
# remains effective across multiple application processes.
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True
AXES_LOCK_OUT_AT_FAILURE = True
AXES_COOLOFF_MESSAGE = _(
    "Too many failed login attempts. Please try again later."
)
AXES_PERMALOCK_MESSAGE = _(
    "Too many failed login attempts. Please try again later."
)
AXES_SENSITIVE_PARAMETERS = [
    "username",
    "ip_address",
    "password",
    "csrfmiddlewaretoken",
]
AXES_DISABLE_ACCESS_LOG = True
AXES_HTTP_RESPONSE_CODE = 429

# Production-oriented defaults when DEBUG is off.
if not DEBUG:
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", default=True)
    CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", default=True)
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", default=False)
