# VSN Lead Engine SaaS development app

An opt-in Django 5.2 LTS / DRF app, isolated from the existing production collector. PostgreSQL is the default store. The first migration defines a custom user model before any identity data is created.

## Local setup

Use Python 3.12 on Linux, a disposable PostgreSQL database and a separate virtual environment. Install runtime with `python -m pip install --require-hashes -r apps/saas/requirements.txt`; use `requirements-dev.txt` for the pinned Ruff development tools. This lock contains CPython 3.12 Linux wheels; regenerate/review hashes before choosing another platform.

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
- `/`: authenticated workspace overview, with links to read-only workspace usage.
- `/workspaces/{workspace_id}/usage/`: session-authenticated read-only settled/reserved/limit table.
- `/api/v1/workspaces/{workspace_id}/usage/`: tenant-scoped server-derived counters/limits; no mutation methods.
- `/api/v1/workspaces/`: list only the actor's workspaces; creation atomically installs an owner membership.
- `/api/v1/workspaces/{workspace_id}/members/`: owner/admin list, bounded at 100 rows.
- `/api/v1/workspaces/{workspace_id}/members/{user_id}/`: PATCH role or DELETE membership; last owner protected transactionally; only owners change ownership.
- `/api/v1/workspaces/{workspace_id}/jobs/`: bounded tenant-scoped listing and draft creation.
- `/api/v1/workspaces/{workspace_id}/jobs/{job_id}/`: tenant-scoped detail; foreign IDs return 404.

Draft creation requires an `Idempotency-Key` header. Search JSON accepts countries (US/CA), categories, statuses, required_fields, source_codes and result_limit (1–1000). Unknown fields fail validation. Phone qualification is always included. A key replays the normalized original request; changing its payload returns 409. Membership and write role are rechecked inside the transaction. A workspace row lock and unique tenant/key constraint serialize concurrent duplicate creates.

Drafts never enqueue, reserve usage, dispatch source calls, collect data, export, schedule or charge. Source codes and statuses in drafts are requested preferences, not verified capabilities. Internal entitlement/source policy enforcement and atomic usage/outbox services now exist; bounded pre-dispatch leases and current-gate rechecks exist, while external execution/idempotency/recovery contracts are required before any consumer is enabled. Public registration, member invitations, source activation and billing remain unavailable. Existing member role changes and removal are available to authorized owners/admins, with role-only audit records committed in the same transaction. Users are created locally by the management command for development testing only.

## Security and recovery

Non-debug settings require HTTPS, secure cookies, HSTS, CSRF, HTTP-only sessions and a supplied secret. No production collector variables, R2/Google credentials or customer contact data are consumed. Do not expose the development server publicly. Do not use this scaffold as production certification: operational deployment, independent security review and the external rights/privacy gates remain open.

Initial migration reversal deletes disposable SaaS tables; never reverse it against customer data. For live migrations use the project expand/migrate/verify/contract policy and a verified restorable backup. This scaffold contains no existing-data migration and has no path to modify collector stores.

