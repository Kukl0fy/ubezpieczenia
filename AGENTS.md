# AGENTS.md

## Purpose

This repository contains a private web application for managing insurance
policies in a small real-estate office. Coding agents must optimize for:

1. reliable policy-expiration reminders;
2. correct and auditable business data;
3. security and privacy of customer data;
4. a simple workflow for a non-technical user;
5. maintainability by a small team;
6. the smallest implementation that satisfies the approved task.

This file defines repository-wide rules. A nested `AGENTS.md` may add stricter
rules for its directory, but must not weaken these rules.

## Current project status

The target architecture is described in `ARCHITECTURE.md`.

### Confirmed toolchain (BOOT-001)

- Python 3.13
- Django 5.2 LTS (currently 5.2.17)
- PostgreSQL via Docker Compose (`postgres:17`) and `psycopg`
- Dependency manager: `uv` with `pyproject.toml` and `uv.lock`
- Tests: `pytest` + `pytest-django`
- Lint: Ruff
- CI: GitHub Actions (`.github/workflows/ci.yml`)

### Repository map (implemented)

- `config/` — Django project settings, URLs, WSGI/ASGI, `/health/`
- `accounts/` — custom `AUTH_USER_MODEL` (`accounts.User`) and admin
- `tests/` — bootstrap tests (settings, user model, health, admin)
- `compose.yaml`, `Dockerfile` — local Docker Compose stack
- `.env.example` — sample environment variables (no real secrets)
- `.github/workflows/ci.yml` — PR/`main` checks

Not implemented yet: `customers`, `insurers`, `policies`, `notifications`,
`documents`, `audit`, reminders, email, import/export, or production hosting.

### Exact commands

Install dependencies:

```bash
uv sync
```

Local Docker Compose (preferred local procedure):

