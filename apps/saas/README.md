# VSN Lead Engine SaaS development app

An opt-in Django 5.2 LTS / DRF app, isolated from the existing production collector. PostgreSQL is the default store. The first migration defines a custom user model before any identity data is created.

## Local setup

Use Python 3.12 on Linux, a disposable PostgreSQL database and a separate virtual environment. Install with `python -m pip install --require-hashes -r apps/saas/requirements.txt`. This lock contains CPython 3.12 Linux wheels; regenerate/review hashes before choosing another platform.

Set `SAAS_SECRET_KEY` outside Git, and configure `SAAS_DB_NAME`, `SAAS_DB_USER`, `SAAS_DB_PASSWORD`, `SAAS_DB_HOST` and `SAAS_DB_PORT`. The database user requires create-database permission only for the disposable test suite. Use separate limited credentials for any eventual deployment. Set `SAAS_DEBUG=1` only for local development. Run:

```sh
python apps/saas/manage.py migrate
python apps/saas/manage.py createsuperuser
python apps/saas/manage.py test core
python apps/saas/manage.py runserver 127.0.0.1:8000
```

The local-only `SAAS_SQLITE_SMOKE=1` option requires debug mode and runs basic tests without PostgreSQL. It does not verify row-lock or concurrency semantics; the concurrency test skips explicitly. CI uses real PostgreSQL and verifies migrations forward, back and forward again.

## Implemented surface

- `/health/`: liveness and explicit disabled provider dispatch; no credentials/database details.
- `/accounts/login/`, `/accounts/logout/`: Django same-origin sessions; CSRF-protected forms and POST logout.
- `/`: authenticated workspace overview.
- `/api/v1/workspaces/`: list only the actor's workspaces; creation atomically installs an owner membership.
- `/api/v1/workspaces/{workspace_id}/members/`: owner/admin list, bounded at 100 rows.
- `/api/v1/workspaces/{workspace_id}/members/{user_id}/`: PATCH role or DELETE membership; last owner protected transactionally; only owners change ownership.
- `/api/v1/workspaces/{workspace_id}/jobs/`: bounded tenant-scoped listing and draft creation.
- `/api/v1/workspaces/{workspace_id}/jobs/{job_id}/`: tenant-scoped detail; foreign IDs return 404.

Draft creation requires an `Idempotency-Key` header. Search JSON accepts countries (US/CA), categories, statuses, required_fields, source_codes and result_limit (1–1000). Unknown fields fail validation. Phone qualification is always included. A key replays the normalized original request; changing its payload returns 409. Membership and write role are rechecked inside the transaction. A workspace row lock and unique tenant/key constraint serialize concurrent duplicate creates.

Drafts never enqueue, reserve usage, dispatch source calls, collect data, export, schedule or charge. Source codes and statuses in drafts are requested preferences, not verified capabilities. Entitlement/source policy enforcement and atomic usage/outbox work are required before dispatch is implemented. Public registration, member invitations, source activation and billing remain unavailable. Existing member role changes and removal are available to authorized owners/admins, with role-only audit records committed in the same transaction. Users are created locally by the management command for development testing only.

## Security and recovery

Non-debug settings require HTTPS, secure cookies, HSTS, CSRF, HTTP-only sessions and a supplied secret. No production collector variables, R2/Google credentials or customer contact data are consumed. Do not expose the development server publicly. Do not use this scaffold as production certification: login abuse controls, operational deployment, independent security review and the external rights/privacy gates remain open.

Initial migration reversal deletes disposable SaaS tables; never reverse it against customer data. For live migrations use the project expand/migrate/verify/contract policy and a verified restorable backup. This scaffold contains no existing-data migration and has no path to modify collector stores.

Dependency evidence: [Django 5.2.18 release notes](https://docs.djangoproject.com/en/5.2/releases/5.2.18/) and [DRF 3.18.3 / security release notes](https://www.django-rest-framework.org/community/release-notes/), reviewed 2026-10-08 PKT. The production collector dependency lock is separate and unchanged.
