"""Tests for the append-only audit foundation."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from audit.models import AuditEvent
from audit.services import record_audit_event

User = get_user_model()

PASSWORD = "safe-audit-password-123"


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="audit-user",
        password=PASSWORD,
    )


@pytest.fixture
def viewer(db):
    account = User.objects.create_user(
        username="audit-viewer",
        password=PASSWORD,
        is_staff=True,
    )
    account.user_permissions.add(
        Permission.objects.get(codename="view_auditevent"),
    )
    return account


@pytest.fixture
def plain_staff(db):
    return User.objects.create_user(
        username="audit-plain-staff",
        password=PASSWORD,
        is_staff=True,
    )


@pytest.mark.django_db
def test_record_audit_event_with_actor(user):
    event = record_audit_event(
        actor=user,
        action="auth.login_succeeded",
        target_type="accounts.user",
        target_id=str(user.pk),
        summary="User signed in successfully.",
    )
    assert event.pk is not None
    assert event.actor_id == user.pk
    assert event.action == "auth.login_succeeded"


@pytest.mark.django_db
def test_record_audit_event_without_actor():
    event = record_audit_event(
        action="auth.login_failed",
        target_type="authentication",
        summary="Authentication attempt failed.",
    )
    assert event.actor is None
    assert event.target_id == ""


@pytest.mark.django_db
def test_action_format_validation():
    with pytest.raises(ValidationError):
        record_audit_event(action="", target_type="accounts.user")
    with pytest.raises(ValidationError):
        record_audit_event(action="Auth.Login", target_type="accounts.user")
    with pytest.raises(ValidationError):
        record_audit_event(action="auth login", target_type="accounts.user")
    with pytest.raises(ValidationError):
        record_audit_event(action="1auth.start", target_type="accounts.user")
    ok = record_audit_event(
        action="policy.renewed",
        target_type="policies.policy",
        target_id="12",
    )
    assert ok.action == "policy.renewed"


@pytest.mark.django_db
def test_field_max_lengths_enforced(user):
    with pytest.raises(ValidationError):
        record_audit_event(
            actor=user,
            action="a" * 101,
            target_type="accounts.user",
        )
    with pytest.raises(ValidationError):
        record_audit_event(
            action="auth.login_succeeded",
            target_type="t" * 101,
        )
    with pytest.raises(ValidationError):
        record_audit_event(
            action="auth.login_succeeded",
            target_type="accounts.user",
            target_id="i" * 101,
        )
    with pytest.raises(ValidationError):
        record_audit_event(
            action="auth.login_succeeded",
            target_type="accounts.user",
            summary="s" * 501,
        )


@pytest.mark.django_db
def test_actor_set_null_when_user_deleted(user):
    event = record_audit_event(
        actor=user,
        action="auth.logout",
        target_type="accounts.user",
        target_id=str(user.pk),
    )
    user_id = user.pk
    user.delete()
    event.refresh_from_db()
    assert event.actor_id is None
    assert event.target_id == str(user_id)


@pytest.mark.django_db
def test_default_ordering_newest_first(user):
    older = record_audit_event(
        actor=user,
        action="auth.login_succeeded",
        target_type="accounts.user",
        target_id=str(user.pk),
        summary="first",
    )
    newer = record_audit_event(
        actor=user,
        action="auth.logout",
        target_type="accounts.user",
        target_id=str(user.pk),
        summary="second",
    )
    ordered = list(AuditEvent.objects.values_list("id", flat=True))
    assert ordered[0] == newer.id
    assert ordered[1] == older.id


@pytest.mark.django_db
def test_model_defines_expected_indexes():
    index_names = {index.name for index in AuditEvent._meta.indexes}
    assert "audit_event_occurred_at_idx" in index_names
    assert "audit_event_action_idx" in index_names
    assert "audit_event_target_idx" in index_names
    assert "audit_event_actor_idx" in index_names


@pytest.mark.django_db
def test_successful_login_creates_one_audit_event(client, user):
    before = AuditEvent.objects.count()
    response = client.post(
        reverse("login"),
        {"username": "audit-user", "password": PASSWORD},
        REMOTE_ADDR="203.0.113.70",
    )
    assert response.status_code == 302
    events = AuditEvent.objects.filter(action="auth.login_succeeded")
    assert events.count() == 1
    event = events.get()
    assert event.actor_id == user.pk
    assert event.target_type == "accounts.user"
    assert event.target_id == str(user.pk)
    assert PASSWORD not in event.summary
    assert AuditEvent.objects.count() == before + 1


@pytest.mark.django_db
def test_failed_login_creates_safe_audit_event(client, user):
    before = AuditEvent.objects.count()
    response = client.post(
        reverse("login"),
        {"username": "audit-user", "password": "wrong-password-value"},
        REMOTE_ADDR="203.0.113.77",
    )
    assert response.status_code == 200
    events = AuditEvent.objects.filter(action="auth.login_failed")
    assert events.count() == 1
    event = events.get()
    assert event.actor is None
    assert event.target_type == "authentication"
    content = f"{event.summary} {event.target_id} {event.action}"
    assert "audit-user" not in content
    assert "wrong-password-value" not in content
    assert PASSWORD not in content
    assert "203.0.113.77" not in content
    assert AuditEvent.objects.count() == before + 1


@pytest.mark.django_db
def test_logout_creates_audit_event(client, user):
    client.force_login(user)
    before = AuditEvent.objects.filter(action="auth.logout").count()
    client.post(reverse("logout"))
    events = AuditEvent.objects.filter(action="auth.logout")
    assert events.count() == before + 1
    event = events.latest("id")
    assert event.actor_id == user.pk
    assert event.target_id == str(user.pk)
    assert PASSWORD not in event.summary


@pytest.mark.django_db
def test_existing_event_cannot_be_changed_or_deleted(user):
    event = record_audit_event(
        actor=user,
        action="auth.login_succeeded",
        target_type="accounts.user",
        target_id=str(user.pk),
        summary="immutable",
    )
    event.summary = "changed"
    with pytest.raises(ValidationError):
        event.save()
    with pytest.raises(ValidationError):
        event.delete()
    event.refresh_from_db()
    assert event.summary == "immutable"
    assert AuditEvent.objects.filter(pk=event.pk).exists()


@pytest.mark.django_db
def test_admin_is_read_only(client, viewer, user):
    event = record_audit_event(
        actor=user,
        action="auth.login_succeeded",
        target_type="accounts.user",
        target_id=str(user.pk),
        summary="visible event",
    )
    client.force_login(viewer)
    changelist = reverse("admin:audit_auditevent_changelist")
    assert client.get(changelist).status_code == 200

    add_url = reverse("admin:audit_auditevent_add")
    assert client.get(add_url).status_code == 403

    change_url = reverse("admin:audit_auditevent_change", args=[event.pk])
    # View-only users may open the detail page, but cannot POST changes.
    detail = client.get(change_url)
    assert detail.status_code in {200, 403}
    assert client.post(change_url, {"summary": "hack"}).status_code == 403

    delete_url = reverse("admin:audit_auditevent_delete", args=[event.pk])
    assert client.get(delete_url).status_code == 403
    assert client.post(delete_url).status_code == 403
    assert AuditEvent.objects.filter(pk=event.pk).exists()


@pytest.mark.django_db
def test_admin_requires_view_permission(client, plain_staff, user):
    record_audit_event(
        actor=user,
        action="auth.logout",
        target_type="accounts.user",
        target_id=str(user.pk),
    )
    client.force_login(plain_staff)
    response = client.get(reverse("admin:audit_auditevent_changelist"))
    assert response.status_code == 403


@pytest.mark.django_db
def test_admin_denied_for_anonymous(client):
    response = client.get(reverse("admin:audit_auditevent_changelist"))
    assert response.status_code == 302
    assert "/admin/login/" in response["Location"]


@pytest.mark.django_db
def test_admin_search_and_filter(client, viewer, user):
    record_audit_event(
        actor=user,
        action="auth.login_succeeded",
        target_type="accounts.user",
        target_id=str(user.pk),
        summary="alpha summary",
    )
    record_audit_event(
        action="auth.login_failed",
        target_type="authentication",
        summary="beta summary",
    )
    client.force_login(viewer)
    changelist = reverse("admin:audit_auditevent_changelist")
    search = client.get(changelist, {"q": "alpha"})
    assert search.status_code == 200
    assert b"alpha summary" in search.content
    assert b"beta summary" not in search.content

    filtered = client.get(changelist, {"action__exact": "auth.login_failed"})
    assert filtered.status_code == 200
    assert b"beta summary" in filtered.content
    assert b"alpha summary" not in filtered.content


@pytest.mark.django_db
def test_no_missing_migrations():
    from django.core.management import call_command

    try:
        call_command("makemigrations", check=True, dry_run=True, verbosity=0)
    except SystemExit as exc:
        pytest.fail(f"Missing migrations detected: {exc}")
