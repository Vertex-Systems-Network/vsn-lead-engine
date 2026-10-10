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
- `/accounts/sign-up/`: self-service account creation (rate-limited with the login buckets); creates an owned workspace and, when `SAAS_STARTER_ENTITLEMENT` is set, a starter allowance. On by default only with `SAAS_DEBUG=1`; production needs `SAAS_SIGNUP_ENABLED=1`.
- `/accounts/password-reset/`: email reset link (Django one-time, 1-hour tokens); same response for unknown addresses; rate-limited per address and IP. Console email in debug; set `SAAS_EMAIL_HOST`, `SAAS_EMAIL_PORT`, `SAAS_EMAIL_USER`, `SAAS_EMAIL_PASSWORD` and `SAAS_FROM_EMAIL` for SMTP.
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

Drafts never enqueue, reserve usage, dispatch source calls, collect data, export, schedule or charge. Source codes and statuses in drafts are requested preferences, not verified capabilities. Internal entitlement/source policy enforcement and atomic usage/outbox services now exist; bounded pre-dispatch leases and current-gate rechecks exist, while external execution/idempotency/recovery contracts are required before any consumer is enabled. Self-service sign-up exists (see `/accounts/sign-up/`); member invitations, real source activation and billing remain unavailable. Existing member role changes and removal are available to authorized owners/admins, with role-only audit records committed in the same transaction. Users are created locally by the management command for development testing only.

## Local end-to-end job fulfilment (development only)

`manage.py run_jobs` fulfils queued jobs: it claims the pre-dispatch lease, records the write-ahead operation, asks the source adapter for leads, drops anything already accepted in the workspace, and settles through the existing candidate review and dual-attested acceptance services. A search that finds nothing new ends with a no-effect receipt that releases the reservation; an adapter error leaves the operation `unknown` with the reservation held.

Two adapters exist: the synthetic `local-fixture` source and `overture`, which serves real Overture Maps Places through the production collector's query code. The Overture worker needs `pip install --require-hashes -r requirements-runtime.txt` (duckdb) and outbound access to the Overture STAC catalog and public S3 release; the manual **SaaS Overture Smoke** workflow (`apps/saas/overture_smoke.py`) checks a real job end to end. Attestations come from an in-process signer whose keys are derived from `SAAS_SECRET_KEY`, registered only for these two sources and only with `SAAS_LOCAL_FULFILMENT=1`, which refuses to start unless `SAAS_DEBUG=1`. Outside debug, run the worker with production keys instead: `python apps/saas/manage.py generate_fulfilment_keys /secure/path/fulfilment-keys.json` writes four random keys to an owner-only (0600) file; set `SAAS_FULFILMENT_KEYS_FILE` to that path for the worker and web processes. Only real sources (`overture`) are registered in this mode, and settings refuse a group/world-readable file. With neither mode the verifier registries stay empty and `run_jobs` refuses to run.

```sh
export SAAS_DEBUG=1 SAAS_LOCAL_FULFILMENT=1
python apps/saas/manage.py seed_local_source                    # synthetic fixture
python apps/saas/manage.py seed_local_source --source overture  # real Overture Places
python apps/saas/manage.py run_jobs --limit 25
```

One job holds at most 25 accepted leads (the v2 batch bound). New sign-ups get a starter allowance in debug (`SAAS_STARTER_ENTITLEMENT`, default `100,10,10,10` = leads, jobs, source calls, exports), so the full flow is sign-up → draft → **Submit job** → `run_jobs` → results/CSV.

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


## Scoped workspace identity read

`GET /api/v1/workspaces/<uuid>/` returns a limited WorkspaceSerializer record
only for a currently authenticated member. It is no-store and supports no POST,
PATCH or DELETE. Anonymous/foreign/revoked actor tests verify denial without
revealing the workspace name. Frontend access is through the fixed trusted
server-side GET transport, never a client-supplied target or authorization
substitute. No administrative workspace edit endpoint is activated.

## Staging readiness (no deployment performed)

The read-only `check_staging` management command is a **fail-closed preflight**,
not a deployment tool or launch certification. On a separately provisioned
staging host, use independently managed secrets, a private PostgreSQL database,
HTTPS and a trusted ingress. Django and Next must share one public HTTPS
origin behind the reviewed reverse proxy; a separate subdomain cannot use
the current host-only Django session cookie. Do not use production collector
credentials or customer data. Prepare the runtime with the existing pinned Python dependencies
and the separately reviewed Overture/duckdb runtime requirements; configure
the Next service with explicit HTTPS backend/public origins.

