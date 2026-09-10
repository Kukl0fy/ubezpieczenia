"""Controlled dictionaries for insurers and insurance types."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _


class NamedDictionaryModel(models.Model):
    """Shared rules for controlled dictionary entries."""

    name = models.CharField(_("name"), max_length=255)
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        abstract = True
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if self.name is not None:
            self.name = self.name.strip()
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        normalized = (self.name or "").strip()
        if not normalized:
            raise ValidationError({"name": _("Name cannot be blank.")})
        self.name = normalized


class Insurer(NamedDictionaryModel):
    """Insurance company dictionary entry."""

    contact_email = models.EmailField(_("contact email"), blank=True)
    contact_phone = models.CharField(_("contact phone"), max_length=50, blank=True)
    website = models.URLField(_("website"), blank=True)

    class Meta(NamedDictionaryModel.Meta):
        verbose_name = _("insurer")
        verbose_name_plural = _("insurers")
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                name="insurers_insurer_name_ci_uniq",
            ),
        ]


class InsuranceType(NamedDictionaryModel):
    """Insurance type dictionary entry."""

    description = models.TextField(_("description"), blank=True)

    class Meta(NamedDictionaryModel.Meta):
        verbose_name = _("insurance type")
        verbose_name_plural = _("insurance types")
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                name="insurers_insurancetype_name_ci_uniq",
            ),
        ]
