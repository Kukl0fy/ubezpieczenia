"""Authentication and private panel tests."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import NoReverseMatch, reverse

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="office-staff",
        password="safe-test-password-123",
    )


@pytest.fixture
def client():
    return Client()


@pytest.mark.django_db
def test_anonymous_user_is_redirected_from_dashboard_to_login(client):
    response = client.get(reverse("dashboard"))

    assert response.status_code == 302
    assert response["Location"].startswith(reverse("login"))


@pytest.mark.django_db
def test_authenticated_user_sees_dashboard(client, user):
    client.force_login(user)
    response = client.get(reverse("dashboard"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "Panel główny" in content
    assert user.username in content


@pytest.mark.django_db
def test_successful_login_redirects_to_dashboard(client, user):
    response = client.post(
        reverse("login"),
        {"username": "office-staff", "password": "safe-test-password-123"},
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("dashboard")


@pytest.mark.django_db
def test_invalid_login_shows_error(client, user):
    response = client.post(
        reverse("login"),
        {"username": "office-staff", "password": "wrong-password"},
    )

    assert response.status_code == 200
    assert response.context["form"].errors
    assert response.context["form"].non_field_errors()


@pytest.mark.django_db
def test_login_respects_safe_next_parameter(client, user):
    next_url = reverse("admin:index")
    response = client.post(
        f"{reverse('login')}?next={next_url}",
        {
            "username": "office-staff",
            "password": "safe-test-password-123",
            "next": next_url,
        },
    )

    assert response.status_code == 302
    assert response["Location"] == next_url


@pytest.mark.django_db
def test_login_rejects_external_next_parameter(client, user):
    response = client.post(
        reverse("login"),
        {
            "username": "office-staff",
            "password": "safe-test-password-123",
            "next": "https://evil.example/phish",
        },
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("dashboard")
    assert "evil.example" not in response["Location"]


@pytest.mark.django_db
def test_logout_via_post_redirects_to_login(client, user):
    client.force_login(user)
    response = client.post(reverse("logout"))

    assert response.status_code == 302
    assert response["Location"] == reverse("login")

    follow = client.get(reverse("dashboard"))
    assert follow.status_code == 302
    assert follow["Location"].startswith(reverse("login"))


@pytest.mark.django_db
def test_logout_via_get_is_not_allowed(client, user):
    client.force_login(user)
    response = client.get(reverse("logout"))

    assert response.status_code == 405
    assert client.get(reverse("dashboard")).status_code == 200


@pytest.mark.django_db
def test_no_public_registration_endpoint(client):
    for path in ("/register/", "/accounts/register/", "/signup/"):
        assert client.get(path).status_code == 404

    with pytest.raises(NoReverseMatch):
        reverse("register")


@pytest.mark.django_db
def test_healthcheck_remains_public(client):
    response = client.get(reverse("healthcheck"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_django_admin_still_requires_authentication(client):
    response = client.get(reverse("admin:index"))

    assert response.status_code == 302
    assert "/admin/login/" in response["Location"]
