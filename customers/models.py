"""Office customer register (persons and companies)."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


class Customer(models.Model):
    """A person or company/organization served by the office."""

    class CustomerType(models.TextChoices):
        PERSON = "PERSON", _("Person")
        COMPANY = "COMPANY", _("Company")

    customer_type = models.CharField(
        _("customer type"),
        max_length=16,
        choices=CustomerType.choices,
    )
    display_name = models.CharField(_("display name"), max_length=255)
    email = models.EmailField(_("email"), blank=True)
    phone = models.CharField(_("phone"), max_length=50, blank=True)
    is_archived = models.BooleanField(_("archived"), default=False)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("customer")
        verbose_name_plural = _("customers")
        ordering = ["display_name", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    customer_type__in=[
                        "PERSON",
                        "COMPANY",
                    ]
                ),
                name="customers_customer_type_valid",
            ),
        ]

    def __str__(self) -> str:
        return self.display_name

    def save(self, *args, **kwargs):
        if self.display_name is not None:
            self.display_name = self.display_name.strip()
        if self.email is not None:
            self.email = self.email.strip()
        if self.phone is not None:
            self.phone = self.phone.strip()
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        normalized_name = (self.display_name or "").strip()
        if not normalized_name:
            raise ValidationError({"display_name": _("Display name cannot be blank.")})
        self.display_name = normalized_name
        self.email = (self.email or "").strip()
        self.phone = (self.phone or "").strip()
