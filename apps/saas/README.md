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
- `/workspaces/{workspace_id}/sources/`: bounded read-only application policy configuration, without rights/availability claims.
- `/workspaces/{workspace_id}/search/new/`: CSRF-protected draft form for owners/admins/members, never execution.
- `/workspaces/{workspace_id}/jobs/`: newest-first read-only history, 25-row signed workspace-bound continuation.
- `/workspaces/{workspace_id}/jobs/{job_id}/submit/`: review then signed, revision-bound submit for writers; reserves allowance and queues the draft via `enqueue_job`. Refusals (inactive plan, limits, no covering source) do not queue.
- `/workspaces/{workspace_id}/jobs/{job_id}/cancel/`: review then signed, revision-bound pending cancellation for writers.
- `/workspaces/{workspace_id}/jobs/{job_id}/`: read-only saved scope, recorded status/counts and UTC times.
- `/workspaces/{workspace_id}/usage/`: session-authenticated read-only settled/reserved/limit table.
- `/api/v1/workspaces/{workspace_id}/usage/`: tenant-scoped server-derived counters/limits; no mutation methods.
- `/api/v1/workspaces/`: list only the actor's workspaces; creation atomically installs an owner membership.
- `/api/v1/workspaces/{workspace_id}/members/`: owner/admin list, bounded at 100 rows.
- `/api/v1/workspaces/{workspace_id}/members/{user_id}/`: PATCH role or DELETE membership; last owner protected transactionally; only owners change ownership.
- `/api/v1/workspaces/{workspace_id}/jobs/`: bounded tenant-scoped listing and draft creation.
- `/api/v1/workspaces/{workspace_id}/jobs/{job_id}/`: tenant-scoped detail; foreign IDs return 404.

Draft creation requires an `Idempotency-Key` header. Search JSON accepts countries (US/CA), categories, statuses, required_fields, source_codes and result_limit (1–1000). Unknown fields fail validation. Phone qualification is always included. A key replays the normalized original request; changing its payload returns 409. Membership and write role are rechecked inside the transaction. A workspace row lock and unique tenant/key constraint serialize concurrent duplicate creates.

Drafts never enqueue, reserve usage, dispatch source calls, collect data, export, schedule or charge. Source codes and statuses in drafts are requested preferences, not verified capabilities. Internal entitlement/source policy enforcement and atomic usage/outbox services now exist; bounded pre-dispatch leases and current-gate rechecks exist, while external execution/idempotency/recovery contracts are required before any consumer is enabled. Public registration, member invitations, source activation and billing remain unavailable. Existing member role changes and removal are available to authorized owners/admins, with role-only audit records committed in the same transaction. Users are created locally by the management command for development testing only.

## Local end-to-end job fulfilment (development only)

`manage.py run_jobs` fulfils queued jobs: it claims the pre-dispatch lease, records the write-ahead operation, asks the source adapter for leads, drops anything already accepted in the workspace, and settles through the existing candidate review and dual-attested acceptance services. A search that finds nothing new ends with a no-effect receipt that releases the reservation; an adapter error leaves the operation `unknown` with the reservation held.

Today the only adapter is the synthetic `local-fixture` source, and its attestations come from an in-process signer whose keys are derived from `SAAS_SECRET_KEY`. Both exist only with `SAAS_LOCAL_FULFILMENT=1`, which refuses to start unless `SAAS_DEBUG=1`. Production verifier registries stay empty, so outside this mode `run_jobs` refuses to run.

```sh
export SAAS_DEBUG=1 SAAS_LOCAL_FULFILMENT=1
python apps/saas/manage.py seed_local_source
python apps/saas/manage.py run_jobs --limit 25
```

One job holds at most 25 accepted leads (the v2 batch bound). A workspace still needs an active entitlement; customers queue jobs with **Submit job**. Sign-up is the next slice.

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


## Session job visibility

The read-only job history and detail pages recheck membership under the workspace lock. Viewers may read; foreign/revoked resources return 404. History orders by immutable creation time and UUID descending, fetches at most 26 rows, and displays 25. Continuations expire after one day, bind the workspace and are signed by the application key. Malformed/tampered/expired/foreign-workspace continuations return a generic 400 after tenant authorization. This is continuation through history, not a frozen snapshot; new inserts sort before the current cursor. API pagination stays compatible and unchanged.

Saved scope is escaped text, never clickable provider HTML. Requested limits and recorded results are labeled separately; drafts/queue intents do not imply collection. No hashes, lease tokens, raw errors or provider credentials are rendered. All displayed dates explicitly use UTC. Start/finish/attempt/failure details and retry/cancel/export actions remain unavailable. The table scroll region is keyboard-focusable at narrow widths. Route/template tests are implemented; comprehensive WCAG/customer acceptance is not certified.


## Draft-only search form