1. Set `SAAS_DEBUG=0`, `SAAS_SECRET_KEY`, explicit non-local
   `SAAS_ALLOWED_HOSTS`, `SAAS_WEB_ORIGIN`, PostgreSQL `SAAS_DB_*`,
   a real `SAAS_EMAIL_HOST` / `SAAS_FROM_EMAIL` and the SMTP credentials
   required by the chosen provider. Do not enable public sign-up by default.
2. Generate and securely mount the four owner-only fulfilment keys with
   `generate_fulfilment_keys` and set `SAAS_FULFILMENT_KEYS_FILE` in both
   the web and worker processes. The fixture signer is forbidden outside DEBUG.
3. With a tested restorable staging backup and a migration/rollback plan,
   run `python apps/saas/manage.py migrate --noinput` as a **separate,
   authorized deployment operation** (the preflight itself never migrates).
4. Run `python apps/saas/manage.py check --deploy --fail-level WARNING`
   and `python apps/saas/manage.py check_staging`. They must both pass.
   `check_staging` checks local security settings, real-source key
   configuration, SMTP selection, a read-only PostgreSQL query and pending
   migration plan. It hides database exception details to prevent secret leaks.
5. Separately verify the real reverse proxy/TLS/CSRF/cookie behavior, SMTP
   delivery, Overture rights/attribution, worker schedule and queue recovery,
   data retention, backup restore and tenant-access HTTP/browser tests. The
   command cannot certify any of these. Do not open paid billing, production
   collection or public launch on the strength of its output.

No hosting vendor, public domain, SMTP account or production rollout is
provisioned by this change.

## Authenticated daily-time DST preview (no automation)

The read-only HTML route `/workspaces/<uuid>/schedule-preview/` uses current
workspace membership and the existing `core.schedules.resolve_daily` DST policy.
An IANA timezone and HH:MM input show the next three local-day decisions with
actual UTC instants/offsets and gap/ambiguous resolutions. A missing spring clock
time advances to the first valid local minute on the same date; repeated autumn
time uses the earlier UTC instant. A skipped entire civil day is shown as a
no-run decision. The GET form and view cannot create or activate `DailySchedule`
records, `ScheduleOccurrence` records or jobs; they do not reserve usage or call
providers. Read-only review is available to workspace viewers as well as owners.
The action to save, enable and operate a daily customer schedule is deliberately
**not** available; it requires separate role, entitlement, recheck, dispatcher,
audit and deployment acceptance. This preview is not recurring collection.

## Disabled daily schedule plans from drafts

Owners/admins/members may open
`/workspaces/<uuid>/jobs/<draft-id>/daily-plan/` from a **currently saved draft**
and submit an HTML form with an IANA timezone and daily HH:MM. Django CSRF and a
one-hour signed actor/workspace/job-bound idempotency token are required. Only
the server-side immutable saved job search is used; no search input is accepted
from the browser. The internal `create_daily_schedule` service explicitly sets
`enabled=False` even if model defaults change. Exact replay returns the same
plan; divergent settings for the same key return a conflict. Revocation, viewer,
foreign draft, stale job status and non-CSRF requests are denied. The plan save
creates no occurrence/job/outbox, source request, charge, or automatic timer.
The route renders a receipt showing the actual plan state. Enabling and running
a schedule needs separate reviewed user controls, durable scheduler fencing,
entitlement/provider policy checks and release acceptance; do not conflate this
page with active recurring collection.

## Read-only daily plan review

`GET /api/v1/workspaces/<uuid>/daily-plans/` returns a member-authorized,
no-store view of stored daily plan IDs, local clock/timezone, actual enabled
state, revision and creation time. `after=<uuid>` moves through at most 25
records per page in stable ID order. The total counts only the current
workspace. No saved search payload, lead identifiers, user email, source evidence
or external work are exposed. Invalid/repeated cursor arguments are rejected;
write methods are not implemented. Viewer, foreign tenant, membership revocation,
empty results, multiple pages and mutation denial are covered in tests.
Recurring plan activation and scheduled collection remain separate, gated work.

## Read-only partial catch-up allowance (2026-10-10)

The daily plan owner/admin source readiness API and Next report show `affordable_due_job_candidates` and `deferred_due_job_candidates` for the seven-day hypothetical backlog. This is an intersection of leads, jobs and provider-call headroom after settled and pending usage; no ordered dates are selected, no budget is reserved and no work is activated. Disabled plans and unusable entitlements/accounting periods return `null`, never false approval. Existing external legal/source/credentials/release gates remain unverified.

## Daily plan search-scope review

