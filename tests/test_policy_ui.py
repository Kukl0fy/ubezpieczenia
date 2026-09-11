"""Focused tests for the core policy workflow UI (POL-002)."""

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
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from audit.models import AuditEvent
from customers.models import Customer
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
def viewer(db):
    return _grant(
        User.objects.create_user(username="pol-viewer", password=PASSWORD),
        "view_policy",
        "view_customer",
    )


@pytest.fixture
def editor(db):
    return _grant(
        User.objects.create_user(username="pol-editor", password=PASSWORD),
        "view_policy",
        "add_policy",
        "change_policy",
        "view_customer",
    )


@pytest.fixture
def plain_user(db):
    return User.objects.create_user(username="pol-plain", password=PASSWORD)


@pytest.fixture
def catalog(db):
    insurer = Insurer.objects.create(name="Synthetic Insurer")
    insurance_type = InsuranceType.objects.create(name="Synthetic Home")
    customer = Customer.objects.create(
        customer_type=Customer.CustomerType.PERSON,
        display_name="Ada Policyholder",
        email="ada-policy@example.test",
    )
    return {
        "insurer": insurer,
        "insurance_type": insurance_type,
        "customer": customer,
    }


def _today():
    return timezone.localdate()


def _make_policy(
    catalog,
    *,
    number="POL-001",
    status=Policy.Status.ACTIVE,
    end_offset=10,
    start_offset=-20,
    extra_party: Customer | None = None,
):
    today = _today()
    policy = Policy.objects.create(
        policy_number=number,
        insurer=catalog["insurer"],
        insurance_type=catalog["insurance_type"],
        coverage_start=today + timedelta(days=start_offset),
        coverage_end=today + timedelta(days=end_offset),
        status=status,
        premium=Decimal("100.00"),
        currency="PLN",
    )
    PolicyParty.objects.create(
        policy=policy,
        customer=catalog["customer"],
        role=PolicyParty.Role.POLICYHOLDER,
    )
    if extra_party is not None:
        PolicyParty.objects.create(
            policy=policy,
            customer=extra_party,
            role=PolicyParty.Role.INSURED,
        )
    return policy


def _policy_audits():
    return AuditEvent.objects.filter(action__startswith="policy.")


@pytest.mark.django_db
def test_login_and_permissions(client, plain_user, viewer, editor, catalog):
    policy = _make_policy(catalog)
    list_url = reverse("policies:list")
    detail_url = reverse("policies:detail", args=[policy.pk])
    create_url = reverse("policies:create")
    edit_url = reverse("policies:edit", args=[policy.pk])
    cancel_url = reverse("policies:cancel", args=[policy.pk])

    assert client.get(list_url).status_code == 302
    client.force_login(plain_user)
    assert client.get(list_url).status_code == 403
    assert client.get(detail_url).status_code == 403

    client.force_login(viewer)
    assert client.get(list_url).status_code == 200
    assert client.get(detail_url).status_code == 200
    assert client.get(create_url).status_code == 403
    assert client.get(edit_url).status_code == 403
    assert client.post(cancel_url).status_code == 403

    client.force_login(editor)
    assert client.get(create_url).status_code == 200
    assert client.get(edit_url).status_code == 200


@pytest.mark.django_db
def test_list_search_filters_and_no_duplicates(client, viewer, catalog):
    other_customer = Customer.objects.create(
        customer_type=Customer.CustomerType.PERSON,
        display_name="Other Party",
    )
    policy = _make_policy(catalog, number="HOME-77", extra_party=other_customer)
    other = _make_policy(catalog, number="AUTO-9", end_offset=40)
    other.status = Policy.Status.CANCELLED
    other.save(update_fields=["status", "updated_at"])

    client.force_login(viewer)
    list_url = reverse("policies:list")
    search = client.get(list_url, {"q": "HOME-77"})
    assert search.status_code == 200
    assert len(search.context["policies"]) == 1
    assert search.context["policies"][0].policy_number == "HOME-77"
    assert "AUTO-9" not in search.content.decode()

    by_customer = client.get(list_url, {"q": "Ada Policyholder"}).content.decode()
    assert "HOME-77" in by_customer

    filtered = client.get(
        list_url,
        {
            "status": Policy.Status.ACTIVE,
            "insurer": str(catalog["insurer"].pk),
            "insurance_type": str(catalog["insurance_type"].pk),
        },
    )
    assert filtered.status_code == 200
    assert policy.policy_number in filtered.content.decode()


