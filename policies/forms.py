"""Forms for the office policy management UI."""

from __future__ import annotations

from django import forms
from django.db.models import Q, QuerySet

from customers.models import Customer
from insurers.models import InsuranceType, Insurer
from policies.models import Policy, PolicyParty
from policies.presenters import COMPLEX_POLICYHOLDERS_MESSAGE


def _active_customers_including(pk: int | None) -> QuerySet[Customer]:
    qs = Customer.objects.filter(is_archived=False)
    if pk is not None:
        qs = Customer.objects.filter(Q(is_archived=False) | Q(pk=pk))
    return qs.order_by("display_name", "id")


def _active_named_including(model, pk: int | None):
    qs = model.objects.filter(is_active=True)
    if pk is not None:
        qs = model.objects.filter(Q(is_active=True) | Q(pk=pk))
    return qs.order_by("name", "id")


class PolicyForm(forms.ModelForm):
    """Create/edit form for core policy fields plus primary customer."""

    primary_customer = forms.ModelChoiceField(
        label="Główny klient",
        queryset=Customer.objects.none(),
    )

    class Meta:
        model = Policy
        fields = (
            "policy_number",
            "insurer",
            "insurance_type",
            "coverage_start",
            "coverage_end",
            "premium",
            "currency",
            "notes",
        )
        labels = {
            "policy_number": "Numer polisy",
            "insurer": "Ubezpieczyciel",
            "insurance_type": "Rodzaj ubezpieczenia",
            "coverage_start": "Początek ochrony",
            "coverage_end": "Koniec ochrony",
            "premium": "Składka",
            "currency": "Waluta",
            "notes": "Notatki",
        }
        widgets = {
            "coverage_start": forms.DateInput(attrs={"type": "date"}),
            "coverage_end": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
        error_messages = {
            "policy_number": {
                "required": "Podaj numer polisy.",
            },
            "coverage_start": {
                "required": "Podaj datę rozpoczęcia ochrony.",
                "invalid": "Podaj poprawną datę rozpoczęcia.",
            },
            "coverage_end": {
                "required": "Podaj datę zakończenia ochrony.",
                "invalid": "Podaj poprawną datę zakończenia.",
            },
            "premium": {
                "invalid": "Podaj poprawną kwotę składki.",
            },
        }

    def __init__(self, *args, instance: Policy | None = None, **kwargs):
        super().__init__(*args, instance=instance, **kwargs)

        holder_customer_id = None
        self.complex_policyholders = False
        if instance is not None:
            holders = list(
                instance.parties.filter(role=PolicyParty.Role.POLICYHOLDER).order_by(
                    "id"
                )
            )
            self.complex_policyholders = len(holders) > 1
            if holders:
                holder_customer_id = holders[0].customer_id
                self.fields["primary_customer"].initial = holder_customer_id

        self.fields["primary_customer"].queryset = _active_customers_including(
            holder_customer_id
        )
        self.fields["insurer"].queryset = _active_named_including(
            Insurer,
            instance.insurer_id if instance is not None else None,
        )
        self.fields["insurance_type"].queryset = _active_named_including(
            InsuranceType,
            instance.insurance_type_id if instance is not None else None,
        )
        self.fields["insurer"].empty_label = "Wybierz ubezpieczyciela"
        self.fields["insurance_type"].empty_label = "Wybierz rodzaj"
        self.fields["primary_customer"].empty_label = "Wybierz klienta"
        self.fields["premium"].required = False
        self.fields["notes"].required = False

        if self.complex_policyholders:
            self.fields["primary_customer"].disabled = True
            self.fields["primary_customer"].help_text = COMPLEX_POLICYHOLDERS_MESSAGE

    def clean_policy_number(self) -> str:
        value = (self.cleaned_data.get("policy_number") or "").strip()
        if not value:
            raise forms.ValidationError("Numer polisy nie może być pusty.")
        return value

    def clean_currency(self) -> str:
        value = (self.cleaned_data.get("currency") or "").strip().upper()
        if len(value) != 3 or not value.isascii() or not value.isalpha():
            raise forms.ValidationError(
                "Waluta musi składać się z trzech liter ASCII."
            )
        return value

    def clean_notes(self) -> str:
        return (self.cleaned_data.get("notes") or "").strip()

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("coverage_start")
        end = cleaned.get("coverage_end")
        if start is not None and end is not None and end < start:
            self.add_error(
                "coverage_end",
                "Data końca ochrony nie może poprzedzać daty początku.",
            )
        premium = cleaned.get("premium")
        if premium is not None and premium < 0:
            self.add_error("premium", "Składka nie może być ujemna.")
        return cleaned


class PolicyRenewalForm(forms.ModelForm):
    """Renewal form without primary-customer editing; parties are copied."""

    class Meta:
        model = Policy
        fields = (
            "policy_number",
            "insurer",
            "insurance_type",
            "coverage_start",
            "coverage_end",
            "premium",
            "currency",
            "notes",
        )
        labels = {
            "policy_number": "Numer nowej polisy",
            "insurer": "Ubezpieczyciel",
            "insurance_type": "Rodzaj ubezpieczenia",
            "coverage_start": "Początek ochrony",
            "coverage_end": "Koniec ochrony",
            "premium": "Składka",
            "currency": "Waluta",
            "notes": "Notatki",
        }
        widgets = {
            "coverage_start": forms.DateInput(attrs={"type": "date"}),
            "coverage_end": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
        error_messages = {
            "policy_number": {
                "required": "Podaj numer nowej polisy.",
            },
            "coverage_start": {
                "required": "Podaj datę rozpoczęcia ochrony.",
                "invalid": "Podaj poprawną datę rozpoczęcia.",
            },
            "coverage_end": {
                "required": "Podaj datę zakończenia ochrony.",
                "invalid": "Podaj poprawną datę zakończenia.",
            },
            "premium": {
                "invalid": "Podaj poprawną kwotę składki.",
            },
        }

    def __init__(self, *args, source_policy: Policy | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.source_policy = source_policy
        insurer_id = source_policy.insurer_id if source_policy else None
        type_id = source_policy.insurance_type_id if source_policy else None
        self.fields["insurer"].queryset = _active_named_including(Insurer, insurer_id)
        self.fields["insurance_type"].queryset = _active_named_including(
            InsuranceType, type_id
        )
        self.fields["insurer"].empty_label = "Wybierz ubezpieczyciela"
        self.fields["insurance_type"].empty_label = "Wybierz rodzaj"
        self.fields["premium"].required = False
        self.fields["notes"].required = False
        self.fields["policy_number"].required = True

        if source_policy is not None and not self.is_bound:
            from policies.presenters import default_renewal_dates

            new_start, new_end = default_renewal_dates(source_policy)
            self.fields["policy_number"].initial = ""
            self.fields["insurer"].initial = source_policy.insurer_id
            self.fields["insurance_type"].initial = source_policy.insurance_type_id
            self.fields["coverage_start"].initial = new_start
            self.fields["coverage_end"].initial = new_end
            self.fields["premium"].initial = source_policy.premium
            self.fields["currency"].initial = source_policy.currency
            self.fields["notes"].initial = source_policy.notes

    def clean_policy_number(self) -> str:
        value = (self.cleaned_data.get("policy_number") or "").strip()
        if not value:
            raise forms.ValidationError("Numer nowej polisy nie może być pusty.")
        return value

    def clean_currency(self) -> str:
        value = (self.cleaned_data.get("currency") or "").strip().upper()
        if len(value) != 3 or not value.isascii() or not value.isalpha():
            raise forms.ValidationError(
                "Waluta musi składać się z trzech liter ASCII."
            )
        return value

    def clean_notes(self) -> str:
        return (self.cleaned_data.get("notes") or "").strip()

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("coverage_start")
        end = cleaned.get("coverage_end")
        if start is not None and end is not None and end < start:
            self.add_error(
                "coverage_end",
                "Data końca ochrony nie może poprzedzać daty początku.",
            )
        premium = cleaned.get("premium")
        if premium is not None and premium < 0:
            self.add_error("premium", "Składka nie może być ujemna.")
        return cleaned
