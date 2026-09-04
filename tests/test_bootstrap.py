"""Bootstrap tests for the Django foundation."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.utils import OperationalError
from django.test import Client
from django.urls import reverse


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