@pytest.mark.django_db
def test_create_policy_with_party_and_audit(client, editor, catalog):
    client.force_login(editor)
    response = client.post(
        reverse("policies:create"),
        {
            "primary_customer": catalog["customer"].pk,
            "policy_number": "  NEW-1  ",
            "insurer": catalog["insurer"].pk,
            "insurance_type": catalog["insurance_type"].pk,
            "coverage_start": str(_today()),
            "coverage_end": str(_today() + timedelta(days=30)),
            "premium": "250.50",
            "currency": "pln",
            "notes": "  note  ",
        },
    )
    policy = Policy.objects.get(policy_number="NEW-1")
    assert response.status_code == 302
    assert policy.status == Policy.Status.ACTIVE
    assert policy.currency == "PLN"
    assert policy.notes == "note"
    assert PolicyParty.objects.filter(
        policy=policy,
        customer=catalog["customer"],
        role=PolicyParty.Role.POLICYHOLDER,
    ).count() == 1
    event = _policy_audits().get(action="policy.created")
    assert event.target_id == str(policy.pk)
    assert "NEW-1" not in event.summary
    assert "Ada" not in event.summary
    assert "250.50" not in event.summary
    assert "note" not in event.summary


@pytest.mark.django_db
def test_invalid_dates_and_premium(client, editor, catalog):
    client.force_login(editor)
    response = client.post(
        reverse("policies:create"),
        {
            "primary_customer": catalog["customer"].pk,
            "policy_number": "BAD-1",
            "insurer": catalog["insurer"].pk,
            "insurance_type": catalog["insurance_type"].pk,
            "coverage_start": str(_today() + timedelta(days=10)),
            "coverage_end": str(_today()),
            "premium": "-1",
            "currency": "PLN",
            "notes": "",
        },
    )
    assert response.status_code == 200
    assert Policy.objects.count() == 0
    assert _policy_audits().count() == 0
    assert response.context["form"].errors


@pytest.mark.django_db
def test_edit_and_noop_audit_rules(client, editor, catalog):
    policy = _make_policy(catalog, number="EDIT-1")
    client.force_login(editor)
    edit_url = reverse("policies:edit", args=[policy.pk])
    payload = {
        "primary_customer": catalog["customer"].pk,
        "policy_number": "EDIT-1",
        "insurer": catalog["insurer"].pk,
        "insurance_type": catalog["insurance_type"].pk,
        "coverage_start": str(policy.coverage_start),
        "coverage_end": str(policy.coverage_end),
        "premium": "100.00",
        "currency": "PLN",
        "notes": "",
    }
    assert client.post(edit_url, payload).status_code == 302
    assert _policy_audits().count() == 0

    payload["notes"] = "updated note"
    assert client.post(edit_url, payload).status_code == 302
    policy.refresh_from_db()
    assert policy.notes == "updated note"
    event = _policy_audits().get(action="policy.updated")
    assert "notes" in event.summary
    assert "updated note" not in event.summary
    assert _policy_audits().count() == 1


@pytest.mark.django_db
def test_cancel_idempotent_csrf_get_and_renewed_block(
    client, csrf_client, editor, catalog
):
    policy = _make_policy(catalog, number="CAN-1")
    client.force_login(editor)
    cancel_url = reverse("policies:cancel", args=[policy.pk])
    assert client.get(cancel_url).status_code == 405
    assert client.post(cancel_url).status_code == 302
    policy.refresh_from_db()
    assert policy.status == Policy.Status.CANCELLED
    assert _policy_audits().filter(action="policy.cancelled").count() == 1
    assert client.post(cancel_url).status_code == 302
    assert _policy_audits().filter(action="policy.cancelled").count() == 1

    csrf_client.force_login(editor)
    active = _make_policy(catalog, number="CAN-2")
    assert csrf_client.post(
        reverse("policies:cancel", args=[active.pk])
    ).status_code == 403
    active.refresh_from_db()
    assert active.status == Policy.Status.ACTIVE

    renewed = _make_policy(catalog, number="CAN-3", status=Policy.Status.RENEWED)
    response = client.post(
        reverse("policies:cancel", args=[renewed.pk]),
        follow=True,
    )
    assert response.status_code == 200
    renewed.refresh_from_db()
    assert renewed.status == Policy.Status.RENEWED
    assert not _policy_audits().filter(
        action="policy.cancelled", target_id=str(renewed.pk)
    ).exists()
    assert "Polisy odnowionej nie można anulować" in response.content.decode()


