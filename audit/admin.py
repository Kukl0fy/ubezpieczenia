"""Read-only Django Admin for append-only audit events."""

from __future__ import annotations

from django.contrib import admin

from audit.models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = (
        "occurred_at",
        "action",
        "actor",
        "target_type",
        "target_id",
        "summary",
    )
    list_filter = ("action", "target_type", "occurred_at")
    search_fields = ("action", "target_type", "target_id", "summary")
    list_select_related = ("actor",)
    ordering = ("-occurred_at", "-id")
    readonly_fields = (
        "actor",
        "action",
        "target_type",
        "target_id",
        "summary",
        "occurred_at",
    )

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions
