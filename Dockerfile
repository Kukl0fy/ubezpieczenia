# syntax=docker/dockerfile:1

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /uvx /usr/local/bin/

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

COPY . .

# Production containers must use a WSGI/ASGI server (e.g. gunicorn), not
# Django's development server. Local Compose overrides the command with
# `runserver` for development only — see compose.yaml.
CMD ["python", "-c", "raise SystemExit('Set a production command (e.g. gunicorn). Django runserver is for local Compose development only.')"]
