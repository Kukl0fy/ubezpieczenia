"""URL configuration for the insurance application."""

from django.contrib import admin
from django.urls import path

from config.health import healthcheck

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", healthcheck, name="healthcheck"),
]