The session form accepts supported country/status/field choices, bounded categories/source preferences and result limits through `SearchSerializer`. Phone is always included. Its hidden idempotency token is signed, expires in one day and binds user/workspace; it is independent of the CSRF token, which is also required. Owner/admin/member role is required both before rendering and inside the existing transactional save. Duplicate POST returns the same 303 detail redirect; changed payload with a used token returns 409. Invalid forms preserve input and token and return 400 with escaped field/error summaries. GET creates no database rows. No outbox/reservation, source activation, billing or schedule is triggered.


## Confirmed pending cancellation

Draft/queued job details show a cancellation-review link only to owner/admin/member roles. GET review does not mutate the job. POST requires CSRF and a signed ten-minute actor/workspace/job/revision confirmation; the existing transactional service rechecks membership/write role/state/revision. Only draft or queued jobs can be cancelled; an identical completed cancellation replays safely. Queued cancellation releases unused reserved capacity and invalidates the active attempt. Saved job/scope stays accessible, settled usage is never refunded, and cancelled jobs have no resume action. Unsupported or stale job state returns 409 with a safe review path; tampered/expired/context-mismatched confirmation returns 400. Running work, automatic retries and external providers remain unavailable. Tests use synthetic source fixtures only.


## Source configuration preview

The session source page requires current workspace membership, allows viewer reads and rejects mutation methods. It shows the first 100 global application policy records sorted by code and labels truncation when more exist. Only code/version/configured-switch/free-declaration/capability fields are exposed; rights evidence and operational control references stay private. Missing/corrupt/oversized capability metadata displays as unknown. Enabled/free flags are configuration declarations, not proof of rights, current cost, eligibility or live service. No policy is seeded/activated by viewing it, and no dispatch or billing path is exposed.

## Internal dispatch write-ahead ledger

`core.dispatch.begin_dispatch` commits one operation per saved source, stable provider key (separate from the lease fencing token), request/policy binding and started job/outbox/attempt state atomically. Current preflight gates and deadlines are rechecked. Failed persistence rolls back all evidence/state. Duplicate begins conflict and cannot mint a replacement key. Pending cancellation/expiry cannot release a started reservation. `mark_outcome_unknown` is an authorized internal, idempotent uncertainty marker; it keeps the reservation and never retries, settles or refunds. Empty migration rollback is reversible; once started evidence exists, reversal refuses to erase it without an explicit reconciliation/migration plan.

There is no adapter, network-send permission, consumer or public dispatch endpoint. Confirmed provider receipts, success/no-effect reconciliation, terminal settlement and scheduling are still open. A stable UUID alone does not certify provider idempotency or exactly-once execution. The new Next frontend under `../web/` reads the existing API and retains these Django forms for mutations.

## Internal terminal receipt reconciliation

`core.receipts` verifies bounded exact-byte HMAC evidence against an empty-by-default trusted server verifier registry. It binds workspace/job/source/operation/provider key/request/policy identity, rejects replay conflicts and saves redacted receipt hashes/references only. No keys are accepted from HTTP or provisioned here. This is a synthetic integration contract, not proof that any real provider supports it.

Current owners/admins may reconcile past signed outcomes without reusing an expired worker lease. Partial outcomes retain the whole reservation. Once every source resolves, confirmed no-effect releases unused capacity; any success settles server-derived job usage and bounded signed provider-call usage exactly once. Accepted leads/exports remain zero because no qualification/dedupe/result storage integration exists; receipts cannot mint result counts. Actual adapters remain disabled until that complete acceptance path and provider-specific contracts are verified.

Generic usage release/settlement now refuses reservations attached to job outboxes. Pending cancellation/expiry and verified reconciliation own those transitions. Saved per-operation call limits default to zero for existing ledger rows; those legacy rows fail closed until an explicit reviewed reconciliation/backfill establishes their bounds. Empty migrations are reversible; persisted terminal/cap evidence blocks destructive reversal. PostgreSQL duplicate/conflicting receipt races are a CI merge gate.

## Explicit development accounting windows

`core.periods.advance_period` is an internal owner/admin service, with no customer API, payment event or automatic scheduler. Explicit aware UTC-equivalent windows must contain now and span at most 366 days. Stable workspace keys replay without resetting again. Initial windows refuse nonzero legacy cumulative usage; no history is silently erased. Rollover requires an expired prior window, its exact ending boundary and **no outstanding reservations**, including started/unknown jobs. It atomically archives settled totals, closes the old period and resets the current counter for the new period.

Reservations bind the current window; new reservations/pre-dispatch checks fail after its end. Pending job deadlines are capped at that end. Late signed outcomes may settle their original window; rollover cannot move the counter until they resolve. API/Django/Next usage views show explicit window dates and manual rollover wording, and never advertise an automatic reset. Legacy period-null cumulative mode is preserved. History blocks destructive migration reversal. Signed billing events, subscription pricing/renewal, payments and operational rollover automation remain open.

### Internal daily occurrence foundation

