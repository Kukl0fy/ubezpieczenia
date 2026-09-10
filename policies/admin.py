"""Django Admin for the policy domain (history-preserving, no hard delete)."""

from __future__ import annotations

from django.contrib import admin

from policies.models import InsuredObject, Policy, PolicyObject, PolicyParty


class PolicyPartyInline(admin.TabularInline):
    model = PolicyParty
    extra = 0
    autocomplete_fields = ("customer",)
    readonly_fields = ("created_at",)


class PolicyObjectInline(admin.TabularInline):
    model = PolicyObject
    extra = 0
    autocomplete_fields = ("insured_object",)
    readonly_fields = ("created_at",)


@admin.register(Policy)
class PolicyAdmin(admin.ModelAdmin):
    list_display = (
        "policy_number",
        "insurer",
        "insurance_type",
        "coverage_start",
        "coverage_end",
        "status",
        "premium",
        "currency",
        "updated_at",
    )
    list_filter = (
        "status",
        "insurer",
        "insurance_type",
        "coverage_start",
        "coverage_end",
    )
    search_fields = (
        "policy_number",
        "parties__customer__display_name",
        "insurer__name",
    )
    ordering = ("coverage_end", "id")
    autocomplete_fields = (
        "insurer",
        "insurance_type",
        "previous_policy",
    )
    readonly_fields = ("created_at", "updated_at")
    inlines = (PolicyPartyInline, PolicyObjectInline)
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "policy_number",
                    "status",
                    "insurer",
                    "insurance_type",
                    "previous_policy",
                )
            },
        ),
        (
            "Coverage",
            {"fields": ("coverage_start", "coverage_end")},
        ),
        (
            "Premium",
            {"fields": ("premium", "currency", "notes")},
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


@admin.register(InsuredObject)
class InsuredObjectAdmin(admin.ModelAdmin):
    list_display = (
        "label",
        "object_type",
        "is_archived",
        "updated_at",
    )
    list_filter = ("object_type", "is_archived")
    search_fields = ("label", "description")
    ordering = ("label", "id")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            None,
            {"fields": ("object_type", "label", "description", "is_archived")},
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