Dependency evidence: [Django 5.2.18 release notes](https://docs.djangoproject.com/en/5.2/releases/5.2.18/) and [DRF 3.18.3 / security release notes](https://www.django-rest-framework.org/community/release-notes/), reviewed 2026-10-08 PKT. The production collector dependency lock is maintained separately; PR #159 verified compatible maintenance within its existing ranges.

## Login abuse controls

The login form allows at most 10 attempts per normalized username and 20 per connection IP within a fixed 15-minute window. Successful attempts count too; success does not reset an attacker’s budget. Limits apply whether or not an account exists, return a generic 429 and do not trust forwarded address headers. Concurrent PostgreSQL requests lock keyed HMAC fingerprints. Raw usernames/IPs are not stored in these buckets. Rows older than one day are cleaned on login traffic; this is not a guarantee of timed deletion on an idle service. A periodic cleanup/operations policy must be configured before deployment.

A global account bucket can temporarily block a legitimate user during a targeted attack. This bounded development default requires production traffic/abuse review; distributed edge controls, recovery/MFA, proxy-aware address configuration and deployment monitoring remain release work. Do not treat this throttle as production security certification.

## Internal usage reservations

`core.usage` provides atomic reserve/settle/release services for accepted leads, jobs, provider calls and exports. Entitlements default inactive with zero limits and are provisioned only by trusted internal code; there is no customer balance, payment or entitlement mutation API. Active reservations and settled counters share the workspace lock so concurrent requests cannot exceed caps. Repeated requests replay by workspace/key and exact normalized amounts; changed amounts conflict. Settlement cannot exceed the reservation and repeats do not double-count. Release frees reserved capacity and cannot refund settled usage.

These are internal primitives, not an activated paid plan. Counters are cumulative within this development model: billing periods, reset/renewal, signed billing events, reservation expiry/recovery remain separate work. Atomic internal queue/outbox wiring is implemented; there is no consumer. Never expose settlement or entitlement provisioning directly as client-authoritative mutations. No draft route calls these services or dispatches a provider. Real PostgreSQL CI verifies concurrent reservation limits.

## Quality gates

CI checks the isolated CPython 3.12 Linux hash locks, Ruff static lint/import rules and formatting, compilation, Django checks, migration drift, all PostgreSQL regression/concurrency tests, reversible migration and secure non-debug settings. Run `ruff check --config apps/saas/ruff.toml apps/saas` and `ruff format --check --config apps/saas/ruff.toml apps/saas` before changes. The app-local configuration avoids changing the existing collector's tooling or lock.

## Internal durable job intents

`core.jobs.enqueue_job` locks membership and workspace, compares the draft revision, validates the saved normalized search, checks explicit source selections against the trusted internal catalog, reserves server-derived lead/job/provider-call caps and persists a unique outbox intent in one transaction. Duplicate submissions replay the original queued intent; mismatched revisions conflict. `cancel_pending_job` supports draft and queued cancellation only, atomically releasing pre-dispatch reservations and closing the outbox. Running cancellation remains unavailable.

The source catalog defaults disabled and empty. Enqueue requires free-collection cost evidence, rights references, attribution/retention/rate/freshness/failure controls and supported territory/category/status/field metadata. References are supplied by trusted internal provisioning after external review; populated strings are not legal certification. No real policies are seeded, no policy activation/customer submit endpoint is exposed, and no outbox consumer, adapter, scheduler or provider call is enabled. A queued intent does not mean work ran. Source version/fingerprint snapshots must be rechecked alongside membership, entitlement, cancellation and budgets immediately before eventual dispatch. Bounded pre-dispatch attempt leases are implemented; bounded operator-driven reservation expiry is implemented; scheduling and full operational reconciliation remain open.

PostgreSQL CI verifies duplicate enqueue and enqueue/cancel races as well as the previous tenant/owner/login/usage concurrency tests. Failure injection verifies that failed intent persistence rolls back the job and reservation together.

## Internal pre-dispatch leases

`core.attempts` issues one active 60-second lease per outbox with a unique fencing token. Reclaim invalidates the expired token, records another numbered attempt and stops after three attempts. There is no heartbeat or automatic retry loop. Claim/check repeat submitted-actor membership/role, active entitlement, current settled plus reserved caps, normalized request hash, source version/fingerprint and cancellation checks under workspace/source locks. A lease expiring during preflight is rejected. Queued cancellation invalidates the active token and releases pre-dispatch capacity.

These services do not mark work running or invoke a provider; no HTTP route, worker process or background consumer calls them. A lease check is an internal state validation, not authorization or certification for external execution. Future external dispatch needs provider idempotency, explicit dispatch-start/uncertain-outcome records and reconciliation before failover/refund semantics can be enabled. New intents expire after one day. Expired/exhausted pre-dispatch intents retain reservations until an authorized explicit cancellation or the bounded operator cleanup command runs; no background schedule or exact-time deletion is claimed. PostgreSQL CI verifies concurrent lease exclusion alongside earlier races.

## Bounded pre-dispatch recovery

New internal outbox intents receive a server-derived one-day expiry; claims/checks fail at the deadline and lease duration cannot outlive it. Existing rows have a nullable deadline with no invented backfill. Run `python apps/saas/manage.py expire_pending_intents --limit 100` with trusted operator database access to process one batch of at most 100 overdue queued/pending/reserved intents. No command is scheduled or HTTP cleanup endpoint exposed. Each intent locks its workspace, rechecks current state and commits job cancellation, active-token invalidation and reservation release together. Replays are harmless; the command reports examined/expired counts. A failure stops the batch after earlier independently committed intents, which can safely be replayed.

Recovery does not rely on the original actor retaining membership. It skips running, settled, legacy-null-deadline, mismatched-tenant and unsupported state/revision records. Settled usage is never refunded. Unknown outcomes after future external dispatch need a separate reconciliation protocol; this pre-dispatch command cannot certify that recovery. Timely expiry requires an independently configured operational schedule and monitoring. PostgreSQL CI verifies concurrent cleanup commits once, alongside earlier lease and enqueue/cancel races.

## Usage visibility

Owners, admins, members and viewers can read their workspace's server-derived settled counters, outstanding reservations and internal limits. The snapshot takes the workspace lock and rechecks membership to keep quota reads consistent with reserve/settle/release. Unknown entitlements/counters show inactive/zero values without provisioning new balances. `period` and `reset_at` are explicitly null; counters are cumulative in this development model. The session page uses escaped workspace names, semantic table headings and a POST logout form. Cross-tenant and revoked access return 404; client usage mutation is unavailable. Automated route/template tests cover these boundaries; complete browser/accessibility/customer task validation remains open.
