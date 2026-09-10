"""Authentication signal receivers that record security audit events."""

from __future__ import annotations

from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.dispatch import receiver

from audit.services import record_audit_event


@receiver(user_logged_in)
def record_login_succeeded(sender, request, user, **kwargs):
    record_audit_event(
        actor=user,
        action="auth.login_succeeded",
        target_type="accounts.user",
        target_id=str(user.pk),
        summary="User signed in successfully.",
    )


@receiver(user_login_failed)
def record_login_failed(sender, credentials, request, **kwargs):
    # Do not record submitted username, password, IP, or other credentials.
    record_audit_event(
        actor=None,
        action="auth.login_failed",
        target_type="authentication",
        target_id="",
        summary="Authentication attempt failed.",
    )


@receiver(user_logged_out)
def record_logout(sender, request, user, **kwargs):
    actor = None
    target_id = ""
    if user is not None and getattr(user, "pk", None) is not None:
        actor = user
        target_id = str(user.pk)
    record_audit_event(
        actor=actor,
        action="auth.logout",
        target_type="accounts.user",
        target_id=target_id,
        summary="User signed out.",
    )
