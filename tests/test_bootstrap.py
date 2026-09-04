"""Bootstrap tests for the Django foundation."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from django.db.utils import OperationalError
from django.test import Client
from django.urls import reverse

from config.settings import require_env


def test_require_env_returns_existing_nonempty_value(monkeypatch):
    monkeypatch.setenv("BOOT_REQUIRED_TEST_VALUE", "configured-value")
    assert require_env("BOOT_REQUIRED_TEST_VALUE") == "configured-value"


def test_require_env_rejects_missing_value(monkeypatch):
    monkeypatch.delenv("BOOT_REQUIRED_TEST_VALUE", raising=False)
    with pytest.raises(ImproperlyConfigured) as exc_info:
        require_env("BOOT_REQUIRED_TEST_VALUE")
    assert "BOOT_REQUIRED_TEST_VALUE" in str(exc_info.value)
    assert "configured-value" not in str(exc_info.value)


def test_require_env_rejects_empty_value(monkeypatch):
    monkeypatch.setenv("BOOT_REQUIRED_TEST_VALUE", "")
    with pytest.raises(ImproperlyConfigured) as exc_info:
        require_env("BOOT_REQUIRED_TEST_VALUE")
    assert "BOOT_REQUIRED_TEST_VALUE" in str(exc_info.value)


def test_require_env_rejects_whitespace_only_value(monkeypatch):
    monkeypatch.setenv("BOOT_REQUIRED_TEST_VALUE", "   \t\n")
    with pytest.raises(ImproperlyConfigured) as exc_info:
        require_env("BOOT_REQUIRED_TEST_VALUE")
    assert "BOOT_REQUIRED_TEST_VALUE" in str(exc_info.value)


@pytest.mark.django_db
def test_django_settings_load():
    from django.conf import settings

    assert settings.configured
    assert settings.TIME_ZONE == "Europe/Warsaw"
    assert settings.USE_TZ is True
    assert settings.DATABASES["default"]["ENGINE"] == (
        "django.db.backends.postgresql"
    )


@pytest.mark.django_db
def test_custom_user_model_is_configured():
    from django.conf import settings

    User = get_user_model()

    assert settings.AUTH_USER_MODEL == "accounts.User"
    assert User._meta.label == "accounts.User"

    user = User.objects.create_user(
        username="office-user",
        password="safe-test-password-123",
    )
    assert user.pk is not None
    assert user.check_password("safe-test-password-123")


@pytest.mark.django_db
def test_healthcheck_ok():
    client = Client()
    response = client.get(reverse("healthcheck"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_healthcheck_reports_database_failure():
    client = Client()

    with patch(
        "config.health.connection.ensure_connection",
        side_effect=OperationalError("database unavailable"),
    ):
        response = client.get(reverse("healthcheck"))

    assert response.status_code == 503
    assert response.json() == {"status": "error"}


@pytest.mark.django_db
def test_healthcheck_uses_live_database_connection():
    client = Client()
    response = client.get(reverse("healthcheck"))

    assert response.status_code == 200
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        assert cursor.fetchone() == (1,)


@pytest.mark.django_db
def test_admin_site_is_configured():
    User = get_user_model()

    assert admin.site.is_registered(User)

    client = Client()
    response = client.get(reverse("admin:index"))
    assert response.status_code == 302
    assert "/admin/login/" in response["Location"]
