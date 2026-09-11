"""Server-rendered office settings for insurers and insurance types."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from insurers.forms import InsuranceTypeForm, InsurerForm
from insurers.models import InsuranceType, Insurer
from insurers.services import (
    create_insurance_type,
    create_insurer,
    deactivate_insurance_type,
    deactivate_insurer,
    restore_insurance_type,
    restore_insurer,
    update_insurance_type,
    update_insurer,
)


def _apply_validation_error(form, exc: ValidationError) -> None:
    if getattr(exc, "message_dict", None):
        for field, errors in exc.message_dict.items():
            target = None if field == "__all__" else field
            for error in errors:
                form.add_error(target, error)
        return
    form.add_error(None, exc)


class InsurerAccessMixin(LoginRequiredMixin, PermissionRequiredMixin):
    """Require login (redirect) and permission (403 when authenticated)."""


class SettingsHubView(InsurerAccessMixin, TemplateView):
    template_name = "insurers/settings.html"

    def has_permission(self) -> bool:
        user = self.request.user
        return user.has_perm("insurers.view_insurer") or user.has_perm(
            "insurers.view_insurancetype"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        can_view_insurers = user.has_perm("insurers.view_insurer")
        can_view_types = user.has_perm("insurers.view_insurancetype")
        context["can_view_insurers"] = can_view_insurers
        context["can_view_types"] = can_view_types
        context["can_add_insurer"] = user.has_perm("insurers.add_insurer")
        context["can_add_type"] = user.has_perm("insurers.add_insurancetype")
        context["active_insurer_count"] = (
            Insurer.objects.filter(is_active=True).count() if can_view_insurers else 0
        )
        context["active_type_count"] = (
            InsuranceType.objects.filter(is_active=True).count()
            if can_view_types
            else 0
        )
        return context


class DictionaryListMixin:
    STATUS_ACTIVE = "active"
    STATUS_INACTIVE = "inactive"
    STATUS_ALL = "all"

    def filtered_status(self) -> str:
        status = self.request.GET.get("status", self.STATUS_ACTIVE)
        if status not in {
            self.STATUS_ACTIVE,
            self.STATUS_INACTIVE,
            self.STATUS_ALL,
        }:
            return self.STATUS_ACTIVE
        return status

    def apply_status_and_search(self, qs: QuerySet) -> QuerySet:
        status = self.filtered_status()
        if status == self.STATUS_ACTIVE:
            qs = qs.filter(is_active=True)
        elif status == self.STATUS_INACTIVE:
            qs = qs.filter(is_active=False)
        query = self.request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(name__icontains=query)
        return qs

    def list_filter_context(self) -> dict:
        params = self.request.GET.copy()
        status = self.filtered_status()
        query_params = params.copy()
        query_params.pop("page", None)
        return {
            "status": status,
            "q": params.get("q", ""),
            "filter_query": query_params.urlencode(),
        }


class InsurerListView(InsurerAccessMixin, DictionaryListMixin, ListView):
    model = Insurer
    permission_required = "insurers.view_insurer"
    template_name = "insurers/insurer_list.html"
    context_object_name = "insurers"
    paginate_by = 25

    def get_queryset(self) -> QuerySet[Insurer]:
        return self.apply_status_and_search(Insurer.objects.all())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.list_filter_context())
        return context


class InsurerCreateView(InsurerAccessMixin, CreateView):
    model = Insurer
    form_class = InsurerForm
    permission_required = "insurers.add_insurer"
    template_name = "insurers/insurer_form.html"
    success_url = reverse_lazy("insurers:insurer_list")

    def form_valid(self, form: InsurerForm) -> HttpResponse:
        try:
            create_insurer(actor=self.request.user, **form.cleaned_data)
        except ValidationError as exc:
            _apply_validation_error(form, exc)
            return self.form_invalid(form)
        messages.success(
            self.request,
            "Towarzystwo ubezpieczeniowe zostało dodane.",
        )
        return redirect(self.success_url)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Nowe towarzystwo ubezpieczeniowe"
        context["submit_label"] = "Dodaj towarzystwo"
        return context


class InsurerUpdateView(InsurerAccessMixin, UpdateView):
    model = Insurer
    form_class = InsurerForm
    permission_required = "insurers.change_insurer"
    template_name = "insurers/insurer_form.html"
    context_object_name = "insurer"
    success_url = reverse_lazy("insurers:insurer_list")

    def form_valid(self, form: InsurerForm) -> HttpResponse:
        try:
            update_insurer(
                actor=self.request.user,
                insurer=self.object,
                **form.cleaned_data,
            )
        except ValidationError as exc:
            _apply_validation_error(form, exc)
            return self.form_invalid(form)
        messages.success(self.request, "Zmiany zostały zapisane.")
        return redirect(self.success_url)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edycja towarzystwa ubezpieczeniowego"
        context["submit_label"] = "Zapisz zmiany"
        return context


class InsurerDeactivateView(InsurerAccessMixin, View):
    permission_required = "insurers.change_insurer"
    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        insurer = get_object_or_404(Insurer, pk=pk)
        insurer, changed = deactivate_insurer(actor=request.user, insurer=insurer)
        if changed:
            messages.success(request, "Towarzystwo zostało wyłączone.")
        else:
            messages.info(request, "Towarzystwo było już wyłączone.")
        return redirect("insurers:insurer_list")


class InsurerRestoreView(InsurerAccessMixin, View):
    permission_required = "insurers.change_insurer"
    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        insurer = get_object_or_404(Insurer, pk=pk)
        insurer, changed = restore_insurer(actor=request.user, insurer=insurer)
        if changed:
            messages.success(request, "Towarzystwo zostało ponownie włączone.")
        else:
            messages.info(request, "Towarzystwo było już aktywne.")
        return redirect("insurers:insurer_list")


class InsuranceTypeListView(InsurerAccessMixin, DictionaryListMixin, ListView):
    model = InsuranceType
    permission_required = "insurers.view_insurancetype"
    template_name = "insurers/insurance_type_list.html"
    context_object_name = "insurance_types"
    paginate_by = 25

    def get_queryset(self) -> QuerySet[InsuranceType]:
        return self.apply_status_and_search(InsuranceType.objects.all())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.list_filter_context())
        return context


class InsuranceTypeCreateView(InsurerAccessMixin, CreateView):
    model = InsuranceType
    form_class = InsuranceTypeForm
    permission_required = "insurers.add_insurancetype"
    template_name = "insurers/insurance_type_form.html"
    success_url = reverse_lazy("insurers:insurance_type_list")

    def form_valid(self, form: InsuranceTypeForm) -> HttpResponse:
        try:
            create_insurance_type(actor=self.request.user, **form.cleaned_data)
        except ValidationError as exc:
            _apply_validation_error(form, exc)
            return self.form_invalid(form)
        messages.success(self.request, "Rodzaj ubezpieczenia został dodany.")
        return redirect(self.success_url)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Nowy rodzaj ubezpieczenia"
        context["submit_label"] = "Dodaj rodzaj"
        return context


class InsuranceTypeUpdateView(InsurerAccessMixin, UpdateView):
    model = InsuranceType
    form_class = InsuranceTypeForm
    permission_required = "insurers.change_insurancetype"
    template_name = "insurers/insurance_type_form.html"
    context_object_name = "insurance_type"
    success_url = reverse_lazy("insurers:insurance_type_list")

    def form_valid(self, form: InsuranceTypeForm) -> HttpResponse:
        try:
            update_insurance_type(
                actor=self.request.user,
                insurance_type=self.object,
                **form.cleaned_data,
            )
        except ValidationError as exc:
            _apply_validation_error(form, exc)
            return self.form_invalid(form)
        messages.success(self.request, "Zmiany zostały zapisane.")
        return redirect(self.success_url)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edycja rodzaju ubezpieczenia"
        context["submit_label"] = "Zapisz zmiany"
        return context


class InsuranceTypeDeactivateView(InsurerAccessMixin, View):
    permission_required = "insurers.change_insurancetype"
    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        insurance_type = get_object_or_404(InsuranceType, pk=pk)
        insurance_type, changed = deactivate_insurance_type(
            actor=request.user,
            insurance_type=insurance_type,
        )
        if changed:
            messages.success(request, "Rodzaj ubezpieczenia został wyłączony.")
        else:
            messages.info(request, "Rodzaj ubezpieczenia był już wyłączony.")
        return redirect("insurers:insurance_type_list")


class InsuranceTypeRestoreView(InsurerAccessMixin, View):
    permission_required = "insurers.change_insurancetype"
    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        insurance_type = get_object_or_404(InsuranceType, pk=pk)
        insurance_type, changed = restore_insurance_type(
            actor=request.user,
            insurance_type=insurance_type,
        )
        if changed:
            messages.success(
                request,
                "Rodzaj ubezpieczenia został ponownie włączony.",
            )
        else:
            messages.info(request, "Rodzaj ubezpieczenia był już aktywny.")
        return redirect("insurers:insurance_type_list")