`GET /api/v1/workspaces/<uuid>/daily-plans/<plan-id>/` returns a current-member,
no-store, workspace-filtered read-only plan snapshot. The stored search is
revalidated through the canonical `SearchSerializer`; malformed or tampered
saved configuration fails closed instead of leaking arbitrary JSON. The response
contains the requested search preferences, timezone, local time, revision,
created timestamp and actual enabled flag. It contains no account/lead/contact
records, signer keys or creator identity. It does not accept query parameters or
write verbs and cannot schedule or dispatch work. Foreign, anonymous and revoked
membership, plan-ID swapping, invalid persisted data and mutation denial have
regression coverage.

## Read-only due-plan diagnostics (no scheduler)

After obtaining a verified owner/admin account UUID and workspace UUID, a
trusted operator can run:

```bash
python manage.py inspect_daily_plans --actor <actor-uuid> --workspace <workspace-uuid> --limit 25
```

The command verifies the current actor's membership and owner/admin role,
returns at most 25 plan records, and can continue with `--after <next-uuid>`.
It does **not** write schedules, occurrences, jobs, outbox entries, usage or
provider requests. Results contain only the plan ID, current enabled flag,
revision, redacted status and local-date/DST-resolution candidates. Inactive
plans remain `disabled`. Synthetically enabled plans are rechecked for saved
search fingerprint, timezone, active creator membership and current entitlement,
but any `candidate_due_requires_execution_gates` status is **advisory only**:
it does not certify available quota, provider rights, valid credentials, signed
operator authorization or a working scheduler. No customer scheduling or
collection starts by inspecting plans. Time calculations follow the same seven
local-calendar-date catch-up limit as internal `materialize_daily`; dates already
materialized are omitted. Clock changes between inspection and future execution
require all gates to be freshly checked. Do not automate this command as a
substitute for a fenced, consented scheduler.

## Owner/admin HTTP due-candidate preview

`GET /api/v1/workspaces/<uuid>/daily-diagnostics/` wraps the same read-only
diagnostic as the `inspect_daily_plans` command for an authenticated owner/admin.
It accepts no query except a single optional `after=<uuid>` cursor and returns
up to 25 plans; a viewer receives 403 and a foreign workspace 404. The service
returns redacted plan IDs/revisions/statuses and at most seven local dates with
DST resolution, an explicit `advisory_only` field and a list of execution gates.
No plan is enabled, materialized or dispatched by this endpoint. HTTP and
PostgreSQL tenant/mutation tests cover the authorization boundary; it does not
replace scheduler fencing, source and entitlement acceptance or deployment.

## Owner/admin one-way daily plan pause (no activation)

An enabled plan (such as one changed by a separate operator) can be **disabled**
from `/workspaces/<uuid>/daily-plans/<plan-id>/pause/` using an explicit
CSRF-protected browser confirmation. The form is bound to the authenticated
actor/workspace/plan and a one-hour signed expected revision. Django refetches
current owner/admin rights while holding the workspace/plan locks. A successful
pause increments the revision and writes only `enabled=False` and `revision`.
A stale form fails with HTTP 409. Disabled plans cannot be enabled by this
endpoint. An inactive entitlement is not grounds to refuse an emergency stop.
The lock ordering matches internal daily materialization, with PostgreSQL race
tests proving that no new occurrence can materialize *after* a successful pause.
One due draft may still be created if materialization completed first; existing
drafts, queued jobs, reservations, completed results and previous occurrences
are **not cancelled or erased** by pausing. A separate cancellation or retention
workflow is required for those. No automatic scheduler, provider, recurring
job dispatch, payment or production activation has been introduced.

## Recorded daily occurrence history (read-only)

A current workspace member can inspect
`GET /api/v1/workspaces/<uuid>/daily-plans/<plan-id>/occurrences/` and optionally
continue with `?before=YYYY-MM-DD`. The Django API verifies current membership,
then the exact workspace-scoped plan; it rejects unsupported/repeated parameters,
invalid dates and all write verbs. It returns up to 25 persisted local-calendar
decisions in descending date order, with the recorded plan revision, timezone,
local time, DST resolution, UTC scheduled instant, linked job ID and the job's
current state (if present). Cross-workspace job linkage fails closed. History
contains no saved search criteria, contact records, provider payloads, signer
secrets, usernames or entitlement data. A paused plan's previously created
drafts remain visible: **pause stops future occurrences; it does not retroactively
cancel or delete previous jobs**. Read access cannot materialize or dispatch any
work; an empty history is not proof of an active or inactive production worker.

## Read-only daily source readiness (not approval to execute)

