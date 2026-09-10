"""Policy domain models: policies, parties, and insured objects."""

from __future__ import annotations

import re
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _

CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


class Policy(models.Model):
    """Insurance policy coverage period and commercial terms."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", _("Draft")
        ACTIVE = "ACTIVE", _("Active")
        EXPIRED = "EXPIRED", _("Expired")
        RENEWED = "RENEWED", _("Renewed")
        CANCELLED = "CANCELLED", _("Cancelled")

    policy_number = models.CharField(_("policy number"), max_length=100)
    insurer = models.ForeignKey(
        "insurers.Insurer",
        on_delete=models.PROTECT,
        related_name="policies",
        verbose_name=_("insurer"),
    )
    insurance_type = models.ForeignKey(
        "insurers.InsuranceType",
        on_delete=models.PROTECT,
        related_name="policies",
        verbose_name=_("insurance type"),
    )
    coverage_start = models.DateField(_("coverage start"))
    coverage_end = models.DateField(_("coverage end"))
    status = models.CharField(
        _("status"),
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    premium = models.DecimalField(
        _("premium"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    currency = models.CharField(_("currency"), max_length=3, default="PLN")
    notes = models.CharField(_("notes"), max_length=2000, blank=True)
    previous_policy = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="renewal_policies",
        verbose_name=_("previous policy"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("policy")
        verbose_name_plural = _("policies")
        ordering = ["coverage_end", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(coverage_end__gte=F("coverage_start")),
                name="policies_policy_coverage_dates_valid",
            ),
            models.CheckConstraint(
                condition=Q(premium__isnull=True) | Q(premium__gte=0),
                name="policies_policy_premium_non_negative",
            ),
            models.CheckConstraint(
                condition=Q(
                    status__in=[
                        "DRAFT",
                        "ACTIVE",
                        "EXPIRED",
                        "RENEWED",
                        "CANCELLED",
                    ]
                ),
                name="policies_policy_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(previous_policy__isnull=True)
                | ~Q(previous_policy=F("id")),
                name="policies_policy_previous_not_self",
            ),
            models.UniqueConstraint(
                fields=["previous_policy"],
                condition=Q(previous_policy__isnull=False),
                name="policies_policy_previous_policy_uniq",
            ),
        ]

    def __str__(self) -> str:
        insurer_name = getattr(self.insurer, "name", "")
        if insurer_name:
            return f"{self.policy_number} ({insurer_name})"
        return self.policy_number

    def save(self, *args, **kwargs):
        if self.policy_number is not None:
            self.policy_number = self.policy_number.strip()
        if self.currency is not None:
            self.currency = self.currency.strip().upper()
        if self.notes is not None:
            self.notes = self.notes.strip()
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        number = (self.policy_number or "").strip()
        if not number:
            raise ValidationError(
                {"policy_number": _("Policy number cannot be blank.")}
            )
        self.policy_number = number

        currency = (self.currency or "").strip().upper()
        if not CURRENCY_RE.fullmatch(currency):
            raise ValidationError(
                {"currency": _("Currency must be a three-letter ASCII code.")}
            )
        self.currency = currency
        self.notes = (self.notes or "").strip()

        if (
            self.coverage_start is not None
            and self.coverage_end is not None
            and self.coverage_end < self.coverage_start
        ):
            raise ValidationError(
                {"coverage_end": _("Coverage end cannot precede coverage start.")}
            )

        if self.premium is not None and self.premium < Decimal("0"):
            raise ValidationError({"premium": _("Premium cannot be negative.")})

        if self.previous_policy_id is not None:
            if self.pk is not None and self.previous_policy_id == self.pk:
                raise ValidationError(
                    {"previous_policy": _("A policy cannot renew itself.")}
                )
            self._validate_no_renewal_cycle()

    def _validate_no_renewal_cycle(self) -> None:
        current = self.previous_policy
        seen: set[int] = set()
        while current is not None:
            if self.pk is not None and current.pk == self.pk:
                raise ValidationError(
                    {"previous_policy": _("Renewal would create a policy cycle.")}
                )
            if current.pk in seen:
                break
            seen.add(current.pk)
            current = current.previous_policy


class PolicyParty(models.Model):
    """A customer's role on a specific policy."""

    class Role(models.TextChoices):
        POLICYHOLDER = "POLICYHOLDER", _("Policyholder")
        INSURED = "INSURED", _("Insured")
        PAYER = "PAYER", _("Payer")

    policy = models.ForeignKey(
        Policy,
        on_delete=models.PROTECT,
        related_name="parties",
        verbose_name=_("policy"),
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,
        related_name="policy_parties",
        verbose_name=_("customer"),
    )
    role = models.CharField(_("role"), max_length=16, choices=Role.choices)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("policy party")
        verbose_name_plural = _("policy parties")
        ordering = ["policy_id", "role", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["policy", "customer", "role"],
                name="policies_policyparty_policy_customer_role_uniq",
            ),
            models.CheckConstraint(
                condition=Q(
                    role__in=[
                        "POLICYHOLDER",
                        "INSURED",
                        "PAYER",
                    ]
                ),
                name="policies_policyparty_role_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.customer} / {self.get_role_display()}"

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class InsuredObject(models.Model):
    """Person, property, vehicle, or other insured subject."""

    class ObjectType(models.TextChoices):
        PROPERTY = "PROPERTY", _("Property")
        VEHICLE = "VEHICLE", _("Vehicle")
        PERSON = "PERSON", _("Person")
        COMPANY = "COMPANY", _("Company")
        OTHER = "OTHER", _("Other")

    object_type = models.CharField(
        _("object type"),
        max_length=16,
        choices=ObjectType.choices,
    )
    label = models.CharField(_("label"), max_length=255)
    description = models.CharField(_("description"), max_length=2000, blank=True)
    is_archived = models.BooleanField(_("archived"), default=False)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("insured object")
        verbose_name_plural = _("insured objects")
        ordering = ["label", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    object_type__in=[
                        "PROPERTY",
                        "VEHICLE",
                        "PERSON",
                        "COMPANY",
                        "OTHER",
                    ]
                ),
                name="policies_insuredobject_type_valid",
            ),
        ]

    def __str__(self) -> str:
        return self.label

    def save(self, *args, **kwargs):
        if self.label is not None:
            self.label = self.label.strip()
        if self.description is not None:
            self.description = self.description.strip()
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        label = (self.label or "").strip()
        if not label:
            raise ValidationError({"label": _("Label cannot be blank.")})
        self.label = label
        self.description = (self.description or "").strip()


class PolicyObject(models.Model):
    """Links a policy to an insured object."""

    policy = models.ForeignKey(
        Policy,
        on_delete=models.PROTECT,
        related_name="policy_objects",
        verbose_name=_("policy"),
    )
    insured_object = models.ForeignKey(
        InsuredObject,
        on_delete=models.PROTECT,
        related_name="policy_links",
        verbose_name=_("insured object"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("policy object")
        verbose_name_plural = _("policy objects")
        ordering = ["policy_id", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["policy", "insured_object"],
                name="policies_policyobject_policy_object_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.policy_id}: {self.insured_object}"

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
