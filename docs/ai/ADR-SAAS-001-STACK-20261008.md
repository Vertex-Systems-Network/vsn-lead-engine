# ADR-SAAS-001: reversible SaaS application stack

Decision date: 2026-10-08 (Asia/Karachi)
Status: accepted technical selection under the standing technical-autonomy delegation
Scope: local development and the first SaaS implementation slice only; no deployment, billing, paid source or production activation is authorized

## Context

The current repository is a mature Python CLI/workflow for one production lead pipeline. It has no SaaS HTTP server, tenant database, web UI, user identity or per-user scheduler. Its existing runtime is coupled to fixed geography/category rules, Google Sheets delivery, R2 deduplication and GitHub Actions operations. M3 preserves that production boundary and defines tenant, job, source and API contracts.

The chosen design should reuse the team's existing Python capability, provide secure workspace/session and admin foundations, support a versioned API, and keep early development runnable without a new recurring paid service. Future desktop/mobile clients can use the API. The public-production host, identity vendor, email delivery, billing gateway, lead provider and qualified compliance conclusions remain separate decisions.

## Decision

Use an additive, isolated SaaS application in this repository:

| Concern | Selection for the first implementation slice |
|---|---|
| Runtime | Python 3.12 for the SaaS app and CI; keep the existing package's compatibility/runtime contract unchanged |
| Web framework | Django 5.2 LTS, pinned to the latest security patch compatible with selected dependencies at implementation |
| API | Django REST Framework under `/api/v1`; explicit serializers, permission classes and workspace-scoped query services |
| Web UI | Django server-rendered templates with progressive enhancement; no SPA build chain until measured UX needs justify it |
| Identity | Django custom user model and session authentication for same-origin web use; workspace membership/roles remain explicit application models |
| Primary data store | PostgreSQL for integration, concurrency and production-like tests; no SaaS data is written to the production Google Sheets or R2 stores |
| Job dispatch | Transactional job/outbox rows in PostgreSQL plus separate web/worker/scheduler processes. Claims use short transactions and row locks; no in-process request background task for durable work |
| Cache/search | Start without a distributed cache or separate search service. Use indexed, tenant-scoped PostgreSQL queries; add a service only with measured need |
| File/export storage | Keep behind an interface; local disposable storage in development. Select production object storage only after retention, rights and cost gates are evidenced |
| Payments, external identity, source API, hosting and monitoring vendors | Not selected or activated |

The SaaS application must be opt-in and isolated under an `apps/saas/` project boundary. Its dependency lock and migrations are separate from the current production collection workflow. Existing CLI commands, scheduler, secrets, production datasets, Google delivery, R2 dedupe and P01-P70 workflows remain unchanged.

Django 5.2 is selected because it is an LTS release with official security and data-loss support through April 2028, supports the repository's existing Python 3.11+ floor, and includes session/authentication, model, migration and admin foundations. Reassess the maintained LTS target before production; do not pin an unsupported patch.

## Alternatives considered

| Option | Strengths | Costs and risks | Decision |
|---|---|---|---|
| **Django 5.2 LTS + DRF + PostgreSQL + server-rendered web** | Fits current Python code; auth/session/admin/ORM/migrations and API serializers are integrated; one main application runtime; relational transactions support atomic usage reservations and job claims | Django's conventions must be learned; tenant boundaries still require explicit service/query tests; templates may need a richer client if interactions grow | **Selected** for lowest early integration and operational complexity |
| FastAPI + SQLAlchemy/Alembic + PostgreSQL + custom admin/auth + React | Strong API ergonomics, type-validated request models and dependency injection; good fit for independently scaled services | Requires separate identity/session/admin/migration choices. FastAPI's in-process background tasks are not a durable job system for long-running work, so this product still needs a persistent queue and worker | Rejected as the default; reconsider if measured API or async requirements outweigh the extra integrations |
| Django + Celery + Redis + React | Mature distributed queue pattern and independent worker scaling | Adds broker, worker and frontend build/runtime components before workload evidence; introduces extra deployment, monitoring, security and potentially recurring cost | Defer until queue volume, latency or reliability evidence requires it |
| Reuse the existing collector directly as the SaaS server | Reuses working collection code | Couples customer tenant configuration to operator-only quota, Google Sheets, production R2 and workflow lifecycle; risks changing daily production behavior and does not provide tenant isolation | Rejected; extract only narrow, tested domain adapters after boundaries are proven |

