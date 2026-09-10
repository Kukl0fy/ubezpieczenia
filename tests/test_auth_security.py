"""CSRF and login-attempt protection tests."""

from __future__ import annotations

import re
from datetime import timedelta

import pytest
from axes.models import AccessAttempt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from config.settings import env_positive_int

User = get_user_model()

LOCKOUT_SNIPPET = "Too many failed login attempts"


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="office-staff",
        password="safe-test-password-123",
    )


@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        username="other-staff",
        password="safe-other-password-123",
    )


def _csrf_client() -> Client:
    return Client(enforce_csrf_checks=True)


def _extract_csrf_token(response) -> str:
    match = re.search(
        r'name="csrfmiddlewaretoken"\s+value="([^"]+)"',
        response.content.decode(),
    )
    assert match, "CSRF token not found in response"
    return match.group(1)


def _failed_login(
    client: Client,
    *,
    username: str = "office-staff",
    password: str = "wrong-password",
    remote_addr: str = "203.0.113.10",
    path: str | None = None,
):
    return client.post(
        path or reverse("login"),
        {"username": username, "password": password},
        REMOTE_ADDR=remote_addr,
    )


def _lock_user(client: Client, *, username: str, remote_addr: str) -> None:
    """Consume the failure limit until Axes locks the username+IP pair."""
    for attempt in range(1, settings.AXES_FAILURE_LIMIT + 1):
        response = _failed_login(
            client,
            username=username,
            remote_addr=remote_addr,
        )
        if attempt < settings.AXES_FAILURE_LIMIT:
            assert response.status_code == 200
        else:
            # The attempt that reaches the limit is already locked out.
            assert response.status_code == settings.AXES_HTTP_RESPONSE_CODE
            assert LOCKOUT_SNIPPET in response.content.decode()


