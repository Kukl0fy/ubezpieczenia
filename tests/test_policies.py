"""Tests for the policy domain model."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError
from django.test import Client
from django.urls import reverse

from customers.models import Customer
from insurers.models import InsuranceType, Insurer
from policies.models import InsuredObject, Policy, PolicyObject, PolicyParty

User = get_user_model()


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def insurer(db):
    return Insurer.objects.create(name="Synthetic Mutual")


@pytest.fixture
def inactive_insurer(db):
    return Insurer.objects.create(name="Inactive Mutual", is_active=False)


@pytest.fixture
def insurance_type(db):
    return InsuranceType.objects.create(name="Synthetic Property")


@pytest.fixture
def inactive_type(db):
    return InsuranceType.objects.create(name="Inactive Cover", is_active=False)


@pytest.fixture
def customer(db):
    return Customer.objects.create(
        customer_type=Customer.CustomerType.PERSON,
        display_name="Ada Synthetic",
    )


@pytest.fixture
def staff_user(db):
    user = User.objects.create_user(
        username="pol-staff",
        password="safe-test-password-123",
        is_staff=True,
    )
    for codename in (
        "view_policy",
        "add_policy",
        "change_policy",
        "view_insuredobject",
        "add_insuredobject",
        "change_insuredobject",
    ):
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return user


@pytest.fixture
def plain_user(db):
    return User.objects.create_user(
        username="pol-plain",
        password="safe-test-password-123",
    )


def _policy_kwargs(insurer, insurance_type, **overrides):
    data = {
        "policy_number": "POL-001",
        "insurer": insurer,
        "insurance_type": insurance_type,
        "coverage_start": date(2026, 1, 1),
        "coverage_end": date(2026, 12, 31),
        "status": Policy.Status.ACTIVE,
        "premium": Decimal("100.00"),
        "currency": "PLN",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_create_valid_policy(insurer, insurance_type):
    policy = Policy.objects.create(**_policy_kwargs(insurer, insurance_type))
    assert policy.pk is not None
    assert policy.currency == "PLN"


@pytest.mark.django_db
def test_reject_coverage_end_before_start(insurer, insurance_type):
    with pytest.raises(ValidationError) as exc_info:
        Policy.objects.create(
            **_policy_kwargs(
                insurer,
                insurance_type,
                coverage_start=date(2026, 12, 31),
                coverage_end=date(2026, 1, 1),
            )
        )
    assert "coverage_end" in exc_info.value.message_dict


@pytest.mark.django_db
def test_postgresql_rejects_invalid_coverage_dates(insurer, insurance_type):
    with pytest.raises(IntegrityError), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO policies_policy "
                "(policy_number, insurer_id, insurance_type_id, coverage_start, "
                "coverage_end, status, premium, currency, notes, "
                "previous_policy_id, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, NOW(), NOW())",
                [
                    "RAW-DATE",
                    insurer.id,
                    insurance_type.id,
                    date(2026, 12, 31),
                    date(2026, 1, 1),
                    "ACTIVE",
                    None,
                    "PLN",
                    "",
                ],
            )


@pytest.mark.django_db
def test_optional_premium_allowed(insurer, insurance_type):
    policy = Policy.objects.create(
        **_policy_kwargs(insurer, insurance_type, premium=None)
    )
    assert policy.premium is None


@pytest.mark.django_db
def test_reject_negative_premium_in_model(insurer, insurance_type):
    with pytest.raises(ValidationError):
        Policy.objects.create(
            **_policy_kwargs(insurer, insurance_type, premium=Decimal("-1.00"))
        )


@pytest.mark.django_db
def test_postgresql_rejects_negative_premium(insurer, insurance_type):
    with pytest.raises(IntegrityError), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO policies_policy "
                "(policy_number, insurer_id, insurance_type_id, coverage_start, "
                "coverage_end, status, premium, currency, notes, "
                "previous_policy_id, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, NOW(), NOW())",
                [
                    "RAW-PREMIUM",
                    insurer.id,
                    insurance_type.id,
                    date(2026, 1, 1),
                    date(2026, 12, 31),
                    "ACTIVE",
                    Decimal("-5.00"),
                    "PLN",
                    "",
                ],
            )


@pytest.mark.django_db
def test_normalize_policy_number_and_currency(insurer, insurance_type):
    policy = Policy.objects.create(
        **_policy_kwargs(
            insurer,
            insurance_type,
            policy_number="  POL-100  ",
            currency="eur",
        )
    )
    policy.refresh_from_db()
    assert policy.policy_number == "POL-100"
    assert policy.currency == "EUR"


@pytest.mark.django_db
def test_reject_blank_policy_number(insurer, insurance_type):
    with pytest.raises(ValidationError):
        Policy.objects.create(
            **_policy_kwargs(insurer, insurance_type, policy_number="   ")
        )


@pytest.mark.django_db
def test_all_allowed_statuses(insurer, insurance_type):
    for status in Policy.Status.values:
        policy = Policy.objects.create(
            **_policy_kwargs(
                insurer,
                insurance_type,
                policy_number=f"ST-{status}",
                status=status,
            )
        )
        assert policy.status == status


@pytest.mark.django_db
def test_reject_invalid_status_in_model(insurer, insurance_type):
    with pytest.raises(ValidationError):
        Policy.objects.create(
            **_policy_kwargs(insurer, insurance_type, status="PENDING")
        )


@pytest.mark.django_db
def test_postgresql_rejects_invalid_status(insurer, insurance_type):
    with pytest.raises(IntegrityError), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO policies_policy "
                "(policy_number, insurer_id, insurance_type_id, coverage_start, "
                "coverage_end, status, premium, currency, notes, "
                "previous_policy_id, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, NOW(), NOW())",
                [
                    "RAW-STATUS",
                    insurer.id,
                    insurance_type.id,
                    date(2026, 1, 1),
                    date(2026, 12, 31),
                    "PENDING",
                    None,
                    "PLN",
                    "",
                ],
            )


@pytest.mark.django_db
def test_policy_str_includes_number_and_insurer(insurer, insurance_type):
    policy = Policy.objects.create(**_policy_kwargs(insurer, insurance_type))
    assert str(policy) == "POL-001 (Synthetic Mutual)"


@pytest.mark.django_db
def test_duplicate_policy_numbers_allowed(insurer, insurance_type):
    Policy.objects.create(**_policy_kwargs(insurer, insurance_type))
    second = Policy.objects.create(
        **_policy_kwargs(insurer, insurance_type, policy_number="POL-001")
    )
    assert Policy.objects.filter(policy_number="POL-001").count() == 2
    assert second.pk is not None


@pytest.mark.django_db
def test_policy_can_reference_inactive_dictionaries(
    inactive_insurer,
    inactive_type,
):
    policy = Policy.objects.create(
        **_policy_kwargs(inactive_insurer, inactive_type)
    )
    assert policy.insurer.is_active is False
    assert policy.insurance_type.is_active is False


@pytest.mark.django_db
def test_previous_policy_link(insurer, insurance_type):
    previous = Policy.objects.create(
        **_policy_kwargs(insurer, insurance_type, policy_number="OLD-1")
    )
    renewal = Policy.objects.create(
        **_policy_kwargs(
            insurer,
            insurance_type,
            policy_number="NEW-1",
            previous_policy=previous,
        )
    )
    assert renewal.previous_policy_id == previous.id
    assert previous.status == Policy.Status.ACTIVE


@pytest.mark.django_db
def test_reject_self_previous_policy(insurer, insurance_type):
    policy = Policy.objects.create(**_policy_kwargs(insurer, insurance_type))
    policy.previous_policy = policy
    with pytest.raises(ValidationError):
        policy.save()


@pytest.mark.django_db
def test_postgresql_rejects_self_previous_policy(insurer, insurance_type):
    policy = Policy.objects.create(**_policy_kwargs(insurer, insurance_type))
    with pytest.raises(IntegrityError), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE policies_policy SET previous_policy_id = %s WHERE id = %s",
                [policy.id, policy.id],
            )


@pytest.mark.django_db
def test_only_one_direct_renewal_of_previous_policy(insurer, insurance_type):
    previous = Policy.objects.create(
        **_policy_kwargs(insurer, insurance_type, policy_number="BASE")
    )
    Policy.objects.create(
        **_policy_kwargs(
            insurer,
            insurance_type,
            policy_number="REN-1",
            previous_policy=previous,
        )
    )
    with pytest.raises(ValidationError):
        Policy.objects.create(
            **_policy_kwargs(
                insurer,
                insurance_type,
                policy_number="REN-2",
                previous_policy=previous,
            )
        )


@pytest.mark.django_db
def test_renewal_cycle_detected(insurer, insurance_type):
    first = Policy.objects.create(
        **_policy_kwargs(insurer, insurance_type, policy_number="A")
    )
    second = Policy.objects.create(
        **_policy_kwargs(
            insurer,
            insurance_type,
            policy_number="B",
            previous_policy=first,
        )
    )
    third = Policy.objects.create(
        **_policy_kwargs(
            insurer,
            insurance_type,
            policy_number="C",
            previous_policy=second,
        )
    )
    first.previous_policy = third
    with pytest.raises(ValidationError) as exc_info:
        first.save()
    assert "previous_policy" in exc_info.value.message_dict


@pytest.mark.django_db
def test_setting_previous_policy_does_not_change_statuses(insurer, insurance_type):
    previous = Policy.objects.create(
        **_policy_kwargs(
            insurer,
            insurance_type,
            policy_number="PREV",
            status=Policy.Status.ACTIVE,
        )
    )
    renewal = Policy.objects.create(
        **_policy_kwargs(
            insurer,
            insurance_type,
            policy_number="NEXT",
            status=Policy.Status.DRAFT,
            previous_policy=previous,
        )
    )
    previous.refresh_from_db()
    renewal.refresh_from_db()
    assert previous.status == Policy.Status.ACTIVE
    assert renewal.status == Policy.Status.DRAFT


@pytest.mark.django_db
def test_policy_parties_roles_and_uniqueness(insurer, insurance_type, customer):
    other = Customer.objects.create(
        customer_type=Customer.CustomerType.COMPANY,
        display_name="Other Synthetic Co",
    )
    policy = Policy.objects.create(**_policy_kwargs(insurer, insurance_type))
    PolicyParty.objects.create(
        policy=policy,
        customer=customer,
        role=PolicyParty.Role.POLICYHOLDER,
    )
    PolicyParty.objects.create(
        policy=policy,
        customer=customer,
        role=PolicyParty.Role.INSURED,
    )
    PolicyParty.objects.create(
        policy=policy,
        customer=other,
        role=PolicyParty.Role.PAYER,
    )
    assert policy.parties.count() == 3
    with pytest.raises(ValidationError):
        PolicyParty.objects.create(
            policy=policy,
            customer=customer,
            role=PolicyParty.Role.POLICYHOLDER,
        )


@pytest.mark.django_db
def test_postgresql_rejects_duplicate_policy_party_role(
    insurer,
    insurance_type,
    customer,
):
    policy = Policy.objects.create(**_policy_kwargs(insurer, insurance_type))
    PolicyParty.objects.create(
        policy=policy,
        customer=customer,
        role=PolicyParty.Role.INSURED,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO policies_policyparty "
                "(policy_id, customer_id, role, created_at) "
                "VALUES (%s, %s, %s, NOW())",
                [policy.id, customer.id, "INSURED"],
            )


@pytest.mark.django_db
def test_archived_customer_remains_linkable(insurer, insurance_type):
    archived = Customer.objects.create(
        customer_type=Customer.CustomerType.PERSON,
        display_name="Archived Client",
        is_archived=True,
    )
    policy = Policy.objects.create(**_policy_kwargs(insurer, insurance_type))
    party = PolicyParty.objects.create(
        policy=policy,
        customer=archived,
        role=PolicyParty.Role.POLICYHOLDER,
    )
    assert party.customer.is_archived is True


@pytest.mark.django_db
def test_customer_delete_protected_by_policy_party(
    insurer,
    insurance_type,
    customer,
):
    policy = Policy.objects.create(**_policy_kwargs(insurer, insurance_type))
    PolicyParty.objects.create(
        policy=policy,
        customer=customer,
        role=PolicyParty.Role.PAYER,
    )
    with pytest.raises(ProtectedError):
        customer.delete()


@pytest.mark.django_db
def test_insured_object_types_and_label_validation():
    for object_type in InsuredObject.ObjectType.values:
        obj = InsuredObject.objects.create(
            object_type=object_type,
            label=f"  Object {object_type}  ",
        )
        obj.refresh_from_db()
        assert obj.label == f"Object {object_type}"

    with pytest.raises(ValidationError):
        InsuredObject.objects.create(object_type="UNKNOWN", label="Bad")
    with pytest.raises(ValidationError):
        InsuredObject.objects.create(
            object_type=InsuredObject.ObjectType.OTHER,
            label="   ",
        )


@pytest.mark.django_db
def test_postgresql_rejects_invalid_object_type():
    with pytest.raises(IntegrityError), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO policies_insuredobject "
                "(object_type, label, description, is_archived, "
                "created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, NOW(), NOW())",
                ["ANIMAL", "Raw Object", "", False],
            )


@pytest.mark.django_db
def test_policy_objects_linking_and_reuse(insurer, insurance_type):
    first = Policy.objects.create(
        **_policy_kwargs(insurer, insurance_type, policy_number="P1")
    )
    second = Policy.objects.create(
        **_policy_kwargs(insurer, insurance_type, policy_number="P2")
    )
    building = InsuredObject.objects.create(
        object_type=InsuredObject.ObjectType.PROPERTY,
        label="Building A",
    )
    vehicle = InsuredObject.objects.create(
        object_type=InsuredObject.ObjectType.VEHICLE,
        label="Vehicle B",
    )
    PolicyObject.objects.create(policy=first, insured_object=building)
    PolicyObject.objects.create(policy=first, insured_object=vehicle)
    PolicyObject.objects.create(policy=second, insured_object=building)
    assert first.policy_objects.count() == 2
    assert building.policy_links.count() == 2

    with pytest.raises(ValidationError):
        PolicyObject.objects.create(policy=first, insured_object=building)


@pytest.mark.django_db
def test_archived_object_remains_linked(insurer, insurance_type):
    policy = Policy.objects.create(**_policy_kwargs(insurer, insurance_type))
    obj = InsuredObject.objects.create(
        object_type=InsuredObject.ObjectType.OTHER,
        label="Archiveable Object",
        is_archived=True,
    )
    link = PolicyObject.objects.create(policy=policy, insured_object=obj)
    assert link.insured_object.is_archived is True


@pytest.mark.django_db
def test_insured_object_delete_protected(insurer, insurance_type):
    policy = Policy.objects.create(**_policy_kwargs(insurer, insurance_type))
    obj = InsuredObject.objects.create(
        object_type=InsuredObject.ObjectType.PROPERTY,
        label="Protected Building",
    )
    PolicyObject.objects.create(policy=policy, insured_object=obj)
    with pytest.raises(ProtectedError):
        obj.delete()


@pytest.mark.django_db
def test_admin_blocks_hard_delete_for_policy_and_object(
    client,
    staff_user,
    insurer,
    insurance_type,
):
    policy = Policy.objects.create(**_policy_kwargs(insurer, insurance_type))
    obj = InsuredObject.objects.create(
        object_type=InsuredObject.ObjectType.PERSON,
        label="Protected Person Object",
    )
    client.force_login(staff_user)
    policy_delete = reverse("admin:policies_policy_delete", args=[policy.pk])
    assert client.get(policy_delete).status_code == 403
    object_delete = reverse("admin:policies_insuredobject_delete", args=[obj.pk])
    assert client.get(object_delete).status_code == 403
    assert Policy.objects.filter(pk=policy.pk).exists()
    assert InsuredObject.objects.filter(pk=obj.pk).exists()


@pytest.mark.django_db
def test_admin_access_and_search_filter(
    client,
    staff_user,
    plain_user,
    insurer,
    insurance_type,
):
    Policy.objects.create(
        **_policy_kwargs(insurer, insurance_type, policy_number="FIND-ME")
    )
    Policy.objects.create(
        **_policy_kwargs(
            insurer,
            insurance_type,
            policy_number="OTHER",
            status=Policy.Status.DRAFT,
        )
    )
    client.force_login(staff_user)
    changelist = reverse("admin:policies_policy_changelist")
    assert client.get(changelist).status_code == 200
    search = client.get(changelist, {"q": "FIND-ME"})
    assert b"FIND-ME" in search.content
    assert b"OTHER" not in search.content
    filtered = client.get(changelist, {"status__exact": Policy.Status.DRAFT})
    assert b"OTHER" in filtered.content
    assert b"FIND-ME" not in filtered.content

    client.logout()
    anon = client.get(changelist)
    assert anon.status_code == 302
    assert "/admin/login/" in anon["Location"]

    client.force_login(plain_user)
    denied = client.get(changelist)
    assert denied.status_code == 302
    assert "/admin/login/" in denied["Location"]


@pytest.mark.django_db
def test_dashboard_policy_link_respects_permission(client, staff_user, plain_user):
    client.force_login(staff_user)
    assert "Polisy" in client.get(reverse("dashboard")).content.decode()
    client.force_login(plain_user)
    assert "Polisy" not in client.get(reverse("dashboard")).content.decode()


@pytest.mark.django_db
def test_no_missing_migrations():
    from django.core.management import call_command

    try:
        call_command("makemigrations", check=True, dry_run=True, verbosity=0)
    except SystemExit as exc:
        pytest.fail(f"Missing migrations detected: {exc}")
