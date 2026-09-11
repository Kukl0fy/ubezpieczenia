"""URL routes for the customer management UI."""

from django.urls import path

from customers import views

app_name = "customers"

urlpatterns = [
    path("", views.CustomerListView.as_view(), name="list"),
    path("new/", views.CustomerCreateView.as_view(), name="create"),
    path("<int:pk>/", views.CustomerDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.CustomerUpdateView.as_view(), name="edit"),
    path("<int:pk>/archive/", views.CustomerArchiveView.as_view(), name="archive"),
    path("<int:pk>/restore/", views.CustomerRestoreView.as_view(), name="restore"),
]