`core.schedules.create_daily_schedule` stores an immutable disabled daily configuration; `materialize_daily` is an internal single-date draft operation, not a worker or API. It snapshots IANA/local time and M3 DST decisions, permits seven local dates of bounded catch-up and retains one occurrence per schedule/date under a workspace lock. Creator and invoking writer authority are rechecked; duplicate calls replay one draft, and skipped whole civil dates record no job. Drafts still require normal entitlement/source/budget enqueue authorization. See [review and remaining activation gates](../../docs/ai/SAAS-DAILY-OCCURRENCES-REVIEW-20261008.md).

### Next session navigation

For localhost Next development, set `SAAS_WEB_ORIGIN=http://localhost:3000` in the Django process; default login/logout then returns to `/dashboard`. The optional value must be an origin only, without credentials/path/query/fragment; production accepts HTTPS only. Omit it for standalone Django defaults. Next's sign-out link opens `/accounts/sign-out/`; confirmation posts the existing CSRF-protected logout route. No GET logout or request-derived external redirect hosts are added. The [session integration review](../../docs/ai/SAAS-NEXT-SESSION-NAVIGATION-REVIEW-20261008.md) records HTTP evidence and remaining native forms/proxy acceptance.

### Native Next forms

Authenticated `draft-form/` and job `cancel-form/` API contexts expose only bounded workspace/job snapshots, masked CSRF and signed bound tokens. Missing CSRF cookies must be seeded through `/accounts/check-session/`. Native Next forms submit to the existing Django handlers; configured successful submissions return to fixed Next job paths. Invalid submissions use the existing Django validation review. `SAAS_WEB_ORIGIN` also explicitly trusts that single frontend Origin for CSRF; wildcard origins are rejected. Shared session cookie scope and production proxy/TLS remain deployment acceptance gates. See [security and compatibility review](../../docs/ai/SAAS-NEXT-NATIVE-FORMS-REVIEW-20261008.md).

### Native source preview API

The read-only workspace `sources/` API reuses the bounded shared catalog preview, omits internal evidence/controls and marks capability data exceeding its per-entry wire budget as unavailable. Responses remain private/no-store and tenant membership is checked. The native Next page displays configured switches and recorded capabilities without granting source/rights/cost/availability authority. See [review](../../docs/ai/SAAS-NEXT-SOURCE-CONFIGURATION-REVIEW-20261008.md).

### Saved job state filtering

The job-list API accepts one supported `status` and optional UUID `after`, returning up to 25 tenant-scoped rows. Unknown/repeated query parameters fail; absent status remains the unfiltered cursor contract. Native Next filter changes reset continuation and pagination retains the selected state. This filters saved job state, not requested business statuses or accepted-lead classification. See [review](../../docs/ai/SAAS-JOB-STATE-FILTER-REVIEW-20261008.md).

Native draft validation uses a bounded five-minute session handoff with the original signed retry identity, preserved inputs and field/error summary. Invalid authority or oversized inputs retain the Django fallback. Native `/account/sign-out` confirms CSRF-protected Django POST logout. Native login and cancellation-error screens remain open. See `docs/ai/SAAS-NEXT-VALIDATION-SIGNOUT-REVIEW-20261008.md` for session retention and acceptance limits.

Native Next sign-in uses explicit browser CSRF bootstrap and direct Django POST with generic fixed failure/limited notices. Native cancellation errors show current job state and require fresh review without issuing confirmation. Frontend origin is opt-in; standalone handlers retain their fallback. See `docs/ai/SAAS-NATIVE-LOGIN-CANCEL-REVIEW-20261008.md` for security, compatibility and acceptance limits.

## Disabled billing ledger and entitlement deadlines

`core.billing.reconcile_billing` persists trusted local binding revisions, redacted event evidence and signed entitlement limits/deadlines atomically. Internal reconciliation defaults disabled, bindings default disabled and verifier keys remain empty. No webhook/provider/payment is available. Current administrator and binding/key/freshness checks apply even to exact replays; new events must be contiguous, with globally unique issuer/event references. Counters, periods, reservations and past-effect settlement are preserved across downgrade/revocation. Deadline/current binding checks now guard capability use, while existing unbound development fixtures remain compatible. Migration rollback refuses to discard billing/deadline evidence. See `docs/ai/SAAS-BILLING-LEDGER-REVIEW-20261008.md` for tested boundaries and remaining production gates.

Readonly `billing_status --actor <current-admin-uuid> --workspace <workspace-uuid>` reports redacted diagnostics only. It never enables or repairs billing. Trusted local operator context and current active admin membership are required; see the billing recovery runbook for preservation and external acceptance gates.

Pure `core.batch_manifest` v3 proof validation has separate empty source/registry authorities and no endpoint/consumer/ORM/network. It preserves v2 intake behavior. See ADR-SAAS-003 for the next durable accounting/pagination gates; synthetic proof shape is not qualification, R2 commit truth or provider permission.
