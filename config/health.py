"""Application health endpoint for monitoring."""

from __future__ import annotations

from django.db import connection
from django.db.utils import OperationalError
from django.http import JsonResponse


def healthcheck(_request):
    """Return 200 when the app and database are reachable."""
    try:
        connection.ensure_connection()
    except OperationalError:
        return JsonResponse({"status": "error"}, status=503)

    return JsonResponse({"status": "ok"})