@pytest.mark.django_db
def test_login_post_without_csrf_token_returns_403(user):
    client = _csrf_client()
    response = client.post(
        reverse("login"),
        {"username": "office-staff", "password": "safe-test-password-123"},
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_login_post_with_valid_csrf_token_succeeds(user):
    client = _csrf_client()
    login_page = client.get(reverse("login"))
    token = _extract_csrf_token(login_page)

    response = client.post(
        reverse("login"),
        {
            "username": "office-staff",
            "password": "safe-test-password-123",
            "csrfmiddlewaretoken": token,
        },
    )
    assert response.status_code == 302
    assert response["Location"] == reverse("dashboard")


@pytest.mark.django_db
def test_logout_post_without_csrf_token_returns_403(user):
    client = _csrf_client()
    client.force_login(user)
    # force_login bypasses CSRF cookie setup for subsequent posts
    client.get(reverse("dashboard"))
    response = client.post(reverse("logout"))
    assert response.status_code == 403


@pytest.mark.django_db
def test_logout_post_with_valid_csrf_token_succeeds(user):
    client = _csrf_client()
    client.force_login(user)
    dashboard = client.get(reverse("dashboard"))
    token = _extract_csrf_token(dashboard)

    response = client.post(
        reverse("logout"),
        {"csrfmiddlewaretoken": token},
    )
    assert response.status_code == 302
    assert response["Location"] == reverse("login")


@pytest.mark.django_db
def test_single_failed_login_shows_regular_error(client, user):
    response = _failed_login(client)
    assert response.status_code == 200
    errors = " ".join(response.context["form"].non_field_errors())
    assert errors
    assert LOCKOUT_SNIPPET not in errors
    assert "office-staff" not in errors


@pytest.mark.django_db
def test_login_is_blocked_after_failure_limit(client, user):
    _lock_user(client, username="office-staff", remote_addr="203.0.113.10")

    response = _failed_login(client, remote_addr="203.0.113.10")
    assert response.status_code == settings.AXES_HTTP_RESPONSE_CODE
    content = response.content.decode()
    assert LOCKOUT_SNIPPET in content
    assert "does not exist" not in content.lower()
    assert "office-staff" not in content


@pytest.mark.django_db
def test_lockout_blocks_correct_password_as_well(client, user):
    _lock_user(client, username="office-staff", remote_addr="203.0.113.10")

    response = client.post(
        reverse("login"),
        {"username": "office-staff", "password": "safe-test-password-123"},
        REMOTE_ADDR="203.0.113.10",
    )
    assert response.status_code == settings.AXES_HTTP_RESPONSE_CODE
    assert LOCKOUT_SNIPPET in response.content.decode()
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_different_lockout_keys_do_not_affect_each_other(client, user, other_user):
    _lock_user(client, username="office-staff", remote_addr="203.0.113.10")

    # Same username, different IP — still allowed.
    other_ip_response = client.post(
        reverse("login"),
        {"username": "office-staff", "password": "safe-test-password-123"},
        REMOTE_ADDR="203.0.113.20",
    )
    assert other_ip_response.status_code == 302

    client.logout()

    # Same IP, different username — still allowed.
    other_user_response = client.post(
        reverse("login"),
        {"username": "other-staff", "password": "safe-other-password-123"},
        REMOTE_ADDR="203.0.113.10",
    )
    assert other_user_response.status_code == 302


@pytest.mark.django_db
def test_lockout_expires_after_cooloff_without_waiting(client, user):
    _lock_user(client, username="office-staff", remote_addr="203.0.113.10")

    past = timezone.now() - settings.AXES_COOLOFF_TIME - timedelta(minutes=1)
    AccessAttempt.objects.filter(
        username="office-staff",
        ip_address="203.0.113.10",
    ).update(attempt_time=past)

    response = client.post(
        reverse("login"),
        {"username": "office-staff", "password": "safe-test-password-123"},
        REMOTE_ADDR="203.0.113.10",
    )
    assert response.status_code == 302
    assert response["Location"] == reverse("dashboard")


@pytest.mark.django_db
def test_successful_login_resets_failed_attempts(client, user):
    for _ in range(3):
        assert _failed_login(client, remote_addr="203.0.113.30").status_code == 200

    success = client.post(
        reverse("login"),
        {"username": "office-staff", "password": "safe-test-password-123"},
        REMOTE_ADDR="203.0.113.30",
    )
    assert success.status_code == 302
    client.logout()

    assert not AccessAttempt.objects.filter(
        username="office-staff",
        ip_address="203.0.113.30",
    ).exists()

    for _ in range(settings.AXES_FAILURE_LIMIT - 1):
        assert _failed_login(client, remote_addr="203.0.113.30").status_code == 200

    still_allowed = client.post(
        reverse("login"),
        {"username": "office-staff", "password": "safe-test-password-123"},
        REMOTE_ADDR="203.0.113.30",
    )
    assert still_allowed.status_code == 302


@pytest.mark.django_db
def test_django_admin_login_is_also_protected(client, user):
    admin_login = reverse("admin:login")
    for attempt in range(1, settings.AXES_FAILURE_LIMIT + 1):
        response = client.post(
            admin_login,
            {"username": "office-staff", "password": "wrong-password"},
            REMOTE_ADDR="198.51.100.10",
        )
        if attempt < settings.AXES_FAILURE_LIMIT:
            assert response.status_code == 200
        else:
            assert response.status_code == settings.AXES_HTTP_RESPONSE_CODE

    locked = client.post(
        admin_login,
        {"username": "office-staff", "password": "safe-test-password-123"},
        REMOTE_ADDR="198.51.100.10",
    )
    assert locked.status_code == settings.AXES_HTTP_RESPONSE_CODE
    assert LOCKOUT_SNIPPET in locked.content.decode()


@pytest.mark.django_db
def test_failed_login_response_does_not_reveal_user_existence(client, user):
    existing = _failed_login(
        client,
        username="office-staff",
        remote_addr="203.0.113.40",
    )
    missing = _failed_login(
        client,
        username="missing-user",
        remote_addr="203.0.113.41",
    )

    existing_errors = " ".join(existing.context["form"].non_field_errors())
    missing_errors = " ".join(missing.context["form"].non_field_errors())
    assert existing_errors == missing_errors
    assert "office-staff" not in existing_errors
    assert "missing-user" not in missing_errors


def test_env_positive_int_default_and_validation(monkeypatch):
    monkeypatch.delenv("DJANGO_SESSION_COOKIE_AGE", raising=False)
    assert env_positive_int("DJANGO_SESSION_COOKIE_AGE", default=28800) == 28800

    monkeypatch.setenv("DJANGO_SESSION_COOKIE_AGE", "3600")
    assert env_positive_int("DJANGO_SESSION_COOKIE_AGE", default=28800) == 3600

    monkeypatch.setenv("DJANGO_SESSION_COOKIE_AGE", "")
    with pytest.raises(ImproperlyConfigured):
        env_positive_int("DJANGO_SESSION_COOKIE_AGE", default=28800)

    monkeypatch.setenv("DJANGO_SESSION_COOKIE_AGE", "-1")
    with pytest.raises(ImproperlyConfigured):
        env_positive_int("DJANGO_SESSION_COOKIE_AGE", default=28800)

    monkeypatch.setenv("DJANGO_SESSION_COOKIE_AGE", "abc")
    with pytest.raises(ImproperlyConfigured):
        env_positive_int("DJANGO_SESSION_COOKIE_AGE", default=28800)


def test_session_settings_match_office_defaults():
    assert settings.SESSION_COOKIE_AGE == 8 * 60 * 60
    assert settings.SESSION_SAVE_EVERY_REQUEST is True
    assert settings.SESSION_EXPIRE_AT_BROWSER_CLOSE is True
