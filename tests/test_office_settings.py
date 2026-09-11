"""Focused tests for office insurance settings UI (UX-001)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from audit.models import AuditEvent
from customers.models import Customer
from insurers.forms import DUPLICATE_NAME_MESSAGE
from insurers.models import InsuranceType, Insurer
from policies.models import Policy, PolicyParty

User = get_user_model()
PASSWORD = "safe-test-password-123"


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def csrf_client():
    return Client(enforce_csrf_checks=True)


def _grant(user, *codenames):
    for codename in codenames:
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return user


@pytest.fixture
def settings_manager(db):
    return _grant(
        User.objects.create_user(username="settings-mgr", password=PASSWORD),
        "view_insurer",
        "add_insurer",
        "change_insurer",
        "view_insurancetype",
        "add_insurancetype",
        "change_insurancetype",
    )


@pytest.fixture
def insurer_viewer(db):
    return _grant(
        User.objects.create_user(username="insurer-viewer", password=PASSWORD),
        "view_insurer",
    )


@pytest.fixture
def type_viewer(db):
    return _grant(
        User.objects.create_user(username="type-viewer", password=PASSWORD),
        "view_insurancetype",
    )


@pytest.fixture
def plain_user(db):
    return User.objects.create_user(username="settings-plain", password=PASSWORD)


def _insurer_audits():
    return AuditEvent.objects.filter(target_type="insurers.insurer")


def _type_audits():
    return AuditEvent.objects.filter(target_type="insurers.insurancetype")


@pytest.mark.django_db
def test_anonymous_redirected_to_login(client):
    for name, args in (
        ("insurers:settings", []),
        ("insurers:insurer_list", []),
        ("insurers:insurance_type_list", []),
        ("insurers:insurer_create", []),
        ("insurers:insurance_type_create", []),
    ):
        response = client.get(reverse(name, args=args))
        assert response.status_code == 302
        assert response["Location"].startswith(reverse("login"))


@pytest.mark.django_db
def test_authenticated_without_permission_gets_403(client, plain_user):
    client.force_login(plain_user)
    assert client.get(reverse("insurers:settings")).status_code == 403
    assert client.get(reverse("insurers:insurer_list")).status_code == 403
    assert client.get(reverse("insurers:insurance_type_list")).status_code == 403


@pytest.mark.django_db
def test_permissions_are_independent(client, insurer_viewer, type_viewer):
    client.force_login(insurer_viewer)
    assert client.get(reverse("insurers:settings")).status_code == 200
    assert client.get(reverse("insurers:insurer_list")).status_code == 200
    assert client.get(reverse("insurers:insurance_type_list")).status_code == 403

    client.force_login(type_viewer)
    assert client.get(reverse("insurers:settings")).status_code == 200
    assert client.get(reverse("insurers:insurance_type_list")).status_code == 200
    assert client.get(reverse("insurers:insurer_list")).status_code == 403


@pytest.mark.django_db
def test_settings_hub_shows_sections(client, settings_manager):
    Insurer.objects.create(name="Active Co", is_active=True)
    Insurer.objects.create(name="Off Co", is_active=False)
    InsuranceType.objects.create(name="Active Type", is_active=True)

    client.force_login(settings_manager)
    response = client.get(reverse("insurers:settings"))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Towarzystwa ubezpieczeniowe" in content
    assert "Rodzaje ubezpieczeń" in content
    assert "Aktywne pozycje" in content
    assert "1" in content
    assert reverse("insurers:insurer_list") in content
    assert reverse("insurers:insurance_type_list") in content
    assert reverse("insurers:insurer_create") in content
    assert reverse("insurers:insurance_type_create") in content


@pytest.mark.django_db
def test_insurer_list_defaults_to_active_and_filters(client, settings_manager):
    Insurer.objects.create(name="Alpha Active", is_active=True)
    Insurer.objects.create(name="Beta Off", is_active=False)

    client.force_login(settings_manager)
    default = client.get(reverse("insurers:insurer_list"))
    body = default.content.decode()
    assert "Alpha Active" in body
    assert "Beta Off" not in body

    inactive = client.get(reverse("insurers:insurer_list"), {"status": "inactive"})
    inactive_body = inactive.content.decode()
    assert "Beta Off" in inactive_body
    assert "Alpha Active" not in inactive_body

    all_items = client.get(reverse("insurers:insurer_list"), {"status": "all"})
    all_body = all_items.content.decode()
    assert "Alpha Active" in all_body
    assert "Beta Off" in all_body


@pytest.mark.django_db
def test_insurer_search_by_name(client, settings_manager):
    Insurer.objects.create(name="Nordic Shield")
    Insurer.objects.create(name="Baltic Care")
    client.force_login(settings_manager)
    response = client.get(reverse("insurers:insurer_list"), {"q": "Nordic"})
    body = response.content.decode()
    assert "Nordic Shield" in body
    assert "Baltic Care" not in body


@pytest.mark.django_db
def test_create_and_edit_insurer(client, settings_manager):
    client.force_login(settings_manager)
    create = client.post(
        reverse("insurers:insurer_create"),
        {
            "name": "  New Mutual  ",
            "contact_phone": "123",
            "contact_email": "desk@example.test",
            "website": "https://example.test",
        },
    )
    assert create.status_code == 302
    insurer = Insurer.objects.get(name="New Mutual")
    assert insurer.contact_phone == "123"
    assert _insurer_audits().filter(action="insurer.created").count() == 1

    edit = client.post(
        reverse("insurers:insurer_edit", args=[insurer.pk]),
        {
            "name": "New Mutual",
            "contact_phone": "999",
            "contact_email": "desk@example.test",
            "website": "https://example.test",
        },
    )
    assert edit.status_code == 302
    insurer.refresh_from_db()
    assert insurer.contact_phone == "999"
    assert _insurer_audits().filter(action="insurer.updated").count() == 1


@pytest.mark.django_db
def test_deactivate_and_restore_insurer_idempotent(client, settings_manager):
    insurer = Insurer.objects.create(name="Toggle Co")
    client.force_login(settings_manager)

    assert client.get(
        reverse("insurers:insurer_deactivate", args=[insurer.pk])
    ).status_code == 405
    assert client.get(
        reverse("insurers:insurer_restore", args=[insurer.pk])
    ).status_code == 405

    first = client.post(reverse("insurers:insurer_deactivate", args=[insurer.pk]))
    assert first.status_code == 302
    insurer.refresh_from_db()
    assert insurer.is_active is False
    assert _insurer_audits().filter(action="insurer.deactivated").count() == 1

    again = client.post(reverse("insurers:insurer_deactivate", args=[insurer.pk]))
    assert again.status_code == 302
    assert _insurer_audits().filter(action="insurer.deactivated").count() == 1

    restore = client.post(reverse("insurers:insurer_restore", args=[insurer.pk]))
    assert restore.status_code == 302
    insurer.refresh_from_db()
    assert insurer.is_active is True
    assert _insurer_audits().filter(action="insurer.restored").count() == 1

    restore_again = client.post(
        reverse("insurers:insurer_restore", args=[insurer.pk])
    )
    assert restore_again.status_code == 302
    assert _insurer_audits().filter(action="insurer.restored").count() == 1


@pytest.mark.django_db
def test_create_edit_deactivate_restore_insurance_type(client, settings_manager):
    client.force_login(settings_manager)
    create = client.post(
        reverse("insurers:insurance_type_create"),
        {"name": "OC", "description": "Odpowiedzialność cywilna"},
    )
    assert create.status_code == 302
    item = InsuranceType.objects.get(name="OC")
    assert _type_audits().filter(action="insurance_type.created").count() == 1

    edit = client.post(
        reverse("insurers:insurance_type_edit", args=[item.pk]),
        {"name": "OC komunikacyjne", "description": "Opis skrócony"},
    )
    assert edit.status_code == 302
    item.refresh_from_db()
    assert item.name == "OC komunikacyjne"
    assert _type_audits().filter(action="insurance_type.updated").count() == 1

    client.post(reverse("insurers:insurance_type_deactivate", args=[item.pk]))
    item.refresh_from_db()
    assert item.is_active is False
    client.post(reverse("insurers:insurance_type_deactivate", args=[item.pk]))
    assert _type_audits().filter(action="insurance_type.deactivated").count() == 1

    client.post(reverse("insurers:insurance_type_restore", args=[item.pk]))
    item.refresh_from_db()
    assert item.is_active is True
    assert client.get(
        reverse("insurers:insurance_type_deactivate", args=[item.pk])
    ).status_code == 405
    client.post(reverse("insurers:insurance_type_restore", args=[item.pk]))
    assert _type_audits().filter(action="insurance_type.restored").count() == 1


@pytest.mark.django_db
def test_polish_blank_and_duplicate_name_errors(client, settings_manager):
    Insurer.objects.create(name="Existing Co")
    client.force_login(settings_manager)

    blank = client.post(
        reverse("insurers:insurer_create"),
        {"name": "   ", "contact_phone": "", "contact_email": "", "website": ""},
    )
    assert blank.status_code == 200
    blank_body = blank.content.decode()
    assert ("Nazwa nie może być pusta." in blank_body) or (
        "Podaj nazwę." in blank_body
    )

    duplicate = client.post(
        reverse("insurers:insurer_create"),
        {
            "name": "  existing co  ",
            "contact_phone": "",
            "contact_email": "",
            "website": "",
        },
    )
    assert duplicate.status_code == 200
    assert DUPLICATE_NAME_MESSAGE in duplicate.content.decode()
    assert Insurer.objects.filter(name__iexact="existing co").count() == 1


@pytest.mark.django_db
def test_no_hard_delete_route_for_settings(client, settings_manager):
    insurer = Insurer.objects.create(name="Keep Me")
    insurance_type = InsuranceType.objects.create(name="Keep Type")
    client.force_login(settings_manager)
    assert (
        client.post(f"/settings/insurers/{insurer.pk}/delete/").status_code == 404
    )
    assert (
        client.post(
            f"/settings/insurance-types/{insurance_type.pk}/delete/"
        ).status_code
        == 404
    )
    assert Insurer.objects.filter(pk=insurer.pk).exists()
    assert InsuranceType.objects.filter(pk=insurance_type.pk).exists()


@pytest.mark.django_db
def test_deactivate_requires_csrf(csrf_client, settings_manager):
    insurer = Insurer.objects.create(name="CSRF Co")
    csrf_client.force_login(settings_manager)
    response = csrf_client.post(
        reverse("insurers:insurer_deactivate", args=[insurer.pk])
    )
    assert response.status_code == 403
    insurer.refresh_from_db()
    assert insurer.is_active is True


@pytest.mark.django_db
def test_audit_failure_rolls_back_insurer_create(client, settings_manager):
    client.force_login(settings_manager)
    with patch(
        "insurers.services.record_audit_event",
        side_effect=RuntimeError("audit unavailable"),
    ):
        with pytest.raises(RuntimeError):
            client.post(
                reverse("insurers:insurer_create"),
                {
                    "name": "Audit Fail Co",
                    "contact_phone": "",
                    "contact_email": "",
                    "website": "",
                },
            )
    assert not Insurer.objects.filter(name="Audit Fail Co").exists()
    assert _insurer_audits().count() == 0


@pytest.mark.django_db
def test_audit_summaries_omit_business_data(client, settings_manager):
    client.force_login(settings_manager)
    client.post(
        reverse("insurers:insurer_create"),
        {
            "name": "Secret Mutual",
            "contact_phone": "555-0100",
            "contact_email": "secret@example.test",
            "website": "https://secret.example.test",
        },
    )
    client.post(
        reverse("insurers:insurance_type_create"),
        {
            "name": "Secret Cover",
            "description": "Very private description text",
        },
    )
    summaries = " ".join(AuditEvent.objects.values_list("summary", flat=True))
    assert "Secret Mutual" not in summaries
    assert "555-0100" not in summaries
    assert "secret@example.test" not in summaries
    assert "secret.example.test" not in summaries
    assert "Secret Cover" not in summaries
    assert "Very private description text" not in summaries


@pytest.mark.django_db
def test_nav_and_dashboard_have_no_admin_links(client, settings_manager, plain_user):
    client.force_login(settings_manager)
    dashboard = client.get(reverse("dashboard")).content.decode()
    settings_page = client.get(reverse("insurers:settings")).content.decode()
    assert "Ustawienia" in dashboard
    assert "/admin/" not in dashboard
    assert "Django Admin" not in dashboard
    assert "/admin/" not in settings_page
    assert "Dom Finanse — Ubezpieczenia" in dashboard

    client.force_login(plain_user)
    plain = client.get(reverse("dashboard")).content.decode()
    assert "Ustawienia" not in plain
    assert "/admin/" not in plain


@pytest.mark.django_db
def test_inactive_choices_hidden_on_new_policy_kept_on_edit(
    client, settings_manager
):
    editor = _grant(
        User.objects.create_user(username="policy-editor", password=PASSWORD),
        "view_policy",
        "add_policy",
        "change_policy",
        "view_customer",
    )
    Insurer.objects.create(name="Active Insurer")
    inactive_insurer = Insurer.objects.create(name="Inactive Insurer", is_active=False)
    InsuranceType.objects.create(name="Active Type")
    inactive_type = InsuranceType.objects.create(
        name="Inactive Type",
        is_active=False,
    )
    customer = Customer.objects.create(
        customer_type=Customer.CustomerType.PERSON,
        display_name="Policy Holder",
    )
    today = timezone.localdate()
    policy = Policy.objects.create(
        policy_number="UX-001-P1",
        insurer=inactive_insurer,
        insurance_type=inactive_type,
        coverage_start=today,
        coverage_end=today + timedelta(days=30),
        status=Policy.Status.ACTIVE,
        premium=Decimal("10.00"),
        currency="PLN",
    )
    PolicyParty.objects.create(
        policy=policy,
        customer=customer,
        role=PolicyParty.Role.POLICYHOLDER,
    )

    client.force_login(editor)
    create_page = client.get(reverse("policies:create")).content.decode()
    assert "Active Insurer" in create_page
    assert "Inactive Insurer" not in create_page
    assert "Active Type" in create_page
    assert "Inactive Type" not in create_page

    edit_page = client.get(reverse("policies:edit", args=[policy.pk])).content.decode()
    assert "Inactive Insurer" in edit_page
    assert "Inactive Type" in edit_page
    assert "Active Insurer" in edit_page
    assert "Active Type" in edit_page


@pytest.mark.django_db
def test_insurer_list_query_count_is_bounded(client, settings_manager):
    for index in range(15):
        Insurer.objects.create(name=f"Query Co {index:02d}")
    client.force_login(settings_manager)
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(reverse("insurers:insurer_list"))
    assert response.status_code == 200
    assert len(ctx) < 25