@pytest.mark.django_db
def test_audit_failure_rolls_back_create_and_cancel(client, editor, catalog):
    client.force_login(editor)
    with patch(
        "policies.services.record_audit_event",
        side_effect=RuntimeError("audit unavailable"),
    ):
        with pytest.raises(RuntimeError):
            client.post(
                reverse("policies:create"),
                {
                    "primary_customer": catalog["customer"].pk,
                    "policy_number": "RB-1",
                    "insurer": catalog["insurer"].pk,
                    "insurance_type": catalog["insurance_type"].pk,
                    "coverage_start": str(_today()),
                    "coverage_end": str(_today() + timedelta(days=5)),
                    "premium": "",
                    "currency": "PLN",
                    "notes": "",
                },
            )
    assert Policy.objects.filter(policy_number="RB-1").count() == 0

    policy = _make_policy(catalog, number="RB-2")
    with patch(
        "policies.services.record_audit_event",
        side_effect=RuntimeError("audit unavailable"),
    ):
        with pytest.raises(RuntimeError):
            client.post(reverse("policies:cancel", args=[policy.pk]))
    policy.refresh_from_db()
    assert policy.status == Policy.Status.ACTIVE


@pytest.mark.django_db
def test_dashboard_expiry_buckets_and_exclusions(client, viewer, editor, catalog):
    today = _today()
    overdue = _make_policy(catalog, number="D-OVER", end_offset=-1)
    today_end = _make_policy(catalog, number="D-TODAY", end_offset=0)
    in_7 = _make_policy(catalog, number="D-7", end_offset=7)
    in_8 = _make_policy(catalog, number="D-8", end_offset=8)
    in_30 = _make_policy(catalog, number="D-30", end_offset=30)
    later = _make_policy(catalog, number="D-31", end_offset=31)
    cancelled = _make_policy(
        catalog, number="D-CAN", end_offset=3, status=Policy.Status.CANCELLED
    )
    renewed = _make_policy(
        catalog, number="D-REN", end_offset=3, status=Policy.Status.RENEWED
    )
    draft = _make_policy(
        catalog, number="D-DR", end_offset=3, status=Policy.Status.DRAFT
    )
    expired = _make_policy(
        catalog, number="D-EX", end_offset=3, status=Policy.Status.EXPIRED
    )

    client.force_login(viewer)
    content = client.get(reverse("dashboard")).content.decode()
    assert reverse("policies:list") in content
    assert "Dodaj polisę" not in content
    assert overdue.policy_number in content
    assert today_end.policy_number in content
    assert in_7.policy_number in content
    assert in_8.policy_number in content
    assert in_30.policy_number in content
    assert later.policy_number not in content
    assert cancelled.policy_number not in content
    assert renewed.policy_number not in content
    assert draft.policy_number not in content
    assert expired.policy_number not in content
    assert "Po terminie" in content
    assert str(today)  # smoke that page rendered with local date context

    client.force_login(editor)
    editor_dash = client.get(reverse("dashboard")).content.decode()
    assert "Dodaj polisę" in editor_dash
    assert reverse("policies:create") in editor_dash


@pytest.mark.django_db
def test_customer_policies_section_and_no_delete_routes(client, viewer, catalog):
    other = Customer.objects.create(
        customer_type=Customer.CustomerType.PERSON,
        display_name="Second Role",
    )
    policy = _make_policy(catalog, number="CUST-POL", extra_party=other)
    client.force_login(viewer)
    content = client.get(
        reverse("customers:detail", args=[catalog["customer"].pk])
    ).content.decode()
    assert "Polisy klienta" in content
    assert content.count("CUST-POL") == 1
    assert reverse("policies:detail", args=[policy.pk]) in content

    with pytest.raises(NoReverseMatch):
        reverse("policies:delete", args=[1])


@pytest.mark.django_db
def test_list_avoids_n_plus_one(client, viewer, catalog):
    for index in range(8):
        _make_policy(catalog, number=f"N1-{index}", end_offset=10 + index)
    client.force_login(viewer)
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(reverse("policies:list"))
    assert response.status_code == 200
    # Auth/session + one main policy query with joins/prefetch; keep bounded.
    assert len(ctx) < 20