`GET /api/v1/workspaces/<uuid>/daily-plans/<uuid>/readiness/` is current
workspace owner/admin only and does not accept filters, mutation verbs, or
request payloads. It validates the stored plan fingerprint/clock and creator,
checks current entitlement and compares explicit requested source codes with
operator-maintained `SourcePolicy` flags, required evidence/control fields and
scope capabilities **without** returning the confidential policy content.
Its verdict is only `blocked` or `internal_catalog_match_only`; neither is
permission to run. Current usable quota, commercial/legal source rights,
provider credentials/health, operator release and production scheduler safety
remain unverified even when internal fields match. It never enables plans,
reserves usage, creates occurrences/jobs, dispatches providers or takes a
payment. Tenant, role, policy corruption and no-write tests are required.

## Bounded daily tick development harness (default read-only)

A trusted operator can preview the same current-owner/admin workspace-scoped
seven-local-day candidates with:

```bash
python manage.py tick_daily_plans --actor <owner-or-admin-uuid> --workspace <workspace-uuid> --limit 5
```

The command is **dry-run by default**, returns redacted JSON, pages at most five
plans with `--after <next-uuid>`, and never changes a plan, schedule, job,
usage or provider state without an explicit separate development-only gate.

The strictly isolated test-fixture path accepts `--apply-dev` **only if** all
three conditions are set in the trusted local runtime:
`SAAS_DEBUG=1`, `SAAS_LOCAL_FULFILMENT=1`, and
`SAAS_DAILY_DEV_APPLY=1`. The configured source registry must include
`local-fixture`, and each candidate saved plan must request **only**
`source_codes=["local-fixture"]`. No frontend can toggle this setting, and
this command does not enable inactive plans. Test fixtures synthetically
set enabled plans solely for verifying the scheduler boundary.

Only the existing workspace-locking, membership/entitlement-revalidating,
revision-fenced `materialize_daily` function may write an occurrence and
**draft**. No job outbox, worker enqueue, collection, external provider call,
usage reservation or billing is made. If a plan is paused, revoked, modified,
or its entitlement expires between preview and write, that attempt is
blocked and reports only a generic recheck status. Prior occurrences are
not deleted. This is **not** a durable recurring scheduler, active customer
automation, a production loop, or a guarantee of due-date delivery.

Operational promotion requires externally reviewed source rights, active
entitlement/quotas, secure credentials, a long-running fenced scheduler,
recovery/observability, explicit activation controls and release approval.

## Single-job read-only budget headroom estimate

The owner/admin daily-plan readiness API includes a `budget_snapshot` with
settled usage, existing pending reservations, internal entitlement limits,
one hypothetical job's requested leads/jobs/provider calls, and estimated
headroom. The requested provider-call count is the sum of the current internal
selected source policies only when the plan's normalized saved scope and all
policy metadata checks pass. An active accounting period must be open and
cover the current UTC instant. Missing entitlements, missing sources, expired
periods, or invalid scope fail closed; no credential, source evidence or lead
payload is exposed. The estimate is **not** a quota reservation, cannot
authorize a provider, and does not forecast a 7-day catch-up batch; it is a
momentary comparison for *one job*. Actual job enqueue must take fresh DB
locks and revalidate entitlement, source rights, pending usage and capacity.

## Seven-local-day catch-up budget preview (read-only)

An enabled plan's owner/admin source-readiness response also contains
`catch_up_budget_snapshot`. It compares a **hypothetical** maximum seven-local-day
backlog with the current single-job accounting snapshot. The estimator first
removes already-materialized local dates and not-yet-due UTC instants; fully
skipped civil dates have no linked job and consume zero job quota. Up to seven
remaining job candidates multiply the plan's result limit, one job per date,
and internal provider-call budget. No usage reservation or job/source write
occurs. Disabled plans display status `disabled` with zero candidates and no
capacity claim; invalid plans and unverified source policies display
`unavailable`. Results can differ from a future real run because membership,
usage, provider rights and time continuously change. `advisory_batch_fits`
certifies **nothing** about commercial source rights, provider credentials,
recurrence activation, next-month rollover or actual ability to deliver.

## M8 admin access audit review (2026-10-10)

Authorized workspace owners and admins can review recorded membership role changes and removals at `GET /api/v1/workspaces/<uuid>/member-audit/?offset=0` or on the native Next member-audit screen. Entries show timestamp, actor/target UUIDs and previous/new role only; no emails, names, provider credentials or lead content are returned. Reads use existing session authentication, owner/admin checks and 25-row default offset pagination, with explicit no-store headers. No invite, role modification or member removal API is introduced by this view. It is an internal audit UI, not a certified external compliance log.
