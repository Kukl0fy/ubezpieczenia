"""Explicit policy write operations with audit recording."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from audit.services import record_audit_event
from customers.models import Customer
from insurers.models import InsuranceType, Insurer
from policies.models import Policy, PolicyObject, PolicyParty
from policies.presenters import (
    COMPLEX_POLICYHOLDERS_MESSAGE,
    RENEWABLE_STATUSES,
    RENEWAL_NOT_ALLOWED_MESSAGE,
    RENEWED_CANCEL_BLOCKED_MESSAGE,
)

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

TARGET_TYPE = "policies.policy"


@dataclass(frozen=True)
class UpdatePolicyResult:
    policy: Policy
    warning: str | None = None


@dataclass(frozen=True)
class RenewPolicyResult:
    policy: Policy
    created: bool


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
) -> UpdatePolicyResult:
    """Update editable policy fields; never rewrite complex POLICYHOLDER sets."""
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

    holders = list(
        policy.parties.filter(role=PolicyParty.Role.POLICYHOLDER).order_by("id")
    )
    warning: str | None = None
    primary_changed = False

    if len(holders) > 1:
        # Keep every PolicyParty untouched; simplified UI cannot pick one primary.
        if primary_customer.pk != holders[0].customer_id:
            warning = COMPLEX_POLICYHOLDERS_MESSAGE
    elif not holders:
        PolicyParty.objects.create(
            policy=policy,
            customer=primary_customer,
            role=PolicyParty.Role.POLICYHOLDER,
        )
        primary_changed = True
    elif holders[0].customer_id != primary_customer.pk:
        holders[0].customer = primary_customer
        holders[0].save()
        primary_changed = True

    if not changed and not primary_changed:
        return UpdatePolicyResult(policy=policy, warning=warning)

    for name, value in values.items():
        setattr(policy, name, value)
    if changed:
        policy.save()

    audit_fields = list(changed)
    if primary_changed:
        audit_fields.append("primary_customer")
    if audit_fields:
        record_audit_event(
            actor=actor,
            action="policy.updated",
            target_type=TARGET_TYPE,
            target_id=str(policy.pk),
            summary=f"Updated fields: {', '.join(audit_fields)}.",
        )
    return UpdatePolicyResult(policy=policy, warning=warning)


@transaction.atomic
def cancel_policy(
    *,
    actor: AbstractBaseUser,
    policy: Policy,
) -> tuple[Policy, bool]:
    """Cancel a policy under a row lock; refuse RENEWED; audit only on change."""
    locked = Policy.objects.select_for_update().get(pk=policy.pk)
    if locked.status == Policy.Status.RENEWED:
        raise ValidationError(RENEWED_CANCEL_BLOCKED_MESSAGE)
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


@transaction.atomic
def renew_policy(
    *,
    actor: AbstractBaseUser,
    source: Policy,
    policy_number: str,
    insurer: Insurer,
    insurance_type: InsuranceType,
    coverage_start: date,
    coverage_end: date,
    premium: Decimal | None = None,
    currency: str = "PLN",
    notes: str = "",
) -> RenewPolicyResult:
    """Create a renewal policy linked to ``source``, or return the existing one."""
    locked = Policy.objects.select_for_update().get(pk=source.pk)
    existing = (
        Policy.objects.select_for_update()
        .filter(previous_policy=locked)
        .order_by("id")
        .first()
    )
    if existing is not None:
        return RenewPolicyResult(policy=existing, created=False)
    if locked.status not in RENEWABLE_STATUSES:
        raise ValidationError(RENEWAL_NOT_ALLOWED_MESSAGE)

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
    new_policy = Policy(
        status=Policy.Status.ACTIVE,
        previous_policy=locked,
        **values,
    )
    try:
        new_policy.save()
    except IntegrityError:
        existing = (
            Policy.objects.filter(previous_policy=locked).order_by("id").first()
        )
        if existing is None:
            raise
        return RenewPolicyResult(policy=existing, created=False)

    for party in locked.parties.order_by("id"):
        PolicyParty.objects.create(
            policy=new_policy,
            customer=party.customer,
            role=party.role,
        )
    for link in locked.policy_objects.order_by("id"):
        PolicyObject.objects.create(
            policy=new_policy,
            insured_object=link.insured_object,
        )

    locked.status = Policy.Status.RENEWED
    locked.save(update_fields=["status", "updated_at"])

    record_audit_event(
        actor=actor,
        action="policy.renewed",
        target_type=TARGET_TYPE,
        target_id=str(locked.pk),
        summary="Policy record renewed.",
    )
    record_audit_event(
        actor=actor,
        action="policy.created",
        target_type=TARGET_TYPE,
        target_id=str(new_policy.pk),
        summary="Policy record created.",
    )
    return RenewPolicyResult(policy=new_policy, created=True)