```bash
cp .env.example .env
docker compose up --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

Migrations and checks (host, after `uv sync` and a configured `.env`):

```bash
uv run python manage.py migrate
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py check
```

Tests and lint:

```bash
uv run pytest
uv run ruff check .
```

Compose equivalents:

```bash
docker compose exec web uv run pytest
docker compose exec web uv run ruff check .
```

Agents must use this toolchain. Do not invent a second package manager or
silently replace Docker Compose, `uv`, pytest, or Ruff.

## Authority and decision hierarchy

When instructions conflict, use this order:

1. the user's current request;
2. the coordinator's task specification;
3. this `AGENTS.md`;
4. accepted Architecture Decision Records in `docs/adr/`;
5. `ARCHITECTURE.md`;
6. existing repository conventions;
7. reasonable defaults.

If a task conflicts with a higher-level rule, stop and report the conflict.
Do not resolve an architectural conflict silently.

## Roles

### Coordinator / architect

The coordinator:

- audits the current branch before assigning work;
- maintains architecture, backlog, status, and ADRs;
- defines task scope and acceptance criteria;
- decides which tasks may run in parallel;
- reviews diffs, migrations, tests, and security impact;
- accepts, requests fixes, reworks, or rejects changes;
- decides when a task is ready to merge.

### Implementation agent

An implementation agent:

- performs only the assigned task;
- follows existing architecture and repository conventions;
- makes the smallest coherent change;
- adds appropriate tests;
- reports blockers instead of expanding the task;
- does not merge its own work unless explicitly authorized.

### Review agent

A review agent, if assigned, must:

- inspect the actual diff and surrounding code;
- verify acceptance criteria independently;
- run relevant checks when possible;
- prioritize correctness, data safety, security, and regression risk;
- report findings with file and line references;
- not modify code unless the task explicitly requests fixes.

## Required workflow for every implementation task

### 1. Read before editing

Read at minimum:

- this file;
- `ARCHITECTURE.md`;
- the complete task specification;
- files directly related to the task;
- relevant tests and migrations;
- applicable ADRs.

Check the current branch and working tree. Existing changes belong to the user
or another agent unless proven otherwise. Preserve them.

### 2. Establish the baseline

Before editing:

- identify the current behavior;
- run the most relevant existing checks;
- record any pre-existing failures;
- identify affected modules and data;
- list assumptions that affect implementation.

A pre-existing failure is not permission to delete or weaken a test.

### 3. Keep the task bounded

Do not:

- implement adjacent backlog items;
- perform unrelated refactors;
- rename public concepts without approval;
- replace the framework or build system;
- add infrastructure that is not needed by the task;
- introduce abstractions solely for hypothetical future use;
- alter production data or external services unless explicitly authorized.

If a necessary change falls outside the task, explain it and request a decision.

### 4. Implement safely

- Reuse existing project patterns where they are sound.
- Keep domain rules out of templates and view-only code.
- Prefer explicit business rules over hidden signals or side effects.
- Use database constraints for invariants that must hold under concurrency.
- Use transactions for operations that must succeed or fail together.
- Make scheduled and retryable work idempotent.
- Keep time-zone behavior explicit; business dates use `Europe/Warsaw`.
- Store money as decimal values with an explicit currency, never binary floats.
- Keep secrets and environment-specific values outside source control.
- Do not log passwords, tokens, policy documents, or unnecessary personal data.

### 5. Test the change

Every business rule requires a test at the lowest useful level. Add integration
tests where several components must cooperate.

At minimum, consider:

- the normal path;
- validation errors;
- permissions and unauthenticated access;
- boundary dates;
- duplicate execution;
- failure and retry behavior;
- cancellation and renewal behavior;
- migration forward behavior;
- existing records created before the change.

Do not claim completion if relevant tests were not run. If they cannot be run,
state the exact blocker.

### 6. Review the diff

Before reporting completion:

- inspect the full diff;
- remove debug output and accidental formatting changes;
- ensure no secret or production data was added;
- confirm migrations match model changes;
- confirm new dependencies are necessary and declared once;
- confirm user-facing behavior and error messages are understandable;
- confirm documentation affected by the change is current.

### 7. Submit a completion report

Use this structure:

1. **Summary** — what changed and why.
2. **Files changed** — grouped by purpose.
3. **Database changes** — migrations, constraints, and data impact.
4. **Tests added or changed**.
5. **Verification** — exact commands and outcomes.
6. **Security/privacy impact**.
7. **Assumptions and limitations**.
8. **Open decisions or blockers**.
9. **Commit hash or PR**, when applicable.

## Architecture boundaries

The default target is a modular monolith:

- one deployable web application;
- one PostgreSQL database;
- server-rendered user interface;
- one scheduled reminder-processing entry point;
- an external transactional email provider;
- optional private object storage for documents.

Do not introduce microservices, Kafka, Kubernetes, Redis, Celery, a separate SPA,
or a second database without an accepted ADR and explicit coordinator approval.

Redis or a task queue may be justified later by demonstrated workload, not by
speculation.

## Intended module ownership

The exact paths must follow the audited repository, but domain ownership should
remain clear:

- `accounts`: users, authentication, authorization;
- `customers`: persons and companies, contact details;
- `insurers`: insurers and insurance-type dictionaries;
- `policies`: policies, parties, insured objects, renewals;
- `notifications`: reminder rules, notification records, email attempts;
- `documents`: optional private attachments;
- `audit`: significant business and security events.

Modules may reference stable public interfaces of another module. Avoid
cross-module writes that bypass domain services or documented operations.

## Domain invariants

These rules must not be weakened without an accepted ADR:

- A policy end date cannot precede its start date.
- Renewal creates a new policy; it never overwrites the previous policy.
- A policy cannot renew itself or create a renewal cycle.
- Cancelling or renewing a policy prevents obsolete future reminders.
- Reminder processing must be idempotent.
- A failed email does not remove the in-app notification.
- Sending an email does not mean the business task was completed.
- Historical policies must not disappear when a customer is archived.
- Referenced dictionaries are deactivated rather than destructively deleted.
- Sensitive attachments are private and require authorization for every access.
- Audit history must not contain secrets or complete document contents.

## Database and migration rules

- PostgreSQL is the production database.
- Schema changes require versioned migrations.
- Never edit an already-applied shared migration unless explicitly authorized.
- Prefer additive, backward-compatible migrations.
- Potentially destructive or blocking migrations require a rollout plan.
- Data migrations must be deterministic, bounded, and tested on representative
  data.
- Enforce uniqueness and referential integrity in the database where practical.
- Do not use hard deletion for customer or policy history by default.

For reminder deduplication, the database must ultimately enforce a unique
business key equivalent to:

`policy + reminder rule + scheduled date/time + channel`

The exact implementation may vary, but application-only duplicate checks are
insufficient under concurrent execution.

## Time and scheduling rules

- Use time-zone-aware timestamps.
- Interpret business scheduling in `Europe/Warsaw` unless requirements change.
- Separate a policy coverage date from a notification execution timestamp.
- Tests must cover month/year boundaries and daylight-saving transitions where
  timestamps are involved.
- Re-running a reminder job for the same period must not duplicate effects.
- Record the last successful job completion so silent scheduler failure can be
  detected.

## Email rules

- Email is initially an internal alert to office staff.
- Customer email automation is outside MVP unless explicitly approved.
- Use a transactional email service or approved SMTP relay.
- Do not attach policy scans to reminder emails.
- Keep email content to the minimum personal data needed.
- Record delivery attempts and errors without storing credentials.
- Use bounded retries with backoff for temporary failures.
- Never mark a reminder handled merely because email delivery succeeded.

## Authentication and authorization

- No public registration.
- Deny access by default.
- Every non-public application view requires authentication.
- Administrative actions require explicit permission.
- Passwords use the framework's approved secure hashing.
- Session cookies must be secure in production.
- CSRF protection must remain enabled.
- File access must check authorization, not only possession of a URL.
- Rate-limit or otherwise protect authentication attempts.
- Prefer two-factor authentication before broader production use.

## Privacy and security

Treat all customer and policy information as confidential.

- Collect only data required by an approved workflow.
- Do not add PESEL, identity-document numbers, health details, or other highly
  sensitive fields without explicit business and legal approval.
- Never use real customer data in tests, fixtures, screenshots, or bug reports.
- Use synthetic or irreversibly anonymized examples.
- Redact personal data from application and infrastructure logs.
- Keep secrets in environment variables or the deployment secret manager.
- Use HTTPS in production.
- Keep dependencies patched and review security-sensitive upgrades.
- Prefer EU/EEA storage and processors for production personal data.

Legal compliance decisions must be confirmed by the responsible person; agents
must not present architectural guidance as legal advice.

## Documents and file uploads

Document upload is optional and should not block the core policy register.
When enabled:

- store metadata in PostgreSQL and bytes in private object storage;
- generate server-controlled object keys;
- validate type and size;
- do not trust original filenames or client MIME types;
- require authorization for upload, download, replacement, and deletion;
- use short-lived access or authenticated streaming;
- include documents in backup and retention design;
- consider malware scanning before production acceptance.

## Audit rules

Audit at least:

- login-related security events;
- policy creation, material edit, cancellation, renewal, and archival;
- reminder handling;
- document upload and deletion;
- administrative changes.

An audit record should identify actor, action, target, timestamp, and a safe
summary. It must not contain passwords, tokens, or full document contents.

## Import and export

- Imports require validation and a preview or dry-run summary.
- Report created, updated, skipped, and invalid rows separately.
- Avoid partial invisible success; use transactions or explicit batch results.
- Imports must be safe to retry or have a documented duplicate strategy.
- Exports must respect authorization and avoid unnecessary sensitive fields.
- CSV/Excel values beginning with formula characters must be escaped when needed
  to prevent spreadsheet-formula injection.

## Dependencies

Before adding a dependency, explain:

- the concrete problem it solves;
- why existing dependencies or standard library are insufficient;
- maintenance and security implications;
- whether it affects deployment or licensing.

Use the repository's existing package manager and lockfile. Do not replace them
inside a feature task.

## Git rules

- Work on one task per branch unless instructed otherwise.
- Use a descriptive branch name containing the task identifier.
- Keep commits focused and reviewable.
- Do not rewrite shared history.
- Do not remove or overwrite unrelated user changes.
- Do not merge without coordinator approval.
- Reference the task identifier in commits or PR descriptions.

## Definition of Done

A task is done only when:

- all acceptance criteria are satisfied;
- relevant tests pass;
- migrations and data impact are verified;
- security/privacy implications are addressed;
- no unrelated changes remain;
- documentation is updated where required;
- the completion report is accurate;
- the coordinator has accepted the result.

Implementation alone is not completion.

## Stop conditions

Stop and ask the coordinator when:

- the task requires an architectural decision not already recorded;
- requirements contradict repository behavior or another accepted decision;
- production credentials, data access, or destructive actions are required;
- a migration may delete or irreversibly transform data;
- real personal data appears in source control;
- tests reveal unrelated corruption or security risk;
- the requested change cannot be completed without expanding scope materially.
