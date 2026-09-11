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

ROLE_LABELS_PL = {
    PolicyParty.Role.POLICYHOLDER: "Ubezpieczający",
    PolicyParty.Role.INSURED: "Ubezpieczony",
    PolicyParty.Role.PAYER: "Płatnik",
}

OBJECT_TYPE_LABELS_PL = {
    "PROPERTY": "Nieruchomość",
    "VEHICLE": "Pojazd",
    "PERSON": "Osoba",
    "COMPANY": "Firma",
    "OTHER": "Inny",
}

COMPLEX_POLICYHOLDERS_MESSAGE = (
    "Ta polisa ma więcej niż jednego ubezpieczającego. "
    "Pozostałe dane można zapisać tutaj, ale zestaw stron polisy "
    "zarządzaj w Django Admin."
)

RENEWED_CANCEL_BLOCKED_MESSAGE = (
    "Polisy odnowionej nie można anulować w tym workflow."
)

RENEWAL_NOT_ALLOWED_MESSAGE = (
    "Tej polisy nie można odnowić w obecnym statusie."
)

RENEWAL_ALREADY_EXISTS_MESSAGE = (
    "Ta polisa ma już odnowienie. Otwarto istniejącą polisę odnawiającą."
)

RENEWABLE_STATUSES = frozenset(
    {
        Policy.Status.ACTIVE,
        Policy.Status.EXPIRED,
    }
)


def can_show_renew_button(*, policy: Policy, user, renewal_policy=None) -> bool:
    """Whether the detail page should offer creating a renewal."""
    if not (
        user.has_perm("policies.view_policy")
        and user.has_perm("policies.add_policy")
        and user.has_perm("policies.change_policy")
    ):
        return False
    if policy.status not in RENEWABLE_STATUSES:
        return False
    if renewal_policy is not None:
        return False
    return True


def default_renewal_dates(source: Policy) -> tuple[date, date]:
    """Suggest coverage dates for a renewal of ``source``."""
    new_start = source.coverage_end + timedelta(days=1)
    span_days = (source.coverage_end - source.coverage_start).days
    new_end = new_start + timedelta(days=span_days)
    return new_start, new_end


def status_label_pl(status: str) -> str:
    return STATUS_LABELS_PL.get(status, status)


def role_label_pl(role: str) -> str:
    return ROLE_LABELS_PL.get(role, role)


def object_type_label_pl(object_type: str) -> str:
    return OBJECT_TYPE_LABELS_PL.get(object_type, object_type)


def list_term_note(display_state: PolicyDisplayState) -> str | None:
    """Extra term hint for lists; omit when it only repeats the status label."""
    if display_state.code in {"overdue", "expiring_soon"}:
        return display_state.label
    return None


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


def policyholder_count(policy: Policy) -> int:
    return sum(
        1
        for party in policy.parties.all()
        if party.role == PolicyParty.Role.POLICYHOLDER
    )


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
