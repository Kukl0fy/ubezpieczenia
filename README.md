# Ubezpieczenia

Internal web application for managing insurance policies in a small
real-estate office. The system keeps a trustworthy policy register and will
support expiration reminders.

**Status:** audited customer management UI (CUST-002). Policy reminders and
remaining domain UI beyond Django Admin are not implemented yet.

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

Policies, parties, and insured objects are managed in Django Admin (no hard
delete; history-preserving foreign keys):

- http://127.0.0.1:8000/admin/policies/policy/
- http://127.0.0.1:8000/admin/policies/insuredobject/

Staff users need `policies.view_policy` (and related change permissions) to work
with policies. The dashboard shows a **Polisy** link only when that view
permission is present. Transactional renewal and reminders are not available yet.

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

Or with dependencies already installed on the host (PostgreSQL must be reachable
with the settings from `.env`; set `POSTGRES_HOST=127.0.0.1` when the database
runs on the host):

```bash
uv sync
uv run pytest
uv run pytest tests/test_customer_ui.py
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
