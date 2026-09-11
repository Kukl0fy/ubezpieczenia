"""URL routes for office insurance settings."""

from django.urls import path

from insurers import views

app_name = "insurers"

urlpatterns = [
    path("settings/", views.SettingsHubView.as_view(), name="settings"),
    path(
        "settings/insurers/",
        views.InsurerListView.as_view(),
        name="insurer_list",
    ),
    path(
        "settings/insurers/new/",
        views.InsurerCreateView.as_view(),
        name="insurer_create",
    ),
    path(
        "settings/insurers/<int:pk>/edit/",
        views.InsurerUpdateView.as_view(),
        name="insurer_edit",
    ),
    path(
        "settings/insurers/<int:pk>/deactivate/",
        views.InsurerDeactivateView.as_view(),
        name="insurer_deactivate",
    ),
    path(
        "settings/insurers/<int:pk>/restore/",
        views.InsurerRestoreView.as_view(),
        name="insurer_restore",
    ),
    path(
        "settings/insurance-types/",
        views.InsuranceTypeListView.as_view(),
        name="insurance_type_list",
    ),
    path(
        "settings/insurance-types/new/",
        views.InsuranceTypeCreateView.as_view(),
        name="insurance_type_create",
    ),
    path(
        "settings/insurance-types/<int:pk>/edit/",
        views.InsuranceTypeUpdateView.as_view(),
        name="insurance_type_edit",
    ),
    path(
        "settings/insurance-types/<int:pk>/deactivate/",
        views.InsuranceTypeDeactivateView.as_view(),
        name="insurance_type_deactivate",
    ),
    path(
        "settings/insurance-types/<int:pk>/restore/",
        views.InsuranceTypeRestoreView.as_view(),
        name="insurance_type_restore",
    ),
]
