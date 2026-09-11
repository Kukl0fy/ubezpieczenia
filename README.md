# Ubezpieczenia

Internal web application for managing insurance policies in a small
real-estate office. The system keeps a trustworthy policy register and will
support expiration reminders.

**Status:** transactional policy renewal workflow (POL-003). Automatic reminder
email/background jobs and contact-handling are not implemented yet.

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

4. Create the first administrator (there is no public registration):

```bash
docker compose exec web python manage.py createsuperuser
```

5. Open the application:

- Login: http://127.0.0.1:8000/login/
- Private dashboard: http://127.0.0.1:8000/
- Customers: http://127.0.0.1:8000/customers/
- Policies: http://127.0.0.1:8000/policies/
- Django Admin: http://127.0.0.1:8000/admin/
- Health endpoint (public, for monitoring): http://127.0.0.1:8000/health/

Logout is available from the dashboard header and must be submitted with
`POST` (CSRF protected). There is no public sign-up page.

Login attempts are rate-limited with `django-axes` (shared PostgreSQL state):
5 consecutive failures for the same username + IP combination lock further
attempts for about 15 minutes. The lockout message does not reveal whether
the account exists.

Sessions expire after 8 hours of inactivity by default, are refreshed on
activity, and end when the browser is closed. Override the idle lifetime with
`DJANGO_SESSION_COOKIE_AGE` (seconds) in `.env`.

## Dictionaries (insurers)

Insurance companies and insurance types are managed as controlled dictionaries
in Django Admin (no free-text-per-policy values, no hard delete):

- http://127.0.0.1:8000/admin/insurers/insurer/
- http://127.0.0.1:8000/admin/insurers/insurancetype/

Create a staff user with the appropriate Django permissions (or a superuser).
Deactivate unused entries with `is_active` instead of deleting them. The private
dashboard shows dictionary links only when the signed-in user has the matching
view permissions.

## Customers

Persons and companies are managed in a dedicated office UI (archive instead of
hard delete; no PESEL/NIP or other highly sensitive identifiers):

- List: http://127.0.0.1:8000/customers/
- Create: http://127.0.0.1:8000/customers/new/
- Detail / edit / archive / restore under `/customers/<id>/…`

Required Django permissions:

- `customers.view_customer` — list and detail
- `customers.add_customer` — create
- `customers.change_customer` — edit, archive, and restore

There is no permanent delete route. Django Admin remains available for
technical administration, but the dashboard **Klienci** link opens the new UI.

Successful create/update/archive/restore operations record append-only audit
events (`customer.created`, `customer.updated`, `customer.archived`,
`customer.restored`) without personal data in the summary.

## Policies

Core policy workflow is available in the office UI:

- List: http://127.0.0.1:8000/policies/
- Create: http://127.0.0.1:8000/policies/new/
- Detail / edit / renew / cancel under `/policies/<id>/…`

Required Django permissions:

- `policies.view_policy` — list, detail, and dashboard expiry sections
- `policies.add_policy` — create
- `policies.change_policy` — edit and cancel
- renewal requires `view` + `add` + `change` together

Renewal creates a new `ACTIVE` policy, marks the previous one `RENEWED`, copies
parties and insured-object links, and keeps history through `previous_policy`.
A policy can have at most one renewal successor.

The dashboard **Polisy** link opens this UI. Expiry buckets on the dashboard are
calculated with `timezone.localdate()` (`Europe/Warsaw`) each time the page
opens. There is no reminder record store, scheduler, or automatic email yet.
Contact-handling workflows are the next stage.

Django Admin remains available for technical administration of parties and
insured objects.

## Audit

Significant authentication and future business events are stored in an
append-only audit register:

- http://127.0.0.1:8000/admin/audit/auditevent/

Staff users need `audit.view_auditevent` to browse events. Entries cannot be
created, edited, or deleted in Admin.

Roles of related mechanisms:

- `django-axes` protects login attempts and stores technical lockout state;
- `audit.AuditEvent` is the application’s safe history of significant events;
- Django Admin `LogEntry` records changes made through the Admin UI.

## Tests

```bash
docker compose exec web uv run pytest
```

Customer UI module only:

```bash
docker compose exec web uv run pytest tests/test_customer_ui.py
```

Policy UI module only:

```bash
docker compose exec web uv run pytest tests/test_policy_ui.py
```

Policy renewal tests:

```bash
docker compose exec web uv run pytest tests/test_policy_renewal.py
```

Or with dependencies already installed on the host (PostgreSQL must be reachable
with the settings from `.env`; set `POSTGRES_HOST=127.0.0.1` when the database
runs on the host):

```bash
uv sync
uv run pytest
uv run pytest tests/test_customer_ui.py
uv run pytest tests/test_policy_ui.py
uv run pytest tests/test_policy_renewal.py
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
