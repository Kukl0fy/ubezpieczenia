"""Tests for the customer register foundation."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import Client
from django.urls import reverse

from customers.models import Customer

User = get_user_model()


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def staff_user(db):
    user = User.objects.create_user(
        username="cust-staff",
        password="safe-test-password-123",
        is_staff=True,
    )
    user.user_permissions.add(
        Permission.objects.get(codename="view_customer"),
        Permission.objects.get(codename="add_customer"),
        Permission.objects.get(codename="change_customer"),
    )
    return user


@pytest.fixture
def plain_user(db):
    return User.objects.create_user(
        username="cust-plain",
        password="safe-test-password-123",
    )


@pytest.mark.django_db
def test_create_person():
    customer = Customer.objects.create(
        customer_type=Customer.CustomerType.PERSON,
        display_name="Ada Synthetic",
        email="ada@example.test",
    )
    assert customer.pk is not None
    assert customer.customer_type == Customer.CustomerType.PERSON


@pytest.mark.django_db
def test_create_company():
    customer = Customer.objects.create(
        customer_type=Customer.CustomerType.COMPANY,
        display_name="Synthetic Holdings Sp. z o.o.",
        phone="+48 500 000 001",
    )
    assert customer.pk is not None
    assert customer.customer_type == Customer.CustomerType.COMPANY


@pytest.mark.django_db
def test_str_returns_display_name():
    customer = Customer.objects.create(
        customer_type=Customer.CustomerType.PERSON,
        display_name="Jan Testowy",
    )
    assert str(customer) == "Jan Testowy"


@pytest.mark.django_db
def test_is_archived_defaults_to_false():
    customer = Customer.objects.create(
        customer_type=Customer.CustomerType.PERSON,
        display_name="Default Archive Flag",
    )
    assert customer.is_archived is False


@pytest.mark.django_db
def test_normalize_surrounding_whitespace():
    customer = Customer.objects.create(
        customer_type=Customer.CustomerType.PERSON,
        display_name="  Ewa Przykład  ",
        email="  ewa@example.test  ",
        phone="  +48 111 222 333  ",
    )
    customer.refresh_from_db()
    assert customer.display_name == "Ewa Przykład"
    assert customer.email == "ewa@example.test"
    assert customer.phone == "+48 111 222 333"


@pytest.mark.django_db
def test_reject_blank_display_name():
    with pytest.raises(ValidationError) as exc_info:
        Customer.objects.create(
            customer_type=Customer.CustomerType.PERSON,
            display_name="   ",
        )
    assert "display_name" in exc_info.value.message_dict


@pytest.mark.django_db
def test_reject_invalid_customer_type():
    with pytest.raises(ValidationError):
        Customer.objects.create(
            customer_type="UNKNOWN",
            display_name="Invalid Type Customer",
        )


@pytest.mark.django_db
def test_postgresql_rejects_invalid_customer_type():
    with pytest.raises(IntegrityError), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO customers_customer "
                "(customer_type, display_name, email, phone, is_archived, "
                "created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, NOW(), NOW())",
                ["ORG", "Raw SQL Customer", "", "", False],
            )


@pytest.mark.django_db
def test_duplicate_display_names_allowed():
    Customer.objects.create(
        customer_type=Customer.CustomerType.PERSON,
        display_name="Shared Name",
    )
    second = Customer.objects.create(
        customer_type=Customer.CustomerType.COMPANY,
        display_name="Shared Name",
    )
    assert Customer.objects.filter(display_name="Shared Name").count() == 2
    assert second.pk is not None


@pytest.mark.django_db
def test_shared_email_and_phone_allowed():
    shared_email = "shared@example.test"
    shared_phone = "+48 600 600 600"
    Customer.objects.create(
        customer_type=Customer.CustomerType.PERSON,
        display_name="Person A",
        email=shared_email,
        phone=shared_phone,
    )
    Customer.objects.create(
        customer_type=Customer.CustomerType.PERSON,
        display_name="Person B",
        email=shared_email,
        phone=shared_phone,
    )
    assert Customer.objects.filter(email=shared_email).count() == 2
    assert Customer.objects.filter(phone=shared_phone).count() == 2


@pytest.mark.django_db
def test_archive_and_restore():
    customer = Customer.objects.create(
        customer_type=Customer.CustomerType.COMPANY,
        display_name="Archive Target",
    )
    customer.is_archived = True
    customer.save()
    customer.refresh_from_db()
    assert customer.is_archived is True

    customer.is_archived = False
    customer.save()
    customer.refresh_from_db()
    assert customer.is_archived is False
    assert Customer.objects.filter(pk=customer.pk).exists()


@pytest.mark.django_db
def test_default_manager_includes_archived():
    active = Customer.objects.create(
        customer_type=Customer.CustomerType.PERSON,
        display_name="Active Customer",
    )
    archived = Customer.objects.create(
        customer_type=Customer.CustomerType.PERSON,
        display_name="Archived Customer",
        is_archived=True,
    )
    ids = set(Customer.objects.values_list("id", flat=True))
    assert active.id in ids
    assert archived.id in ids


@pytest.mark.django_db
def test_admin_blocks_hard_delete(client, staff_user):
    customer = Customer.objects.create(
        customer_type=Customer.CustomerType.PERSON,
        display_name="Protected Customer",
    )
    client.force_login(staff_user)
    delete_url = reverse("admin:customers_customer_delete", args=[customer.pk])
    assert client.get(delete_url).status_code == 403
    assert client.post(delete_url).status_code == 403
    assert Customer.objects.filter(pk=customer.pk).exists()


@pytest.mark.django_db
def test_admin_accessible_for_staff_with_permissions(client, staff_user):
    client.force_login(staff_user)
    response = client.get(reverse("admin:customers_customer_changelist"))
    assert response.status_code == 200


@pytest.mark.django_db
def test_admin_denied_for_anonymous(client):
    response = client.get(reverse("admin:customers_customer_changelist"))
    assert response.status_code == 302
    assert "/admin/login/" in response["Location"]


@pytest.mark.django_db
def test_admin_denied_for_user_without_permissions(client, plain_user):
    client.force_login(plain_user)
    response = client.get(reverse("admin:customers_customer_changelist"))
    assert response.status_code == 302
    assert "/admin/login/" in response["Location"]


@pytest.mark.django_db
def test_admin_search_and_filter(client, staff_user):
    Customer.objects.create(
        customer_type=Customer.CustomerType.PERSON,
        display_name="Alpha Person",
        email="alpha@example.test",
        phone="+48 101 101 101",
        is_archived=False,
    )
    Customer.objects.create(
        customer_type=Customer.CustomerType.COMPANY,
        display_name="Beta Company",
        email="beta@example.test",
        is_archived=True,
    )
    client.force_login(staff_user)
    changelist = reverse("admin:customers_customer_changelist")

    search = client.get(changelist, {"q": "Alpha"})
    assert search.status_code == 200
    assert b"Alpha Person" in search.content
    assert b"Beta Company" not in search.content

    filtered = client.get(changelist, {"is_archived__exact": "1"})
    assert filtered.status_code == 200
    assert b"Beta Company" in filtered.content
    assert b"Alpha Person" not in filtered.content

    by_type = client.get(
        changelist,
        {"customer_type__exact": Customer.CustomerType.COMPANY},
    )
    assert by_type.status_code == 200
    assert b"Beta Company" in by_type.content
    assert b"Alpha Person" not in by_type.content


@pytest.mark.django_db
def test_dashboard_customer_link_respects_permission(client, staff_user, plain_user):
    client.force_login(staff_user)
    staff_content = client.get(reverse("dashboard")).content.decode()
    assert "Klienci" in staff_content
    assert reverse("customers:list") in staff_content
    assert reverse("admin:customers_customer_changelist") not in staff_content

    client.force_login(plain_user)
    plain_content = client.get(reverse("dashboard")).content.decode()
    assert "Klienci" not in plain_content


@pytest.mark.django_db
def test_default_ordering_by_display_name_then_id():
    Customer.objects.create(
        customer_type=Customer.CustomerType.PERSON,
        display_name="Zeta",
    )
    first_same = Customer.objects.create(
        customer_type=Customer.CustomerType.PERSON,
        display_name="Alpha",
    )
    second_same = Customer.objects.create(
        customer_type=Customer.CustomerType.COMPANY,
        display_name="Alpha",
    )
    ordered = list(Customer.objects.values_list("display_name", "id"))
    assert ordered == [
        ("Alpha", first_same.id),
        ("Alpha", second_same.id),
        ("Zeta", ordered[2][1]),
    ]


@pytest.mark.django_db
def test_no_missing_migrations():
    from django.core.management import call_command

    try:
        call_command("makemigrations", check=True, dry_run=True, verbosity=0)
    except SystemExit as exc:
        pytest.fail(f"Missing migrations detected: {exc}")