FastAPI remains a valid framework. Its documentation describes dependency injection and in-process background tasks; those tasks alone do not satisfy the durable, retryable, tenant-scoped job contract. Django's built-in authentication/session facilities and DRF's serializers/authentication are a stronger fit for this repository's initial account, workspace, admin and versioned API scope.

## Queue and transaction rules

- Persist job intent and usage reservation in one database transaction before acknowledging a run request.
- Worker claims are short, atomic and recoverable. Use PostgreSQL row locking (including `SKIP LOCKED` only for queue-like claims), a lease expiry and compare-and-set state transitions.
- External provider calls happen outside the database transaction. Re-check cancellation, tenant membership, source policy and limits immediately before dispatch.
- Delivery is at least once; idempotency keys and append-only attempts make repeated delivery safe. Do not claim exactly-once provider execution.
- Exercise real concurrency against PostgreSQL in CI. SQLite-only tests cannot certify row-lock, uniqueness or usage-reservation behavior.
- Keep scheduling occurrences durable and use the M3 IANA timezone/DST resolution and unique occurrence key. Do not use GitHub Actions cron for customer schedules.

## Security and data constraints

- Every web/API request resolves the actor's membership server-side and scopes data access before filtering or pagination.
- Use secure, HTTP-only, same-site session cookies and CSRF protection for browser mutations. Never trust a workspace ID or role from a client without membership lookup.
- Define a custom user model before the first app migration. Keep lead records separate from identity/session records.
- Platform support access is separate from ordinary workspace admin and must be least-privileged, attributable and audited.
- No provider secret, payment data, raw email/phone or signed export URL may enter logs, AI context or Git.
- Source policy, retention, export rights and qualified privacy review remain mandatory before real customer-source data is enabled.

## Cost and rollout

The implementation spike and test suite use open-source dependencies and local/disposable PostgreSQL. This is a zero-new-paid-spend choice for development, not a claim that hosted production will be free. No paid infrastructure, API, identity, email, AI, payment or monitoring service is selected. If a required production capability has no safe no-spend path, continue local contracts, tests and UI while leaving that external activation disabled.

Roll out in slices:

1. Add the isolated Django project, settings, health endpoint and PostgreSQL test configuration without changing existing CLI dependencies or workflows.
2. Implement workspace/membership authorization and cross-tenant tests.
3. Implement versioned API contracts and tenant-scoped persistence.
4. Add transactional job/outbox and schedule workers after concurrency tests pass.
5. Add a responsive user workflow only after API behavior is stable.
6. Keep production SaaS deploy, customer data and billing behind separate release gates.

Migration uses expand -> migrate/backfill -> verify -> contract. No existing production store is migrated in this ADR.

## Revisit triggers

Re-evaluate the framework or queue only if measured requirements show the Django monolith cannot meet a documented latency, throughput, scaling, integration or usability target; if independent release/access boundaries demand a separate repository; or if Django 5.2's support horizon is too short at implementation. Record a new ADR before an incompatible stack or repository change.

## Evidence reviewed

- Django 5.2 supports Python 3.10–3.14 and the project states security/data-loss support through April 2028: [Django 5.2 release notes](https://docs.djangoproject.com/en/5.2/releases/5.2/) and [Django 5.2 LTS release announcement](https://www.djangoproject.com/weblog/2025/dec/03/django-52-released/).
- Django provides built-in authentication and session handling: [authentication](https://docs.djangoproject.com/en/5.2/topics/auth/default/) and [sessions](https://docs.djangoproject.com/en/5.2/topics/http/sessions/).
- DRF provides configurable authentication and serializers for versioned API contracts: [authentication](https://www.django-rest-framework.org/api-guide/authentication/) and [serializers](https://www.django-rest-framework.org/api-guide/serializers/).
- Django documents transactions and PostgreSQL row-locking support: [database transactions](https://docs.djangoproject.com/en/5.2/topics/db/transactions/) and [QuerySet select_for_update](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update).
- PostgreSQL documents `SKIP LOCKED` as suitable to reduce contention for queue-like tables, while warning it yields an inconsistent view for general-purpose queries: [SELECT locking clause](https://www.postgresql.org/docs/current/sql-select.html).
- FastAPI documents in-process background tasks and dependency injection: [background tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/) and [features](https://fastapi.tiangolo.com/features/).

These sources support framework capability and support-horizon claims; they do not establish VSN's scale, source rights, legal compliance, willingness-to-pay, hosting cost or production readiness.
