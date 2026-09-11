"""Focused tests for transactional policy renewal (POL-003)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from audit.models import AuditEvent
from customers.models import Customer
from insurers.models import InsuranceType, Insurer
from policies.models import InsuredObject, Policy, PolicyObject, PolicyParty
from policies.presenters import (
    RENEWAL_ALREADY_EXISTS_MESSAGE,
    RENEWAL_NOT_ALLOWED_MESSAGE,
    default_renewal_dates,
)
from policies.services import renew_policy

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
def renewer(db):
    return _grant(
        User.objects.create_user(username="pol-renewer", password=PASSWORD),
        "view_policy",
        "add_policy",
        "change_policy",
        "view_customer",
    )


@pytest.fixture
def viewer_only(db):
    return _grant(
        User.objects.create_user(username="pol-view-only", password=PASSWORD),
        "view_policy",
    )


@pytest.fixture
def catalog(db):
    insurer = Insurer.objects.create(name="Renewal Insurer")
    insurance_type = InsuranceType.objects.create(name="Renewal Type")
    customer = Customer.objects.create(
        customer_type=Customer.CustomerType.PERSON,
        display_name="Renewal Holder",
    )
    return {
        "insurer": insurer,
        "insurance_type": insurance_type,
        "customer": customer,
    }


def _today():
    return timezone.localdate()


def _source_policy(
    catalog,
    *,
    number="SRC-1",
    status=Policy.Status.ACTIVE,
    multi_holders=False,
    with_objects=False,
):
    today = _today()
    start = today - timedelta(days=30)
    end = today + timedelta(days=10)
    policy = Policy.objects.create(
        policy_number=number,
        insurer=catalog["insurer"],
        insurance_type=catalog["insurance_type"],
        coverage_start=start,
        coverage_end=end,
        status=status,
        premium=Decimal("150.00"),
        currency="PLN",
        notes="source note",
    )
    PolicyParty.objects.create(
        policy=policy,
        customer=catalog["customer"],
        role=PolicyParty.Role.POLICYHOLDER,
    )
    if multi_holders:
        second = Customer.objects.create(
            customer_type=Customer.CustomerType.COMPANY,
            display_name="Second Holder",
        )
        payer = Customer.objects.create(
            customer_type=Customer.CustomerType.PERSON,
            display_name="Payer Person",
        )
        PolicyParty.objects.create(
            policy=policy,
            customer=second,
            role=PolicyParty.Role.POLICYHOLDER,
        )
        PolicyParty.objects.create(
            policy=policy,
            customer=payer,
            role=PolicyParty.Role.PAYER,
        )
        PolicyParty.objects.create(
            policy=policy,
            customer=catalog["customer"],
            role=PolicyParty.Role.INSURED,
        )
    if with_objects:
        obj_a = InsuredObject.objects.create(
            object_type=InsuredObject.ObjectType.PROPERTY,
            label="Building A",
        )
        obj_b = InsuredObject.objects.create(
            object_type=InsuredObject.ObjectType.VEHICLE,
            label="Car B",
        )
        PolicyObject.objects.create(policy=policy, insured_object=obj_a)
        PolicyObject.objects.create(policy=policy, insured_object=obj_b)
    return policy


def _renew_payload(source: Policy, *, number="NEW-1", **overrides):
    start, end = default_renewal_dates(source)
    payload = {
        "policy_number": number,
        "insurer": source.insurer_id,
        "insurance_type": source.insurance_type_id,
        "coverage_start": str(start),
        "coverage_end": str(end),
        "premium": "150.00",
        "currency": "PLN",
        "notes": "source note",
    }
    payload.update(overrides)
    return payload


def _policy_audits():
    return AuditEvent.objects.filter(action__startswith="policy.")


@pytest.mark.django_db
def test_renew_requires_login_and_all_permissions(client, viewer_only, catalog):
    source = _source_policy(catalog)
    url = reverse("policies:renew", args=[source.pk])
    assert client.get(url).status_code == 302
    client.force_login(viewer_only)
    assert client.get(url).status_code == 403
    assert client.post(url, _renew_payload(source)).status_code == 403


@pytest.mark.django_db
def test_renew_form_initial_values(client, renewer, catalog):
    source = _source_policy(catalog)
    expected_start, expected_end = default_renewal_dates(source)
    client.force_login(renewer)
    response = client.get(reverse("policies:renew", args=[source.pk]))
    assert response.status_code == 200
    form = response.context["form"]
    assert form["policy_number"].value() in ("", None)
    assert form["insurer"].value() == source.insurer_id
    assert form["insurance_type"].value() == source.insurance_type_id
    assert form["coverage_start"].value() == expected_start
    assert form["coverage_end"].value() == expected_end
    assert form["premium"].value() == source.premium
    assert form["currency"].value() == "PLN"
    assert form["notes"].value() == "source note"


@pytest.mark.django_db
@pytest.mark.parametrize("status", [Policy.Status.ACTIVE, Policy.Status.EXPIRED])
def test_renew_active_and_expired(client, renewer, catalog, status):
    source = _source_policy(
        catalog,
        number=f"SRC-{status}",
        status=status,
        multi_holders=True,
        with_objects=True,
    )
    old_party_keys = set(
        source.parties.values_list("customer_id", "role")
    )
    old_object_ids = set(
        source.policy_objects.values_list("insured_object_id", flat=True)
    )
    old_party_count = source.parties.count()
    old_object_count = source.policy_objects.count()

    client.force_login(renewer)
    response = client.post(
        reverse("policies:renew", args=[source.pk]),
        _renew_payload(source, number=f"NEW-{status}"),
    )
    assert response.status_code == 302
    source.refresh_from_db()
    new_policy = Policy.objects.get(policy_number=f"NEW-{status}")
    assert response["Location"] == reverse("policies:detail", args=[new_policy.pk])
    assert new_policy.status == Policy.Status.ACTIVE
    assert new_policy.previous_policy_id == source.pk
    assert source.status == Policy.Status.RENEWED
    assert set(new_policy.parties.values_list("customer_id", "role")) == old_party_keys
    assert set(
        new_policy.policy_objects.values_list("insured_object_id", flat=True)
    ) == old_object_ids
    assert source.parties.count() == old_party_count
    assert source.policy_objects.count() == old_object_count

    events = list(_policy_audits().order_by("id"))
    assert len(events) == 2
    assert events[0].action == "policy.renewed"
    assert events[0].target_id == str(source.pk)
    assert events[1].action == "policy.created"
    assert events[1].target_id == str(new_policy.pk)
    for event in events:
        assert f"NEW-{status}" not in event.summary
        assert "Renewal Holder" not in event.summary
        assert "150.00" not in event.summary
        assert "source note" not in event.summary


@pytest.mark.django_db
def test_renew_idempotent_no_extra_audit(client, renewer, catalog):
    source = _source_policy(catalog, number="IDEM-SRC")
    client.force_login(renewer)
    url = reverse("policies:renew", args=[source.pk])
    first = client.post(url, _renew_payload(source, number="IDEM-NEW"))
    new_policy = Policy.objects.get(policy_number="IDEM-NEW")
    assert first.status_code == 302
    assert _policy_audits().count() == 2

    second = client.post(url, _renew_payload(source, number="IDEM-OTHER"), follow=True)
    assert second.status_code == 200
    assert Policy.objects.filter(previous_policy=source).count() == 1
    assert Policy.objects.filter(policy_number="IDEM-OTHER").count() == 0
    assert _policy_audits().count() == 2
    assert RENEWAL_ALREADY_EXISTS_MESSAGE in second.content.decode()
    assert new_policy.policy_number in second.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status",
    [Policy.Status.DRAFT, Policy.Status.CANCELLED, Policy.Status.RENEWED],
)
def test_renew_blocked_for_disallowed_statuses(client, renewer, catalog, status):
    source = _source_policy(catalog, number=f"BAD-{status}", status=status)
    client.force_login(renewer)
    get_response = client.get(
        reverse("policies:renew", args=[source.pk]),
        follow=True,
    )
    assert RENEWAL_NOT_ALLOWED_MESSAGE in get_response.content.decode()
    post_response = client.post(
        reverse("policies:renew", args=[source.pk]),
        _renew_payload(source, number=f"BAD-NEW-{status}"),
        follow=True,
    )
    assert RENEWAL_NOT_ALLOWED_MESSAGE in post_response.content.decode()
    source.refresh_from_db()
    assert source.status == status
    assert Policy.objects.filter(previous_policy=source).count() == 0
    assert _policy_audits().count() == 0


@pytest.mark.django_db
def test_renew_rejects_invalid_dates_and_premium(client, renewer, catalog):
    source = _source_policy(catalog)
    client.force_login(renewer)
    response = client.post(
        reverse("policies:renew", args=[source.pk]),
        _renew_payload(
            source,
            number="BAD-FORM",
            coverage_start=str(_today() + timedelta(days=10)),
            coverage_end=str(_today()),
            premium="-5",
        ),
    )
    assert response.status_code == 200
    assert response.context["form"].errors
    assert Policy.objects.filter(previous_policy=source).count() == 0
    source.refresh_from_db()
    assert source.status == Policy.Status.ACTIVE


@pytest.mark.django_db
def test_renew_audit_failure_rolls_back(client, renewer, catalog):
    source = _source_policy(catalog, number="RB-SRC", with_objects=True)
    client.force_login(renewer)
    with patch(
        "policies.services.record_audit_event",
        side_effect=RuntimeError("audit unavailable"),
    ):
        with pytest.raises(RuntimeError):
            client.post(
                reverse("policies:renew", args=[source.pk]),
                _renew_payload(source, number="RB-NEW"),
            )
    source.refresh_from_db()
    assert source.status == Policy.Status.ACTIVE
    assert Policy.objects.filter(policy_number="RB-NEW").count() == 0
    assert Policy.objects.filter(previous_policy=source).count() == 0
    assert source.parties.count() >= 1
    assert source.policy_objects.count() == 2


@pytest.mark.django_db
def test_renew_requires_csrf(csrf_client, renewer, catalog):
    source = _source_policy(catalog)
    csrf_client.force_login(renewer)
    response = csrf_client.post(
        reverse("policies:renew", args=[source.pk]),
        _renew_payload(source),
    )
    assert response.status_code == 403
    assert Policy.objects.filter(previous_policy=source).count() == 0


@pytest.mark.django_db
def test_renew_button_visibility(client, renewer, viewer_only, catalog):
    active = _source_policy(catalog, number="BTN-ACTIVE")
    expired = _source_policy(
        catalog, number="BTN-EXPIRED", status=Policy.Status.EXPIRED
    )
    cancelled = _source_policy(
        catalog, number="BTN-CAN", status=Policy.Status.CANCELLED
    )
    client.force_login(renewer)
    active_page = client.get(
        reverse("policies:detail", args=[active.pk])
    ).content.decode()
    assert "Odnów polisę" in active_page
    assert reverse("policies:renew", args=[active.pk]) in active_page
    expired_page = client.get(
        reverse("policies:detail", args=[expired.pk])
    ).content.decode()
    assert "Odnów polisę" in expired_page
    cancelled_page = client.get(
        reverse("policies:detail", args=[cancelled.pk])
    ).content.decode()
    assert "Odnów polisę" not in cancelled_page

    client.post(
        reverse("policies:renew", args=[active.pk]),
        _renew_payload(active, number="BTN-NEW"),
    )
    renewed_page = client.get(
        reverse("policies:detail", args=[active.pk])
    ).content.decode()
    assert "Odnów polisę" not in renewed_page
    assert "BTN-NEW" in renewed_page

    client.force_login(viewer_only)
    viewer_page = client.get(
        reverse("policies:detail", args=[expired.pk])
    ).content.decode()
    assert "Odnów polisę" not in viewer_page


@pytest.mark.django_db(transaction=True)
def test_renew_service_second_call_returns_existing(renewer, catalog):
    source = _source_policy(catalog, number="SVC-SRC")
    start, end = default_renewal_dates(source)
    first = renew_policy(
        actor=renewer,
        source=source,
        policy_number="SVC-NEW",
        insurer=source.insurer,
        insurance_type=source.insurance_type,
        coverage_start=start,
        coverage_end=end,
        premium=source.premium,
        currency=source.currency,
        notes=source.notes,
    )
    assert first.created is True
    second = renew_policy(
        actor=renewer,
        source=source,
        policy_number="SVC-OTHER",
        insurer=source.insurer,
        insurance_type=source.insurance_type,
        coverage_start=start,
        coverage_end=end,
        premium=source.premium,
        currency=source.currency,
        notes=source.notes,
    )
    assert second.created is False
    assert second.policy.pk == first.policy.pk
    assert Policy.objects.filter(previous_policy=source).count() == 1
    assert _policy_audits().count() == 2