@pytest.mark.django_db
def test_polish_labels_and_renewed_cancel_message(client, viewer, editor, catalog):
    from policies.models import InsuredObject, PolicyObject
    from policies.presenters import RENEWED_CANCEL_BLOCKED_MESSAGE

    policy = _make_policy(catalog, number="PL-LABELS", end_offset=3)
    insured = InsuredObject.objects.create(
        object_type=InsuredObject.ObjectType.PROPERTY,
        label="Synthetic Flat",
    )
    PolicyObject.objects.create(policy=policy, insured_object=insured)
    PolicyParty.objects.create(
        policy=policy,
        customer=Customer.objects.create(
            customer_type=Customer.CustomerType.PERSON,
            display_name="Payer Person",
        ),
        role=PolicyParty.Role.PAYER,
    )

    client.force_login(viewer)
    content = client.get(
        reverse("policies:detail", args=[policy.pk])
    ).content.decode()
    assert "Ubezpieczający" in content
    assert "Płatnik" in content
    assert "Nieruchomość" in content
    assert ">Policyholder<" not in content
    assert ">Property<" not in content

    list_content = client.get(reverse("policies:list")).content.decode()
    assert "Aktywna · Aktywna" not in list_content
    soon = _make_policy(catalog, number="PL-SOON", end_offset=2)
    soon_list = client.get(reverse("policies:list")).content.decode()
    assert soon.policy_number in soon_list
    assert "Kończy się wkrótce" in soon_list

    client.force_login(editor)
    renewed = _make_policy(catalog, number="PL-REN", status=Policy.Status.RENEWED)
    cancel_page = client.post(
        reverse("policies:cancel", args=[renewed.pk]),
        follow=True,
    )
    assert RENEWED_CANCEL_BLOCKED_MESSAGE in cancel_page.content.decode()


@pytest.mark.django_db
def test_complex_policyholders_edit_keeps_parties(client, editor, catalog):
    from policies.presenters import COMPLEX_POLICYHOLDERS_MESSAGE
    from policies.services import update_policy

    second = Customer.objects.create(
        customer_type=Customer.CustomerType.COMPANY,
        display_name="Second Holder Co",
    )
    third = Customer.objects.create(
        customer_type=Customer.CustomerType.PERSON,
        display_name="Third Attempt",
    )
    policy = _make_policy(catalog, number="MULTI-H")
    PolicyParty.objects.create(
        policy=policy,
        customer=second,
        role=PolicyParty.Role.POLICYHOLDER,
    )
    holder_ids_before = set(
        policy.parties.filter(role=PolicyParty.Role.POLICYHOLDER).values_list(
            "id", "customer_id"
        )
    )

    client.force_login(editor)
    edit_url = reverse("policies:edit", args=[policy.pk])
    form_page = client.get(edit_url)
    assert form_page.status_code == 200
    assert COMPLEX_POLICYHOLDERS_MESSAGE in form_page.content.decode()

    response = client.post(
        edit_url,
        {
            "primary_customer": third.pk,
            "policy_number": "MULTI-H",
            "insurer": catalog["insurer"].pk,
            "insurance_type": catalog["insurance_type"].pk,
            "coverage_start": str(policy.coverage_start),
            "coverage_end": str(policy.coverage_end),
            "premium": "100.00",
            "currency": "PLN",
            "notes": "safe note",
        },
        follow=True,
    )
    assert response.status_code == 200
    assert COMPLEX_POLICYHOLDERS_MESSAGE in response.content.decode()
    policy.refresh_from_db()
    assert policy.notes == "safe note"
    holder_ids_after = set(
        policy.parties.filter(role=PolicyParty.Role.POLICYHOLDER).values_list(
            "id", "customer_id"
        )
    )
    assert holder_ids_after == holder_ids_before
    assert policy.parties.count() == 2
    event = _policy_audits().get(action="policy.updated")
    assert event.summary == "Updated fields: notes."
    assert "primary_customer" not in event.summary

    result = update_policy(
        actor=editor,
        policy=policy,
        primary_customer=third,
        policy_number=policy.policy_number,
        insurer=policy.insurer,
        insurance_type=policy.insurance_type,
        coverage_start=policy.coverage_start,
        coverage_end=policy.coverage_end,
        premium=policy.premium,
        currency=policy.currency,
        notes=policy.notes,
    )
    assert result.warning == COMPLEX_POLICYHOLDERS_MESSAGE
    assert (
        set(
            policy.parties.filter(role=PolicyParty.Role.POLICYHOLDER).values_list(
                "id", "customer_id"
            )
        )
        == holder_ids_before
    )
    assert _policy_audits().filter(action="policy.updated").count() == 1
