"""Custom user model for the insurance application."""

from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Application user based on Django's standard user model."""

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"
