"""Append-only audit event records."""

from __future__ import annotations

import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

ACTION_RE = re.compile(r"^[a-z][a-z0-9._-]*$")


class AuditEvent(models.Model):
    """Immutable record of a significant business or security event."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
        verbose_name=_("actor"),
    )
    action = models.CharField(_("action"), max_length=100)
    target_type = models.CharField(_("target type"), max_length=100)
    target_id = models.CharField(_("target id"), max_length=100, blank=True)
    summary = models.CharField(_("summary"), max_length=500, blank=True)
    occurred_at = models.DateTimeField(_("occurred at"), auto_now_add=True)

    class Meta:
        verbose_name = _("audit event")
        verbose_name_plural = _("audit events")
        ordering = ["-occurred_at", "-id"]
        indexes = [
            models.Index(fields=["occurred_at"], name="audit_event_occurred_at_idx"),
            models.Index(fields=["action"], name="audit_event_action_idx"),
            models.Index(
                fields=["target_type", "target_id"],
                name="audit_event_target_idx",
            ),
            models.Index(fields=["actor"], name="audit_event_actor_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.action} @ {self.occurred_at}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError(
                _("Audit events are append-only and cannot be changed.")
            )
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            _("Audit events are append-only and cannot be deleted.")
        )

    def clean(self) -> None:
        super().clean()
        action = (self.action or "").strip()
        if not action or not ACTION_RE.fullmatch(action):
            raise ValidationError(
                {
                    "action": _(
                        "Action must start with a lowercase letter and contain "
                        "only lowercase ASCII letters, digits, dots, hyphens, "
                        "or underscores."
                    )
                }
            )
        self.action = action
        self.target_type = (self.target_type or "").strip()
        if not self.target_type:
            raise ValidationError({"target_type": _("Target type cannot be blank.")})
        self.target_id = (self.target_id or "").strip()
        self.summary = (self.summary or "").strip()
