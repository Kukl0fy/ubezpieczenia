"""Django Admin for insurer dictionaries (deactivate instead of delete)."""

from __future__ import annotations

from django.contrib import admin

from insurers.models import InsuranceType, Insurer


class DictionaryAdmin(admin.ModelAdmin):
    """Shared admin behaviour for controlled dictionaries."""

    list_display = ("name", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name",)
    ordering = ("name",)
    readonly_fields = ("created_at", "updated_at")

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions


@admin.register(Insurer)
class InsurerAdmin(DictionaryAdmin):
    list_display = (
        "name",
        "contact_email",
        "contact_phone",
        "is_active",
        "updated_at",
    )
    fieldsets = (
        (None, {"fields": ("name", "is_active")}),
        (
            "Contact",
            {"fields": ("contact_email", "contact_phone", "website")},
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at")},
        ),
    )


@admin.register(InsuranceType)
class InsuranceTypeAdmin(DictionaryAdmin):
    list_display = ("name", "is_active", "updated_at")
    fieldsets = (
        (None, {"fields": ("name", "description", "is_active")}),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at")},
        ),
    )
