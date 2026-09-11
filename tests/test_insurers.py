"""Tests for insurer and insurance-type dictionaries."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import Client
from django.urls import reverse

from insurers.models import InsuranceType, Insurer

User = get_user_model()


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def staff_user(db):
    user = User.objects.create_user(
        username="dict-staff",
        password="safe-test-password-123",
        is_staff=True,
    )
    user.user_permissions.add(
        Permission.objects.get(codename="view_insurer"),
        Permission.objects.get(codename="add_insurer"),
        Permission.objects.get(codename="change_insurer"),
        Permission.objects.get(codename="view_insurancetype"),
        Permission.objects.get(codename="add_insurancetype"),
        Permission.objects.get(codename="change_insurancetype"),
    )
    return user


@pytest.fixture
def plain_user(db):
    return User.objects.create_user(
        username="dict-plain",
        password="safe-test-password-123",
    )


@pytest.mark.django_db
def test_create_insurer():
    insurer = Insurer.objects.create(
        name="Synthetic Mutual Co",
        contact_email="desk@example.test",
    )
    assert insurer.pk is not None
    assert str(insurer) == "Synthetic Mutual Co"
    assert list(Insurer.objects.values_list("name", flat=True)) == [
        "Synthetic Mutual Co"
    ]


@pytest.mark.django_db
def test_create_insurance_type():
    insurance_type = InsuranceType.objects.create(
        name="Synthetic Property Cover",
        description="Synthetic test category",
    )
    assert insurance_type.pk is not None
    assert str(insurance_type) == "Synthetic Property Cover"


@pytest.mark.django_db
def test_reject_blank_name():
    with pytest.raises(ValidationError) as exc_info:
        Insurer.objects.create(name="   ")
    assert "name" in exc_info.value.message_dict

    with pytest.raises(ValidationError):
        InsuranceType.objects.create(name="")


@pytest.mark.django_db
def test_normalize_surrounding_whitespace():
    insurer = Insurer.objects.create(name="  Acme Shield  ")
    insurance_type = InsuranceType.objects.create(name="  Home Cover  ")
    insurer.refresh_from_db()
    insurance_type.refresh_from_db()
    assert insurer.name == "Acme Shield"
    assert insurance_type.name == "Home Cover"


@pytest.mark.django_db
def test_case_insensitive_duplicate_rejected():
    Insurer.objects.create(name="Nordic Cover")
    with pytest.raises(ValidationError):
        Insurer.objects.create(name="nordic cover")

    InsuranceType.objects.create(name="Motor")
    with pytest.raises(ValidationError):
        InsuranceType.objects.create(name="MOTOR")


@pytest.mark.django_db
def test_whitespace_duplicate_rejected():
    Insurer.objects.create(name="Baltic Care")
    with pytest.raises(ValidationError):
        Insurer.objects.create(name="  Baltic Care  ")


@pytest.mark.django_db
def test_postgresql_enforces_case_insensitive_uniqueness():
    Insurer.objects.create(name="Unique Guard")
    with pytest.raises(IntegrityError), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO insurers_insurer "
                "(name, contact_email, contact_phone, website, is_active, "
                "created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, NOW(), NOW())",
                ["unique guard", "", "", "", True],
            )


@pytest.mark.django_db
def test_postgresql_rejects_trimmed_case_insensitive_insurer_duplicate():
    """DB constraint must reject spaced/cased duplicates even without save()."""
    Insurer.objects.create(name="Example Insurer")
    with pytest.raises(IntegrityError), transaction.atomic():
        Insurer.objects.bulk_create(
            [Insurer(name="  example insurer  ", is_active=True)]
        )


@pytest.mark.django_db
def test_postgresql_rejects_trimmed_case_insensitive_type_duplicate():
    InsuranceType.objects.create(name="Example Type")
    with pytest.raises(IntegrityError), transaction.atomic():
        InsuranceType.objects.bulk_create(
            [InsuranceType(name="  example type  ", is_active=True)]
        )


@pytest.mark.django_db
def test_is_active_defaults_to_true():
    insurer = Insurer.objects.create(name="Default Active Insurer")
    insurance_type = InsuranceType.objects.create(name="Default Active Type")
    assert insurer.is_active is True
    assert insurance_type.is_active is True


@pytest.mark.django_db
def test_deactivate_and_reactivate():
    insurer = Insurer.objects.create(name="Toggle Insurer")
    insurer.is_active = False
    insurer.save()
    insurer.refresh_from_db()
    assert insurer.is_active is False

    insurer.is_active = True
    insurer.save()
    insurer.refresh_from_db()
    assert insurer.is_active is True

    assert Insurer.objects.filter(pk=insurer.pk).exists()


@pytest.mark.django_db
def test_admin_blocks_hard_delete(client, staff_user):
    insurer = Insurer.objects.create(name="Protected Insurer")
    insurance_type = InsuranceType.objects.create(name="Protected Type")
    client.force_login(staff_user)

    delete_insurer = reverse("admin:insurers_insurer_delete", args=[insurer.pk])
    delete_type = reverse(
        "admin:insurers_insurancetype_delete",
        args=[insurance_type.pk],
    )

    assert client.get(delete_insurer).status_code == 403
    assert client.post(delete_insurer).status_code == 403
    assert client.get(delete_type).status_code == 403
    assert client.post(delete_type).status_code == 403
    assert Insurer.objects.filter(pk=insurer.pk).exists()
    assert InsuranceType.objects.filter(pk=insurance_type.pk).exists()


@pytest.mark.django_db
def test_admin_accessible_for_staff_with_permissions(client, staff_user):
    client.force_login(staff_user)
    insurer_list = reverse("admin:insurers_insurer_changelist")
    type_list = reverse("admin:insurers_insurancetype_changelist")

    assert client.get(insurer_list).status_code == 200
    assert client.get(type_list).status_code == 200


@pytest.mark.django_db
def test_admin_denied_for_anonymous(client):
    insurer_list = reverse("admin:insurers_insurer_changelist")
    response = client.get(insurer_list)
    assert response.status_code == 302
    assert "/admin/login/" in response["Location"]


@pytest.mark.django_db
def test_admin_denied_for_user_without_permissions(client, plain_user):
    client.force_login(plain_user)
    insurer_list = reverse("admin:insurers_insurer_changelist")
    response = client.get(insurer_list)
    assert response.status_code == 302
    assert "/admin/login/" in response["Location"]


@pytest.mark.django_db
def test_admin_search_and_filter(client, staff_user):
    Insurer.objects.create(name="Alpha Carrier", is_active=True)
    Insurer.objects.create(name="Beta Carrier", is_active=False)
    client.force_login(staff_user)

    changelist = reverse("admin:insurers_insurer_changelist")
    search = client.get(changelist, {"q": "Alpha"})
    assert search.status_code == 200
    assert b"Alpha Carrier" in search.content
    assert b"Beta Carrier" not in search.content

    filtered = client.get(changelist, {"is_active__exact": "0"})
    assert filtered.status_code == 200
    assert b"Beta Carrier" in filtered.content
    assert b"Alpha Carrier" not in filtered.content


@pytest.mark.django_db
def test_dashboard_settings_link_respects_permissions(client, staff_user, plain_user):
    client.force_login(staff_user)
    staff_dashboard = client.get(reverse("dashboard"))
    assert staff_dashboard.status_code == 200
    staff_content = staff_dashboard.content.decode()
    assert "Ustawienia" in staff_content
    assert reverse("insurers:settings") in staff_content
    assert "/admin/" not in staff_content
    assert "Django Admin" not in staff_content

    client.force_login(plain_user)
    plain_dashboard = client.get(reverse("dashboard"))
    assert plain_dashboard.status_code == 200
    plain_content = plain_dashboard.content.decode()
    assert "Ustawienia" not in plain_content
    assert reverse("insurers:settings") not in plain_content


@pytest.mark.django_db
def test_default_ordering_is_alphabetical():
    Insurer.objects.create(name="Zulu Cover")
    Insurer.objects.create(name="Alpha Cover")
    Insurer.objects.create(name="Middle Cover")
    assert list(Insurer.objects.values_list("name", flat=True)) == [
        "Alpha Cover",
        "Middle Cover",
        "Zulu Cover",
    ]


@pytest.mark.django_db
def test_no_missing_migrations():
    from django.core.management import call_command

    try:
        call_command("makemigrations", check=True, dry_run=True, verbosity=0)
    except SystemExit as exc:
        pytest.fail(f"Missing migrations detected: {exc}")
