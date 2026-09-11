"""Presentation helpers for policy dates and dashboard buckets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from django.db.models import Prefetch, QuerySet
from django.utils import timezone

from policies.models import Policy, PolicyParty


@dataclass(frozen=True)
class PolicyDisplayState:
    code: str
    label: str


STATUS_LABELS_PL = {
    Policy.Status.DRAFT: "Szkic",
    Policy.Status.ACTIVE: "Aktywna",
    Policy.Status.EXPIRED: "Wygasła",
    Policy.Status.RENEWED: "Odnowiona",
    Policy.Status.CANCELLED: "Anulowana",
}


def status_label_pl(status: str) -> str:
    return STATUS_LABELS_PL.get(status, status)


def local_today() -> date:
    return timezone.localdate()


def days_until_end(coverage_end: date, *, today: date | None = None) -> int:
    current = today or local_today()
    return (coverage_end - current).days


def policy_display_state(
    policy: Policy,
    *,
    today: date | None = None,
) -> PolicyDisplayState:
    """Derive a human-readable state without persisting a new status."""
    current = today or local_today()
    if policy.status == Policy.Status.CANCELLED:
        return PolicyDisplayState("cancelled", "Anulowana")
    if policy.status == Policy.Status.RENEWED:
        return PolicyDisplayState("renewed", "Odnowiona")
    if policy.status == Policy.Status.DRAFT:
        return PolicyDisplayState("draft", "Szkic")

    remaining = days_until_end(policy.coverage_end, today=current)
    if remaining < 0:
        return PolicyDisplayState("overdue", "Termin minął")
    if remaining <= 7:
        return PolicyDisplayState("expiring_soon", "Kończy się wkrótce")
    if policy.status == Policy.Status.EXPIRED:
        return PolicyDisplayState("expired", "Wygasła")
    return PolicyDisplayState("active", "Aktywna")


def primary_policyholder(policy: Policy):
    for party in policy.parties.all():
        if party.role == PolicyParty.Role.POLICYHOLDER:
            return party.customer
    parties = list(policy.parties.all())
    if parties:
        return parties[0].customer
    return None


def policies_for_list() -> QuerySet[Policy]:
    return (
        Policy.objects.select_related("insurer", "insurance_type")
        .prefetch_related(
            Prefetch(
                "parties",
                queryset=PolicyParty.objects.select_related("customer").order_by(
                    "id"
                ),
            )
        )
        .order_by("coverage_end", "id")
    )


def actionable_active_policies() -> QuerySet[Policy]:
    """ACTIVE policies that should appear on the expiry dashboard."""
    return policies_for_list().filter(status=Policy.Status.ACTIVE)


def dashboard_expiry_buckets(*, today: date | None = None) -> dict[str, list[Policy]]:
    current = today or local_today()
    end_7 = current + timedelta(days=7)
    end_30 = current + timedelta(days=30)
    policies = list(actionable_active_policies())

    overdue: list[Policy] = []
    within_7: list[Policy] = []
    within_30: list[Policy] = []
    for policy in policies:
        if policy.coverage_end < current:
            overdue.append(policy)
        elif policy.coverage_end <= end_7:
            within_7.append(policy)
        elif policy.coverage_end <= end_30:
            within_30.append(policy)
    return {
        "overdue": overdue,
        "within_7": within_7,
        "within_30": within_30,
        "today": current,
    }


def policies_for_customer(customer_id: int) -> QuerySet[Policy]:
    return (
        policies_for_list()
        .filter(parties__customer_id=customer_id)
        .distinct()
    )
