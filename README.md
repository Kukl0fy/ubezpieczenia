# Ubezpieczenia

Internal web application for managing insurance policies in a small
real-estate office. The system keeps a trustworthy policy register and will
support expiration reminders.

**Status:** early foundation (BOOT-001). Domain modules such as customers,
policies, and notifications are not implemented yet.

## Requirements

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- Optionally, for host-side commands without containers:
  - Python 3.13
  - [uv](https://docs.astral.sh/uv/)
  - PostgreSQL 17+

## Quick start (Docker Compose)

This is the supported local procedure.

1. Copy the example environment file:

```bash
cp .env.example .env
```

On Windows (PowerShell):

```powershell
Copy-Item .env.example .env
```

2. Start the stack (PostgreSQL + application):

```bash
docker compose up --build
```

Compose starts Django with the **development** server (`runserver`) on purpose.
Do not use `runserver` in production.

3. Apply migrations:

```bash
docker compose exec web python manage.py migrate
```

4. Create an administrator:

```bash
docker compose exec web python manage.py createsuperuser
```

5. Open the application:

- Application: http://127.0.0.1:8000/admin/
- Health endpoint: http://127.0.0.1:8000/health/

## Tests

```bash
docker compose exec web uv run pytest
```

Or with dependencies already installed on the host (PostgreSQL must be reachable
with the settings from `.env`; set `POSTGRES_HOST=127.0.0.1` when the database
runs on the host):

```bash
uv sync
uv run pytest
```

## Code quality (Ruff)

```bash
docker compose exec web uv run ruff check .
```

Host equivalent:

```bash
uv run ruff check .
```

## Useful host commands

When working outside Compose after `uv sync` and a local `.env`:

```bash
uv sync
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run pytest
uv run ruff check .
```

## Privacy

Do not commit real customer data, policy scans, production secrets, or a local
`.env` file. Use synthetic examples only in tests, fixtures, and documentation.
