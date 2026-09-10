"""Authentication and application panel views."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.views.generic import TemplateView


class AppLoginView(LoginView):
    """Staff login using Django's authentication form."""

    template_name = "accounts/login.html"
    redirect_authenticated_user = True


class AppLogoutView(LogoutView):
    """End the session with POST only; redirect to the login page."""

    next_page = reverse_lazy("login")
    http_method_names = ["post", "options"]


class DashboardView(LoginRequiredMixin, TemplateView):
    """Minimal private application home page."""

    template_name = "accounts/dashboard.html"
