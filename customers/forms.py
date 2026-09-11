"""Forms for the office customer management UI."""

from __future__ import annotations

from django import forms

from customers.models import Customer


class CustomerForm(forms.ModelForm):
    """Create/edit form limited to contact identity fields."""

    customer_type = forms.ChoiceField(
        label="Typ klienta",
        choices=[
            (Customer.CustomerType.PERSON, "Osoba"),
            (Customer.CustomerType.COMPANY, "Firma"),
        ],
    )

    class Meta:
        model = Customer
        fields = ("customer_type", "display_name", "email", "phone")
        labels = {
            "display_name": "Nazwa wyświetlana",
            "email": "E-mail",
            "phone": "Telefon",
        }
        error_messages = {
            "display_name": {
                "required": "Podaj nazwę wyświetlaną.",
            },
            "email": {
                "invalid": "Podaj poprawny adres e-mail.",
            },
        }

    def clean_display_name(self) -> str:
        value = (self.cleaned_data.get("display_name") or "").strip()
        if not value:
            raise forms.ValidationError("Nazwa wyświetlana nie może być pusta.")
        return value

    def clean_email(self) -> str:
        return (self.cleaned_data.get("email") or "").strip()

    def clean_phone(self) -> str:
        return (self.cleaned_data.get("phone") or "").strip()
