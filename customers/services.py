"""Explicit customer write operations with audit recording."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from audit.services import record_audit_event
from customers.models import Customer

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

TARGET_TYPE = "customers.customer"


def _normalized_form_values(
    *,
    customer_type: str,
    display_name: str,
    email: str,
    phone: str,
) -> dict[str, str]:
    return {
        "customer_type": customer_type,
        "display_name": (display_name or "").strip(),
        "email": (email or "").strip(),
        "phone": (phone or "").strip(),
    }


@transaction.atomic
def create_customer(
    *,
    actor: AbstractBaseUser,
    customer_type: str,
    display_name: str,
    email: str = "",
    phone: str = "",
) -> Customer:
    """Create a customer and record exactly one audit event."""
    values = _normalized_form_values(
        customer_type=customer_type,
        display_name=display_name,
        email=email,
        phone=phone,
    )
    customer = Customer(**values)
    customer.save()
    record_audit_event(
        actor=actor,
        action="customer.created",
        target_type=TARGET_TYPE,
        target_id=str(customer.pk),
        summary="Customer record created.",
    )
    return customer


@transaction.atomic
def update_customer(
    *,
    actor: AbstractBaseUser,
    customer: Customer,
    customer_type: str,
    display_name: str,
    email: str = "",
    phone: str = "",
) -> Customer:
    """Update a customer; audit only when at least one field changes."""
    # ModelForm validation may have already mutated the in-memory instance.
    customer.refresh_from_db()
    values = _normalized_form_values(
        customer_type=customer_type,
        display_name=display_name,
        email=email,
        phone=phone,
    )
    changed = [
        name for name, value in values.items() if getattr(customer, name) != value
    ]
    if not changed:
        return customer

    for name, value in values.items():
        setattr(customer, name, value)
    customer.save()
    record_audit_event(
        actor=actor,
        action="customer.updated",
        target_type=TARGET_TYPE,
        target_id=str(customer.pk),
        summary=f"Updated fields: {', '.join(changed)}.",
    )
    return customer


@transaction.atomic
def archive_customer(
    *,
    actor: AbstractBaseUser,
    customer: Customer,
) -> tuple[Customer, bool]:
    """Archive a customer under a row lock; audit only when state changes."""
    locked = Customer.objects.select_for_update().get(pk=customer.pk)
    if locked.is_archived:
        return locked, False
    locked.is_archived = True
    locked.save(update_fields=["is_archived", "updated_at"])
    record_audit_event(
        actor=actor,
        action="customer.archived",
        target_type=TARGET_TYPE,
        target_id=str(locked.pk),
        summary="Customer record archived.",
    )
    return locked, True


@transaction.atomic
def restore_customer(
    *,
    actor: AbstractBaseUser,
    customer: Customer,
) -> tuple[Customer, bool]:
    """Restore a customer under a row lock; audit only when state changes."""
    locked = Customer.objects.select_for_update().get(pk=customer.pk)
    if not locked.is_archived:
        return locked, False
    locked.is_archived = False
    locked.save(update_fields=["is_archived", "updated_at"])
    record_audit_event(
        actor=actor,
        action="customer.restored",
        target_type=TARGET_TYPE,
        target_id=str(locked.pk),
        summary="Customer record restored.",
    )
    return locked, True
