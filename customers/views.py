"""Server-rendered customer management views."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from customers.forms import CustomerForm
from customers.models import Customer
from customers.services import (
    archive_customer,
    create_customer,
    restore_customer,
    update_customer,
)


class CustomerAccessMixin(LoginRequiredMixin, PermissionRequiredMixin):
    """Require login (redirect) and permission (403 when authenticated)."""

    # Do not set raise_exception=True: AccessMixin already returns 403 for
    # authenticated users lacking permission, while anonymous users redirect.

class CustomerListView(CustomerAccessMixin, ListView):
    model = Customer
    permission_required = "customers.view_customer"
    template_name = "customers/customer_list.html"
    context_object_name = "customers"
    paginate_by = 25

    STATUS_ACTIVE = "active"
    STATUS_ARCHIVED = "archived"
    STATUS_ALL = "all"

    def get_queryset(self) -> QuerySet[Customer]:
        qs = Customer.objects.all()
        status = self.request.GET.get("status", self.STATUS_ACTIVE)
        if status == self.STATUS_ACTIVE:
            qs = qs.filter(is_archived=False)
        elif status == self.STATUS_ARCHIVED:
            qs = qs.filter(is_archived=True)
        # STATUS_ALL and unknown values that fall through: show all for "all";
        # for unknown, default to active behavior is safer — treat unknown as active.
        elif status != self.STATUS_ALL:
            qs = qs.filter(is_archived=False)

        customer_type = self.request.GET.get("customer_type", "").strip()
        if customer_type in Customer.CustomerType.values:
            qs = qs.filter(customer_type=customer_type)

        query = self.request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(
                Q(display_name__icontains=query)
                | Q(email__icontains=query)
                | Q(phone__icontains=query)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        status = params.get("status", self.STATUS_ACTIVE)
        if status not in {
            self.STATUS_ACTIVE,
            self.STATUS_ARCHIVED,
            self.STATUS_ALL,
        }:
            status = self.STATUS_ACTIVE
        context["status"] = status
        context["customer_type"] = params.get("customer_type", "")
        context["q"] = params.get("q", "")
        context["customer_type_choices"] = Customer.CustomerType.choices
        query_params = params.copy()
        query_params.pop("page", None)
        context["filter_query"] = query_params.urlencode()
        return context


class CustomerDetailView(CustomerAccessMixin, DetailView):
    model = Customer
    permission_required = "customers.view_customer"
    template_name = "customers/customer_detail.html"
    context_object_name = "customer"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.has_perm("policies.view_policy"):
            from policies.presenters import policies_for_customer, status_label_pl

            policies = list(policies_for_customer(self.object.pk))
            for policy in policies:
                policy.status_label_pl = status_label_pl(policy.status)
            context["customer_policies"] = policies
            context["show_customer_policies"] = True
        else:
            context["show_customer_policies"] = False
        return context


class CustomerCreateView(CustomerAccessMixin, CreateView):
    model = Customer
    form_class = CustomerForm
    permission_required = "customers.add_customer"
    template_name = "customers/customer_form.html"
    success_url = reverse_lazy("customers:list")

    def form_valid(self, form: CustomerForm) -> HttpResponse:
        customer = create_customer(actor=self.request.user, **form.cleaned_data)
        messages.success(self.request, "Klient został utworzony.")
        return redirect("customers:detail", pk=customer.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Nowy klient"
        context["submit_label"] = "Utwórz klienta"
        return context


class CustomerUpdateView(CustomerAccessMixin, UpdateView):
    model = Customer
    form_class = CustomerForm
    permission_required = "customers.change_customer"
    template_name = "customers/customer_form.html"
    context_object_name = "customer"

    def form_valid(self, form: CustomerForm) -> HttpResponse:
        customer = update_customer(
            actor=self.request.user,
            customer=self.object,
            **form.cleaned_data,
        )
        messages.success(self.request, "Dane klienta zostały zapisane.")
        return redirect("customers:detail", pk=customer.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edycja klienta"
        context["submit_label"] = "Zapisz zmiany"
        return context


class CustomerArchiveView(CustomerAccessMixin, View):
    permission_required = "customers.change_customer"
    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        customer = get_object_or_404(Customer, pk=pk)
        customer, changed = archive_customer(actor=request.user, customer=customer)
        if changed:
            messages.success(request, "Klient został zarchiwizowany.")
        else:
            messages.info(request, "Klient był już zarchiwizowany.")
        return redirect("customers:detail", pk=customer.pk)


class CustomerRestoreView(CustomerAccessMixin, View):
    permission_required = "customers.change_customer"
    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        customer = get_object_or_404(Customer, pk=pk)
        customer, changed = restore_customer(actor=request.user, customer=customer)
        if changed:
            messages.success(request, "Klient został przywrócony.")
        else:
            messages.info(request, "Klient był już aktywny.")
        return redirect("customers:detail", pk=customer.pk)
