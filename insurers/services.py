"""Explicit insurer dictionary write operations with audit recording."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from audit.services import record_audit_event
from insurers.forms import DUPLICATE_NAME_MESSAGE
from insurers.models import InsuranceType, Insurer

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

INSURER_TARGET = "insurers.insurer"
INSURANCE_TYPE_TARGET = "insurers.insurancetype"


def _normalized_insurer_values(
    *,
    name: str,
    contact_phone: str = "",
    contact_email: str = "",
    website: str = "",
) -> dict[str, str]:
    return {
        "name": (name or "").strip(),
        "contact_phone": (contact_phone or "").strip(),
        "contact_email": (contact_email or "").strip(),
        "website": (website or "").strip(),
    }


def _normalized_type_values(*, name: str, description: str = "") -> dict[str, str]:
    return {
        "name": (name or "").strip(),
        "description": (description or "").strip(),
    }


def _save_with_unique_guard(instance) -> None:
    try:
        with transaction.atomic():
            instance.save()
    except IntegrityError as exc:
        raise ValidationError({"name": DUPLICATE_NAME_MESSAGE}) from exc


@transaction.atomic
def create_insurer(
    *,
    actor: AbstractBaseUser,
    name: str,
    contact_phone: str = "",
    contact_email: str = "",
    website: str = "",
) -> Insurer:
    values = _normalized_insurer_values(
        name=name,
        contact_phone=contact_phone,
        contact_email=contact_email,
        website=website,
    )
    insurer = Insurer(**values)
    _save_with_unique_guard(insurer)
    record_audit_event(
        actor=actor,
        action="insurer.created",
        target_type=INSURER_TARGET,
        target_id=str(insurer.pk),
        summary="Insurer record created.",
    )
    return insurer


@transaction.atomic
def update_insurer(
    *,
    actor: AbstractBaseUser,
    insurer: Insurer,
    name: str,
    contact_phone: str = "",
    contact_email: str = "",
    website: str = "",
) -> Insurer:
    insurer.refresh_from_db()
    values = _normalized_insurer_values(
        name=name,
        contact_phone=contact_phone,
        contact_email=contact_email,
        website=website,
    )
    changed = [
        field for field, value in values.items() if getattr(insurer, field) != value
    ]
    if not changed:
        return insurer

    for field, value in values.items():
        setattr(insurer, field, value)
    _save_with_unique_guard(insurer)
    record_audit_event(
        actor=actor,
        action="insurer.updated",
        target_type=INSURER_TARGET,
        target_id=str(insurer.pk),
        summary=f"Updated fields: {', '.join(changed)}.",
    )
    return insurer


@transaction.atomic
def deactivate_insurer(
    *,
    actor: AbstractBaseUser,
    insurer: Insurer,
) -> tuple[Insurer, bool]:
    locked = Insurer.objects.select_for_update().get(pk=insurer.pk)
    if not locked.is_active:
        return locked, False
    locked.is_active = False
    locked.save(update_fields=["is_active", "updated_at"])
    record_audit_event(
        actor=actor,
        action="insurer.deactivated",
        target_type=INSURER_TARGET,
        target_id=str(locked.pk),
        summary="Insurer record deactivated.",
    )
    return locked, True


@transaction.atomic
def restore_insurer(
    *,
    actor: AbstractBaseUser,
    insurer: Insurer,
) -> tuple[Insurer, bool]:
    locked = Insurer.objects.select_for_update().get(pk=insurer.pk)
    if locked.is_active:
        return locked, False
    locked.is_active = True
    locked.save(update_fields=["is_active", "updated_at"])
    record_audit_event(
        actor=actor,
        action="insurer.restored",
        target_type=INSURER_TARGET,
        target_id=str(locked.pk),
        summary="Insurer record restored.",
    )
    return locked, True


@transaction.atomic
def create_insurance_type(
    *,
    actor: AbstractBaseUser,
    name: str,
    description: str = "",
) -> InsuranceType:
    values = _normalized_type_values(name=name, description=description)
    insurance_type = InsuranceType(**values)
    _save_with_unique_guard(insurance_type)
    record_audit_event(
        actor=actor,
        action="insurance_type.created",
        target_type=INSURANCE_TYPE_TARGET,
        target_id=str(insurance_type.pk),
        summary="Insurance type record created.",
    )
    return insurance_type


@transaction.atomic
def update_insurance_type(
    *,
    actor: AbstractBaseUser,
    insurance_type: InsuranceType,
    name: str,
    description: str = "",
) -> InsuranceType:
    insurance_type.refresh_from_db()
    values = _normalized_type_values(name=name, description=description)
    changed = [
        field
        for field, value in values.items()
        if getattr(insurance_type, field) != value
    ]
    if not changed:
        return insurance_type

    for field, value in values.items():
        setattr(insurance_type, field, value)
    _save_with_unique_guard(insurance_type)
    record_audit_event(
        actor=actor,
        action="insurance_type.updated",
        target_type=INSURANCE_TYPE_TARGET,
        target_id=str(insurance_type.pk),
        summary=f"Updated fields: {', '.join(changed)}.",
    )
    return insurance_type


@transaction.atomic
def deactivate_insurance_type(
    *,
    actor: AbstractBaseUser,
    insurance_type: InsuranceType,
) -> tuple[InsuranceType, bool]:
    locked = InsuranceType.objects.select_for_update().get(pk=insurance_type.pk)
    if not locked.is_active:
        return locked, False
    locked.is_active = False
    locked.save(update_fields=["is_active", "updated_at"])
    record_audit_event(
        actor=actor,
        action="insurance_type.deactivated",
        target_type=INSURANCE_TYPE_TARGET,
        target_id=str(locked.pk),
        summary="Insurance type record deactivated.",
    )
    return locked, True


@transaction.atomic
def restore_insurance_type(
    *,
    actor: AbstractBaseUser,
    insurance_type: InsuranceType,
) -> tuple[InsuranceType, bool]:
    locked = InsuranceType.objects.select_for_update().get(pk=insurance_type.pk)
    if locked.is_active:
        return locked, False
    locked.is_active = True
    locked.save(update_fields=["is_active", "updated_at"])
    record_audit_event(
        actor=actor,
        action="insurance_type.restored",
        target_type=INSURANCE_TYPE_TARGET,
        target_id=str(locked.pk),
        summary="Insurance type record restored.",
    )
    return locked, True
