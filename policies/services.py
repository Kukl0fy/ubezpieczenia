"""Explicit policy write operations with audit recording."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from audit.services import record_audit_event
from customers.models import Customer
from insurers.models import InsuranceType, Insurer
from policies.models import Policy, PolicyParty

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

TARGET_TYPE = "policies.policy"


def _normalized_values(
    *,
    policy_number: str,
    insurer: Insurer,
    insurance_type: InsuranceType,
    coverage_start: date,
    coverage_end: date,
    premium: Decimal | None,
    currency: str,
    notes: str,
) -> dict:
    return {
        "policy_number": (policy_number or "").strip(),
        "insurer": insurer,
        "insurance_type": insurance_type,
        "coverage_start": coverage_start,
        "coverage_end": coverage_end,
        "premium": premium,
        "currency": (currency or "").strip().upper(),
        "notes": (notes or "").strip(),
    }


def _changed_field_names(*, policy: Policy, values: dict) -> list[str]:
    changed: list[str] = []
    for name, value in values.items():
        if name in {"insurer", "insurance_type"}:
            current_id = getattr(policy, f"{name}_id")
            new_id = value.pk if value is not None else None
            if current_id != new_id:
                changed.append(name)
            continue
        if getattr(policy, name) != value:
            changed.append(name)
    return changed


@transaction.atomic
def create_policy(
    *,
    actor: AbstractBaseUser,
    primary_customer: Customer,
    policy_number: str,
    insurer: Insurer,
    insurance_type: InsuranceType,
    coverage_start: date,
    coverage_end: date,
    premium: Decimal | None = None,
    currency: str = "PLN",
    notes: str = "",
) -> Policy:
    """Create an ACTIVE policy with one POLICYHOLDER party and one audit event."""
    values = _normalized_values(
        policy_number=policy_number,
        insurer=insurer,
        insurance_type=insurance_type,
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        premium=premium,
        currency=currency,
        notes=notes,
    )
    policy = Policy(status=Policy.Status.ACTIVE, **values)
    policy.save()
    PolicyParty.objects.create(
        policy=policy,
        customer=primary_customer,
        role=PolicyParty.Role.POLICYHOLDER,
    )
    record_audit_event(
        actor=actor,
        action="policy.created",
        target_type=TARGET_TYPE,
        target_id=str(policy.pk),
        summary="Policy record created.",
    )
    return policy


@transaction.atomic
def update_policy(
    *,
    actor: AbstractBaseUser,
    policy: Policy,
    primary_customer: Customer,
    policy_number: str,
    insurer: Insurer,
    insurance_type: InsuranceType,
    coverage_start: date,
    coverage_end: date,
    premium: Decimal | None = None,
    currency: str = "PLN",
    notes: str = "",
) -> Policy:
    """Update editable policy fields; audit only when something changes."""
    policy.refresh_from_db()
    values = _normalized_values(
        policy_number=policy_number,
        insurer=insurer,
        insurance_type=insurance_type,
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        premium=premium,
        currency=currency,
        notes=notes,
    )
    changed = _changed_field_names(policy=policy, values=values)

    holder = (
        policy.parties.filter(role=PolicyParty.Role.POLICYHOLDER)
        .order_by("id")
        .first()
    )
    primary_changed = False
    if holder is None:
        PolicyParty.objects.create(
            policy=policy,
            customer=primary_customer,
            role=PolicyParty.Role.POLICYHOLDER,
        )
        primary_changed = True
    elif holder.customer_id != primary_customer.pk:
        holder.customer = primary_customer
        holder.save()
        primary_changed = True

    if not changed and not primary_changed:
        return policy

    for name, value in values.items():
        setattr(policy, name, value)
    if changed:
        policy.save()

    audit_fields = list(changed)
    if primary_changed:
        audit_fields.append("primary_customer")
    record_audit_event(
        actor=actor,
        action="policy.updated",
        target_type=TARGET_TYPE,
        target_id=str(policy.pk),
        summary=f"Updated fields: {', '.join(audit_fields)}.",
    )
    return policy


@transaction.atomic
def cancel_policy(
    *,
    actor: AbstractBaseUser,
    policy: Policy,
) -> tuple[Policy, bool]:
    """Cancel a policy under a row lock; refuse RENEWED; audit only on change."""
    locked = Policy.objects.select_for_update().get(pk=policy.pk)
    if locked.status == Policy.Status.RENEWED:
        raise ValidationError(
            _("Renewed policies cannot be cancelled in this workflow.")
        )
    if locked.status == Policy.Status.CANCELLED:
        return locked, False
    locked.status = Policy.Status.CANCELLED
    locked.save(update_fields=["status", "updated_at"])
    record_audit_event(
        actor=actor,
        action="policy.cancelled",
        target_type=TARGET_TYPE,
        target_id=str(locked.pk),
        summary="Policy record cancelled.",
    )
    return locked, True
