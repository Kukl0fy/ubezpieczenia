"""Server-rendered policy management views."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import Prefetch, Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from insurers.models import InsuranceType, Insurer
from policies.forms import PolicyForm
from policies.models import Policy, PolicyObject, PolicyParty
from policies.presenters import (
    COMPLEX_POLICYHOLDERS_MESSAGE,
    days_until_end,
    list_term_note,
    local_today,
    object_type_label_pl,
    policies_for_list,
    policy_display_state,
    primary_policyholder,
    role_label_pl,
    status_label_pl,
)
from policies.services import cancel_policy, create_policy, update_policy


class PolicyAccessMixin(LoginRequiredMixin, PermissionRequiredMixin):
    """Require login (redirect) and permission (403 when authenticated)."""


class PolicyListView(PolicyAccessMixin, ListView):
    model = Policy
    permission_required = "policies.view_policy"
    template_name = "policies/policy_list.html"
    context_object_name = "policies"
    paginate_by = 25

    def get_queryset(self) -> QuerySet[Policy]:
        qs = policies_for_list()
        status = self.request.GET.get("status", "").strip()
        if status in Policy.Status.values:
            qs = qs.filter(status=status)

        insurer_id = self.request.GET.get("insurer", "").strip()
        if insurer_id.isdigit():
            qs = qs.filter(insurer_id=int(insurer_id))

        insurance_type_id = self.request.GET.get("insurance_type", "").strip()
        if insurance_type_id.isdigit():
            qs = qs.filter(insurance_type_id=int(insurance_type_id))

        query = self.request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(
                Q(policy_number__icontains=query)
                | Q(insurer__name__icontains=query)
                | Q(parties__customer__display_name__icontains=query)
            ).distinct()
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        context["q"] = params.get("q", "")
        context["status"] = params.get("status", "")
        context["insurer"] = params.get("insurer", "")
        context["insurance_type"] = params.get("insurance_type", "")
        context["status_choices"] = [
            (value, status_label_pl(value)) for value, _label in Policy.Status.choices
        ]
        context["insurers"] = Insurer.objects.order_by("name", "id")
        context["insurance_types"] = InsuranceType.objects.order_by("name", "id")
        query_params = params.copy()
        query_params.pop("page", None)
        context["filter_query"] = query_params.urlencode()
        context["today"] = local_today()
        for policy in context["policies"]:
            policy.primary_customer = primary_policyholder(policy)
            display_state = policy_display_state(policy, today=context["today"])
            policy.display_state = display_state
            policy.status_label_pl = status_label_pl(policy.status)
            policy.term_note = list_term_note(display_state)
        return context


class PolicyDetailView(PolicyAccessMixin, DetailView):
    model = Policy
    permission_required = "policies.view_policy"
    template_name = "policies/policy_detail.html"
    context_object_name = "policy"

    def get_queryset(self) -> QuerySet[Policy]:
        return (
            Policy.objects.select_related(
                "insurer",
                "insurance_type",
                "previous_policy",
                "previous_policy__insurer",
            )
            .prefetch_related(
                Prefetch(
                    "parties",
                    queryset=PolicyParty.objects.select_related("customer").order_by(
                        "role", "id"
                    ),
                ),
                Prefetch(
                    "policy_objects",
                    queryset=PolicyObject.objects.select_related("insured_object"),
                ),
                "renewal_policies",
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        policy = context["policy"]
        today = local_today()
        context["today"] = today
        context["display_state"] = policy_display_state(policy, today=today)
        context["primary_customer"] = primary_policyholder(policy)
        context["days_remaining"] = days_until_end(policy.coverage_end, today=today)
        context["days_remaining_abs"] = abs(context["days_remaining"])
        context["status_label_pl"] = status_label_pl(policy.status)
        context["renewal_policy"] = policy.renewal_policies.order_by("id").first()
        for party in policy.parties.all():
            party.role_label_pl = role_label_pl(party.role)
        for link in policy.policy_objects.all():
            link.object_type_label_pl = object_type_label_pl(
                link.insured_object.object_type
            )
        return context


class PolicyCreateView(PolicyAccessMixin, CreateView):
    model = Policy
    form_class = PolicyForm
    permission_required = "policies.add_policy"
    template_name = "policies/policy_form.html"

    def form_valid(self, form: PolicyForm) -> HttpResponse:
        data = form.cleaned_data
        policy = create_policy(
            actor=self.request.user,
            primary_customer=data["primary_customer"],
            policy_number=data["policy_number"],
            insurer=data["insurer"],
            insurance_type=data["insurance_type"],
            coverage_start=data["coverage_start"],
            coverage_end=data["coverage_end"],
            premium=data.get("premium"),
            currency=data["currency"],
            notes=data.get("notes") or "",
        )
        messages.success(self.request, "Polisa została utworzona.")
        return redirect("policies:detail", pk=policy.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Nowa polisa"
        context["submit_label"] = "Utwórz polisę"
        return context


class PolicyUpdateView(PolicyAccessMixin, UpdateView):
    model = Policy
    form_class = PolicyForm
    permission_required = "policies.change_policy"
    template_name = "policies/policy_form.html"
    context_object_name = "policy"

    def get_queryset(self) -> QuerySet[Policy]:
        return (
            Policy.objects.select_related("insurer", "insurance_type")
            .prefetch_related("parties")
        )

    def form_valid(self, form: PolicyForm) -> HttpResponse:
        data = form.cleaned_data
        result = update_policy(
            actor=self.request.user,
            policy=self.object,
            primary_customer=data["primary_customer"],
            policy_number=data["policy_number"],
            insurer=data["insurer"],
            insurance_type=data["insurance_type"],
            coverage_start=data["coverage_start"],
            coverage_end=data["coverage_end"],
            premium=data.get("premium"),
            currency=data["currency"],
            notes=data.get("notes") or "",
        )
        messages.success(self.request, "Dane polisy zostały zapisane.")
        warning = result.warning
        if warning is None and getattr(form, "complex_policyholders", False):
            posted = self.request.POST.get("primary_customer")
            first_holder = (
                self.object.parties.filter(role=PolicyParty.Role.POLICYHOLDER)
                .order_by("id")
                .first()
            )
            if (
                posted
                and first_holder is not None
                and str(posted) != str(first_holder.customer_id)
            ):
                warning = COMPLEX_POLICYHOLDERS_MESSAGE
        if warning:
            messages.warning(self.request, warning)
        return redirect("policies:detail", pk=result.policy.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edycja polisy"
        context["submit_label"] = "Zapisz zmiany"
        return context


class PolicyCancelView(PolicyAccessMixin, View):
    permission_required = "policies.change_policy"
    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        policy = get_object_or_404(Policy, pk=pk)
        try:
            policy, changed = cancel_policy(actor=request.user, policy=policy)
        except ValidationError as exc:
            message = "; ".join(str(item) for item in exc.messages)
            messages.error(request, message)
            return redirect("policies:detail", pk=pk)
        if changed:
            messages.success(request, "Polisa została anulowana.")
        else:
            messages.info(request, "Polisa była już anulowana.")
        return redirect("policies:detail", pk=policy.pk)
