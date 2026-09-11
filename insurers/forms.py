"""Forms for the office insurance settings UI."""

from __future__ import annotations

from django import forms

from insurers.models import InsuranceType, Insurer

DUPLICATE_NAME_MESSAGE = "Pozycja o tej nazwie już istnieje."
BLANK_NAME_MESSAGE = "Nazwa nie może być pusta."


def _name_taken(*, model, name: str, exclude_pk: int | None = None) -> bool:
    normalized = (name or "").strip()
    qs = model.objects.filter(name__iexact=normalized)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()

class InsurerForm(forms.ModelForm):
    """Create/edit form for insurance companies (no is_active field)."""

    website = forms.URLField(
        label="Strona internetowa",
        required=False,
        assume_scheme="https",
        error_messages={
            "invalid": "Podaj poprawny adres strony internetowej.",
        },
    )

    class Meta:
        model = Insurer
        fields = ("name", "contact_phone", "contact_email", "website")
        labels = {
            "name": "Nazwa",
            "contact_phone": "Telefon kontaktowy",
            "contact_email": "E-mail kontaktowy",
            "website": "Strona internetowa",
        }
        error_messages = {
            "name": {
                "required": "Podaj nazwę.",
            },
            "contact_email": {
                "invalid": "Podaj poprawny adres e-mail.",
            },
        }

    def clean_name(self) -> str:
        value = (self.cleaned_data.get("name") or "").strip()
        if not value:
            raise forms.ValidationError(BLANK_NAME_MESSAGE)
        exclude_pk = self.instance.pk if self.instance and self.instance.pk else None
        if _name_taken(model=Insurer, name=value, exclude_pk=exclude_pk):
            raise forms.ValidationError(DUPLICATE_NAME_MESSAGE)
        return value

    def clean_contact_phone(self) -> str:
        return (self.cleaned_data.get("contact_phone") or "").strip()

    def clean_contact_email(self) -> str:
        return (self.cleaned_data.get("contact_email") or "").strip()

    def clean_website(self) -> str:
        return (self.cleaned_data.get("website") or "").strip()


class InsuranceTypeForm(forms.ModelForm):
    """Create/edit form for insurance types (no is_active field)."""

    class Meta:
        model = InsuranceType
        fields = ("name", "description")
        labels = {
            "name": "Nazwa",
            "description": "Opis",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }
        error_messages = {
            "name": {
                "required": "Podaj nazwę.",
            },
        }

    def clean_name(self) -> str:
        value = (self.cleaned_data.get("name") or "").strip()
        if not value:
            raise forms.ValidationError(BLANK_NAME_MESSAGE)
        exclude_pk = self.instance.pk if self.instance and self.instance.pk else None
        if _name_taken(model=InsuranceType, name=value, exclude_pk=exclude_pk):
            raise forms.ValidationError(DUPLICATE_NAME_MESSAGE)
        return value

    def clean_description(self) -> str:
        return (self.cleaned_data.get("description") or "").strip()
