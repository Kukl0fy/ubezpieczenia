"""URL routes for the policy management UI."""

from django.urls import path

from policies import views

app_name = "policies"

urlpatterns = [
    path("", views.PolicyListView.as_view(), name="list"),
    path("new/", views.PolicyCreateView.as_view(), name="create"),
    path("<int:pk>/", views.PolicyDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.PolicyUpdateView.as_view(), name="edit"),
    path("<int:pk>/renew/", views.PolicyRenewView.as_view(), name="renew"),
    path("<int:pk>/cancel/", views.PolicyCancelView.as_view(), name="cancel"),
]
