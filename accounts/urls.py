"""URL routes for authentication and the private dashboard."""

from django.urls import path

from accounts.views import AppLoginView, AppLogoutView, DashboardView

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("login/", AppLoginView.as_view(), name="login"),
    path("logout/", AppLogoutView.as_view(), name="logout"),
]
