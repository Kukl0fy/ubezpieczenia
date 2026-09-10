"""Explicit API for recording audit events."""

from __future__ import annotations

from typing import TYPE_CHECKING

from audit.models import AuditEvent

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser


def record_audit_event(
    *,
    action: str,
    target_type: str,
    actor: AbstractBaseUser | None = None,
    target_id: str | None = None,
    summary: str = "",
) -> AuditEvent:
    """Create and persist one audit event after validation."""
    event = AuditEvent(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id or "",
        summary=summary or "",
    )
    event.save()
    return event
