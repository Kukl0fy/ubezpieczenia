"""Django Admin for the customer register (archive instead of delete)."""

from __future__ import annotations

from django.contrib import admin

from customers.models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        "display_name",
        "customer_type",
        "email",
        "phone",
        "is_archived",
        "updated_at",
    )
    list_filter = ("customer_type", "is_archived")
    search_fields = ("display_name", "email", "phone")
    ordering = ("display_name", "id")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "customer_type",
                    "display_name",
                    "is_archived",
                )
            },
        ),
        (
            "Contact",
            {"fields": ("email", "phone")},
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at")},
        ),
    )

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions
