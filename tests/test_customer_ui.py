"""Tests for the audited customer management UI (CUST-002)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import NoReverseMatch, reverse

from audit.models import AuditEvent
from customers.models import Customer

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
    user = User.objects.create_user(username="cust-viewer", password=PASSWORD)
    return _grant(user, "view_customer")


@pytest.fixture
def editor(db):
    user = User.objects.create_user(username="cust-editor", password=PASSWORD)
    return _grant(user, "view_customer", "change_customer")


@pytest.fixture
def creator(db):
    user = User.objects.create_user(username="cust-creator", password=PASSWORD)
    return _grant(user, "view_customer", "add_customer")


@pytest.fixture
def manager(db):
    user = User.objects.create_user(username="cust-manager", password=PASSWORD)
    return _grant(user, "view_customer", "add_customer", "change_customer")


@pytest.fixture
def plain_user(db):
    return User.objects.create_user(username="cust-plain-ui", password=PASSWORD)


def _customer(**kwargs) -> Customer:
    defaults = {
        "customer_type": Customer.CustomerType.PERSON,
        "display_name": "Synthetic Customer",
    }
    defaults.update(kwargs)
    return Customer.objects.create(**defaults)


def _customer_audit_events():
    return AuditEvent.objects.filter(action__startswith="customer.")


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("name", "needs_pk"),
    [
        ("customers:list", False),
        ("customers:create", False),
        ("customers:detail", True),
        ("customers:edit", True),
        ("customers:archive", True),
        ("customers:restore", True),
    ],
)
def test_login_required_for_all_customer_views(client, name, needs_pk):
    kwargs = {}
    if needs_pk:
        customer = _customer(display_name="Login Gate")
        kwargs["pk"] = customer.pk
    url = reverse(name, kwargs=kwargs)
    method = client.post if name.endswith(("archive", "restore")) else client.get
    response = method(url)
    assert response.status_code == 302
    assert response["Location"].startswith(reverse("login"))


@pytest.mark.django_db
def test_forbidden_without_permissions(client, plain_user):
    customer = _customer(display_name="Forbidden Target")
    client.force_login(plain_user)
    detail = reverse("customers:detail", args=[customer.pk])
    edit = reverse("customers:edit", args=[customer.pk])
    archive = reverse("customers:archive", args=[customer.pk])
    restore = reverse("customers:restore", args=[customer.pk])
    assert client.get(reverse("customers:list")).status_code == 403
    assert client.get(reverse("customers:create")).status_code == 403
    assert client.get(detail).status_code == 403
    assert client.get(edit).status_code == 403
    assert client.post(archive).status_code == 403
    assert client.post(restore).status_code == 403


@pytest.mark.django_db
def test_view_permission_allows_list_and_detail_only(client, viewer):
    customer = _customer(display_name="Visible Only")
    client.force_login(viewer)
    detail = reverse("customers:detail", args=[customer.pk])
    edit = reverse("customers:edit", args=[customer.pk])
    archive = reverse("customers:archive", args=[customer.pk])
    assert client.get(reverse("customers:list")).status_code == 200
    assert client.get(detail).status_code == 200
    assert client.get(reverse("customers:create")).status_code == 403
    assert client.get(edit).status_code == 403
    assert client.post(archive).status_code == 403


@pytest.mark.django_db
def test_list_defaults_to_active_customers(client, viewer):
    active = _customer(display_name="Active One")
    archived = _customer(display_name="Archived One", is_archived=True)
    client.force_login(viewer)
    content = client.get(reverse("customers:list")).content.decode()
    assert active.display_name in content
    assert archived.display_name not in content


@pytest.mark.django_db
def test_status_filters(client, viewer):
    active = _customer(display_name="Filter Active")
    archived = _customer(display_name="Filter Archived", is_archived=True)
    client.force_login(viewer)
    list_url = reverse("customers:list")

    active_page = client.get(list_url, {"status": "active"}).content.decode()
    assert active.display_name in active_page
    assert archived.display_name not in active_page

    archived_page = client.get(list_url, {"status": "archived"}).content.decode()
    assert archived.display_name in archived_page
    assert active.display_name not in archived_page

    all_page = client.get(list_url, {"status": "all"}).content.decode()
    assert active.display_name in all_page
    assert archived.display_name in all_page


@pytest.mark.django_db
def test_customer_type_filter(client, viewer):
    person = _customer(
        display_name="Type Person",
        customer_type=Customer.CustomerType.PERSON,
    )
    company = _customer(
        display_name="Type Company",
        customer_type=Customer.CustomerType.COMPANY,
    )
    client.force_login(viewer)
    content = client.get(
        reverse("customers:list"),
        {"customer_type": Customer.CustomerType.COMPANY, "status": "all"},
    ).content.decode()
    assert company.display_name in content
    assert person.display_name not in content


@pytest.mark.django_db
def test_search_by_name_email_and_phone(client, viewer):
    by_name = _customer(display_name="Alpha Search")
    by_email = _customer(display_name="Other Name", email="unique-search@example.test")
    by_phone = _customer(display_name="Phone Holder", phone="+48 111 222 999")
    unrelated = _customer(display_name="Unrelated")
    client.force_login(viewer)
    list_url = reverse("customers:list")

    name_hit = client.get(list_url, {"q": "alpha", "status": "all"}).content.decode()
    assert by_name.display_name in name_hit
    assert unrelated.display_name not in name_hit

    email_hit = client.get(
        list_url, {"q": "UNIQUE-SEARCH@EXAMPLE.TEST", "status": "all"}
    ).content.decode()
    assert by_email.display_name in email_hit
    assert unrelated.display_name not in email_hit

    phone_hit = client.get(
        list_url, {"q": "111 222 999", "status": "all"}
    ).content.decode()
    assert by_phone.display_name in phone_hit
    assert unrelated.display_name not in phone_hit


@pytest.mark.django_db
def test_pagination_is_25_per_page(client, viewer):
    for index in range(26):
        _customer(display_name=f"Paged Customer {index:02d}")
    client.force_login(viewer)
    page1 = client.get(reverse("customers:list"))
    assert page1.status_code == 200
    assert page1.context["paginator"].per_page == 25
    assert len(page1.context["customers"]) == 25

    page2 = client.get(reverse("customers:list"), {"page": "2"})
    assert page2.status_code == 200
    assert len(page2.context["customers"]) == 1


@pytest.mark.django_db
def test_pagination_preserves_filters(client, viewer):
    for index in range(26):
        _customer(
            display_name=f"Preserve {index:02d}",
            customer_type=Customer.CustomerType.COMPANY,
            is_archived=True,
        )
    client.force_login(viewer)
    response = client.get(
        reverse("customers:list"),
        {
            "status": "archived",
            "customer_type": "COMPANY",
            "q": "Preserve",
            "page": "1",
        },
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "status=archived" in content
    assert "customer_type=COMPANY" in content
    assert "q=Preserve" in content
    assert "page=2" in content


@pytest.mark.django_db
def test_create_customer_success_and_audit(client, creator):
    client.force_login(creator)
    response = client.post(
        reverse("customers:create"),
        {
            "customer_type": Customer.CustomerType.PERSON,
            "display_name": "New Synthetic",
            "email": "new@example.test",
            "phone": "+48 200 300 400",
        },
    )
    customer = Customer.objects.get(display_name="New Synthetic")
    assert response.status_code == 302
    assert response["Location"] == reverse("customers:detail", args=[customer.pk])

    events = AuditEvent.objects.filter(action="customer.created")
    assert events.count() == 1
    event = events.get()
    assert event.actor_id == creator.pk
    assert event.target_type == "customers.customer"
    assert event.target_id == str(customer.pk)
    assert event.summary == "Customer record created."
    assert "New Synthetic" not in event.summary
    assert "new@example.test" not in event.summary
    assert "+48 200 300 400" not in event.summary


@pytest.mark.django_db
def test_invalid_create_form_has_no_audit(client, creator):
    client.force_login(creator)
    response = client.post(
        reverse("customers:create"),
        {
            "customer_type": Customer.CustomerType.PERSON,
            "display_name": "   ",
            "email": "",
            "phone": "",
        },
    )
    assert response.status_code == 200
    assert Customer.objects.count() == 0
    assert _customer_audit_events().count() == 0
    assert response.context["form"].errors


@pytest.mark.django_db
def test_create_normalizes_whitespace(client, creator):
    client.force_login(creator)
    client.post(
        reverse("customers:create"),
        {
            "customer_type": Customer.CustomerType.COMPANY,
            "display_name": "  Trimmed Co  ",
            "email": "  trimmed@example.test  ",
            "phone": "  +48 123  ",
        },
    )
    customer = Customer.objects.get()
    assert customer.display_name == "Trimmed Co"
    assert customer.email == "trimmed@example.test"
    assert customer.phone == "+48 123"


@pytest.mark.django_db
def test_duplicate_customers_allowed_via_ui(client, creator):
    client.force_login(creator)
    payload = {
        "customer_type": Customer.CustomerType.PERSON,
        "display_name": "Shared UI Name",
        "email": "shared-ui@example.test",
        "phone": "+48 555 555 555",
    }
    assert client.post(reverse("customers:create"), payload).status_code == 302
    assert client.post(reverse("customers:create"), payload).status_code == 302
    assert Customer.objects.filter(display_name="Shared UI Name").count() == 2
    assert AuditEvent.objects.filter(action="customer.created").count() == 2


@pytest.mark.django_db
def test_detail_view_shows_customer_fields(client, viewer):
    customer = _customer(
        display_name="Detail Person",
        email="detail@example.test",
        phone="+48 777 888 999",
    )
    client.force_login(viewer)
    content = client.get(
        reverse("customers:detail", args=[customer.pk])
    ).content.decode()
    assert "Detail Person" in content
    assert "detail@example.test" in content
    assert "+48 777 888 999" in content
    assert "Aktywny" in content
    assert "Edytuj" not in content


@pytest.mark.django_db
def test_edit_updates_existing_record_and_audits_field_names(client, editor):
    customer = _customer(
        display_name="Before Edit",
        email="before@example.test",
        phone="+48 100 100 100",
    )
    client.force_login(editor)
    response = client.post(
        reverse("customers:edit", args=[customer.pk]),
        {
            "customer_type": Customer.CustomerType.COMPANY,
            "display_name": "After Edit",
            "email": "after@example.test",
            "phone": "+48 100 100 100",
        },
    )
    assert response.status_code == 302
    assert Customer.objects.count() == 1
    customer.refresh_from_db()
    assert customer.display_name == "After Edit"
    assert customer.email == "after@example.test"
    assert customer.customer_type == Customer.CustomerType.COMPANY

    event = AuditEvent.objects.get(action="customer.updated")
    assert event.target_id == str(customer.pk)
    assert "display_name" in event.summary
    assert "email" in event.summary
    assert "customer_type" in event.summary
    assert "After Edit" not in event.summary
    assert "after@example.test" not in event.summary
    assert _customer_audit_events().count() == 1


@pytest.mark.django_db
def test_edit_without_changes_skips_audit(client, editor):
    customer = _customer(
        display_name="Unchanged",
        email="same@example.test",
        phone="+48 101 101 101",
        customer_type=Customer.CustomerType.PERSON,
    )
    client.force_login(editor)
    response = client.post(
        reverse("customers:edit", args=[customer.pk]),
        {
            "customer_type": Customer.CustomerType.PERSON,
            "display_name": "Unchanged",
            "email": "same@example.test",
            "phone": "+48 101 101 101",
        },
    )
    assert response.status_code == 302
    assert _customer_audit_events().count() == 0


@pytest.mark.django_db
def test_archive_and_restore_with_audit(client, editor):
    customer = _customer(display_name="Lifecycle")
    client.force_login(editor)

    archive = client.post(reverse("customers:archive", args=[customer.pk]))
    assert archive.status_code == 302
    customer.refresh_from_db()
    assert customer.is_archived is True
    archived_event = AuditEvent.objects.get(action="customer.archived")
    assert archived_event.target_id == str(customer.pk)
    assert "Lifecycle" not in archived_event.summary

    restore = client.post(reverse("customers:restore", args=[customer.pk]))
    assert restore.status_code == 302
    customer.refresh_from_db()
    assert customer.is_archived is False
    restored_event = AuditEvent.objects.get(action="customer.restored")
    assert restored_event.target_id == str(customer.pk)
    assert _customer_audit_events().count() == 2


@pytest.mark.django_db
def test_archive_restore_idempotent_without_extra_audit(client, editor):
    customer = _customer(display_name="Already Archived", is_archived=True)
    client.force_login(editor)
    archive_url = reverse("customers:archive", args=[customer.pk])
    assert client.post(archive_url).status_code == 302
    assert _customer_audit_events().count() == 0

    active = _customer(display_name="Already Active")
    restore_url = reverse("customers:restore", args=[active.pk])
    assert client.post(restore_url).status_code == 302
    assert _customer_audit_events().count() == 0


@pytest.mark.django_db
def test_archive_and_restore_reject_get(client, editor):
    customer = _customer(display_name="Method Check")
    client.force_login(editor)
    archive_url = reverse("customers:archive", args=[customer.pk])
    restore_url = reverse("customers:restore", args=[customer.pk])
    assert client.get(archive_url).status_code == 405
    assert client.get(restore_url).status_code == 405


@pytest.mark.django_db
def test_archive_requires_csrf(csrf_client, editor):
    customer = _customer(display_name="CSRF Target")
    csrf_client.force_login(editor)
    response = csrf_client.post(reverse("customers:archive", args=[customer.pk]))
    assert response.status_code == 403
    customer.refresh_from_db()
    assert customer.is_archived is False
    assert _customer_audit_events().count() == 0


@pytest.mark.django_db
def test_audit_failure_rolls_back_create(client, creator):
    client.force_login(creator)
    with patch(
        "customers.services.record_audit_event",
        side_effect=RuntimeError("audit unavailable"),
    ):
        with pytest.raises(RuntimeError):
            client.post(
                reverse("customers:create"),
                {
                    "customer_type": Customer.CustomerType.PERSON,
                    "display_name": "Rollback Create",
                    "email": "",
                    "phone": "",
                },
            )
    assert Customer.objects.filter(display_name="Rollback Create").count() == 0
    assert _customer_audit_events().count() == 0


@pytest.mark.django_db
def test_audit_failure_rolls_back_update(client, editor):
    customer = _customer(display_name="Rollback Update")
    client.force_login(editor)
    with patch(
        "customers.services.record_audit_event",
        side_effect=RuntimeError("audit unavailable"),
    ):
        with pytest.raises(RuntimeError):
            client.post(
                reverse("customers:edit", args=[customer.pk]),
                {
                    "customer_type": Customer.CustomerType.PERSON,
                    "display_name": "Should Not Persist",
                    "email": "",
                    "phone": "",
                },
            )
    customer.refresh_from_db()
    assert customer.display_name == "Rollback Update"
    assert _customer_audit_events().count() == 0


@pytest.mark.django_db
def test_dashboard_customers_link_points_to_new_ui(client, viewer, plain_user):
    client.force_login(viewer)
    response = client.get(reverse("dashboard"))
    content = response.content.decode()
    assert reverse("customers:list") in content
    assert "Klienci" in content
    assert reverse("admin:customers_customer_changelist") not in content

    client.force_login(plain_user)
    plain = client.get(reverse("dashboard")).content.decode()
    assert "Klienci" not in plain


@pytest.mark.django_db
def test_no_public_hard_delete_route():
    with pytest.raises(NoReverseMatch):
        reverse("customers:delete", args=[1])
    customer = _customer(display_name="No Delete Route")
    # Direct path must not expose a delete endpoint under the customers namespace.
    from django.urls import resolve
    from django.urls.exceptions import Resolver404

    with pytest.raises(Resolver404):
        resolve(f"/customers/{customer.pk}/delete/")


@pytest.mark.django_db
def test_action_buttons_respect_permissions(client, viewer, editor, creator):
    customer = _customer(display_name="Buttons")
    client.force_login(viewer)
    viewer_list = client.get(reverse("customers:list")).content.decode()
    assert "Dodaj klienta" not in viewer_list

    client.force_login(creator)
    creator_list = client.get(reverse("customers:list")).content.decode()
    assert "Dodaj klienta" in creator_list

    client.force_login(editor)
    detail = client.get(
        reverse("customers:detail", args=[customer.pk])
    ).content.decode()
    assert "Edytuj" in detail
    assert "Potwierdź archiwizację" in detail
