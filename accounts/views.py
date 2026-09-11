"""Authentication and application panel views."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.views.generic import TemplateView

from policies.presenters import (
    dashboard_expiry_buckets,
    days_until_end,
    primary_policyholder,
)


class AppLoginView(LoginView):
    """Staff login using Django's authentication form."""

    template_name = "accounts/login.html"
    redirect_authenticated_user = True


class AppLogoutView(LogoutView):
    """End the session with POST only; redirect to the login page."""

    next_page = reverse_lazy("login")
    http_method_names = ["post", "options"]


class DashboardView(LoginRequiredMixin, TemplateView):
    """Private home page with on-demand policy expiry sections."""

    template_name = "accounts/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        if user.has_perm("policies.view_policy"):
            buckets = dashboard_expiry_buckets()
            today = buckets["today"]
            for key in ("overdue", "within_7", "within_30"):
                for policy in buckets[key]:
                    policy.primary_customer = primary_policyholder(policy)
                    policy.days_delta = days_until_end(
                        policy.coverage_end, today=today
                    )
                    policy.days_abs = abs(policy.days_delta)
            context.update(buckets)
            context["show_policy_expiry"] = True
        else:
            context["show_policy_expiry"] = False
        return context
