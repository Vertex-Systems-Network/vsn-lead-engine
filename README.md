# VSN Lead Engine

Zero-paid-discovery-API lead engine for Vertex Systems Network.

## Runtime status

Real lead collection has been **APPROVED** by the user and the runtime gate is enabled.

The scheduled runner enforces a Google credential preflight. If the GitHub
secret `GOOGLE_SERVICE_ACCOUNT_JSON` is missing, the real run exits safely
without collecting or writing leads.

## Daily objective

- Countries: United States + Canada
- 12 categories
- 1,000 accepted unique phone-qualified leads/category/day
- 12,000/day target
- Registry-first writes
- Cross-day dedupe through a pluggable Registry backend
- FREE discovery mode: no paid Places/search API

The 12,000/day figure is a target, not a guarantee; output depends on source
coverage, public contact completeness, query execution, classification precision
and dedupe.


## SaaS milestone roadmap

Snapshot: **2026-10-08 PKT**, reconciled through protected `main` commit `1f63f028` / merged PR #192; internal accepted-result storage/accounting and native Next result reads verified through required checks, 208 PostgreSQL tests and Next/HTTP CI. Live signers/consumers remain disabled. This table covers the new SaaS direction only; the existing P01–P70 production runtime is tracked separately below. Bars are engineering implementation estimates, not customer, legal, provider, deployment or launch certification.

| Milestone | Start date | Status | Progress |
|---|---:|---|---|
| M0 — Current engine audit and SaaS boundary | 2026-10-04 | Complete | `██████████` 100% |
| M1 — User/market and competitor desk research | 2026-10-04 | Desk research complete; external validation pending | `███████░░░` 70% |
| M2 — MVP options, scope and success criteria | 2026-10-05 | Reversible development boundary/defaults accepted; external market/commercial validation still open | `███████░░░` 70% |
| M3 — System, tenant and threat-model design | 2026-10-07 | System/threat, API/data and UX design contracts reconciled; runtime assurance tracked separately | `██████████` 100% |
| M4 — Technology stack and repository decision | 2026-10-07 | Development stack selected: Next.js + TypeScript frontend; Django 5.2 LTS + DRF + PostgreSQL backend, additive current-repo boundary; production vendors/hosting remain gated | `███████░░░` 70% |
| M5 — SaaS foundation: workspace, roles, entitlements and tenant-safety contracts | 2026-10-07 | Isolated Django session/workspace/draft API and initial migrations implemented; owner-safe membership lifecycle and bounded login protection implemented; persisted internal entitlements and atomic usage reservations added; explicit period/rollover and readonly window visibility verified by PostgreSQL concurrency and Next/HTTP CI; billing event/payment reconciliation and complete acceptance remain open | `████████░░` 85% |
| M6 — Source policy, adapters and job orchestration | 2026-10-07 | Source-policy identity and source-aware export authorization hardened; internal source-gated atomic job/reservation/outbox and pre-dispatch cancellation implemented; bounded pre-dispatch lease fencing and membership/entitlement/source rechecks implemented; operator-driven expiry/recovery implemented; internal write-ahead start/unknown ledger verified including PostgreSQL start/cancel races; signed terminal-receipt/whole-job accounting and usage bypass guards verified by PostgreSQL receipt races/migration CI; internal disabled daily occurrence/DST/bounded draft foundation verified by PostgreSQL duplicate/revocation CI; dual-attested internal accepted-result storage and atomic nonzero accounting verified with v1 compatibility and PostgreSQL races; real R2 signer/consumer/live adapter/customer scheduler remain open | `███████░░░` 75% |
| M7 — Lead web workflow, filters and export | 2026-10-07 | UX/export-policy contracts and session workspace overview exist; tenant-safe usage API/page plus bounded chronological job history/detail pages implemented; signed idempotent draft form, confirmed pending cancellation and source configuration preview implemented; Next.js workspace/jobs/detail/usage frontend verified with build/type/transport and disposable HTTP CI; fixed dashboard login/logout return and Next sign-out confirmation verified by real CSRF HTTP/session CI; native draft/cancel and bounded Django contexts verified by PostgreSQL and CSRF/role/replay HTTP CI; native readonly source configuration verified by bounded metadata/tenant/XSS CI; saved-job state filtering and retained cursor/tenant checks verified by PostgreSQL and Next HTTP CI; native draft validation/correction/conflict and sign-out verified by PostgreSQL/Next HTTP CI; native login with explicit cookie bootstrap/attempt caps and cancellation-error review verified by PostgreSQL/Next HTTP CI; signed candidate phone/scope/lineage/retention preflight and redacted tenant-safe event replay verified by 182-case PostgreSQL and Next/HTTP CI (PRs #188–#189); internal accepted-result storage and bounded current-rights results API/native Next view verified by 208 PostgreSQL tests and HTTP viewer/revocation/expiry/escaped-text flows (PRs #191–#192); export, physical retention cleanup and full browser/customer acceptance remain open | `███████░░░` 75% |
| M8 — Admin controls and bounded AI | 2026-10-07 | Not started | `░░░░░░░░░░` 0% |
| M9 — Production readiness, desktop/mobile and launch | 2026-10-07 | Not started | `░░░░░░░░░░` 0% |
| **Overall SaaS direction** | **2026-10-04** | **Design and contract implementation advancing; runtime, provider, validation and launch gates remain open** | **`████░░░░░░` ~47% engineering-plan indicator** |

Progress notes:
- Owner-selected Next.js UI is recorded in [ADR-SAAS-002](docs/ai/ADR-SAAS-002-NEXT-FRONTEND-20261008.md); backend auth/tenant authority remains Django. Percentages describe implemented engineering slices; browser/customer/deployment/release limits remain open.
- M0 is complete from repository audit evidence.
- M1 remains desk research only; no external interviews or customer-demand validation are counted as complete.
- M2 development sequencing/defaults are no longer blocked on technical owner confirmation; external market, pricing, provider-rights and launch decisions remain separate evidence/authorization gates.
- M3 evidence: PR #141 added the stack-neutral system/threat-model baseline, PR #145 added versioned API/data contracts, and PR #150 added the responsive MVP UX interaction contract.
- M4 evidence: PR #146 accepted the reversible development stack of Django 5.2 LTS + Django REST Framework + PostgreSQL with server-rendered progressive-enhancement UI and no new paid service activation.
- M5 evidence: PRs #147 and #149 hardened tenant-bound authorization. `apps/saas/` adds opt-in Django session identity, PostgreSQL models/migrations, transactional workspace ownership and an idempotent draft-job API. The isolated test suite covers cross-tenant reads/writes, stale membership, viewer denial, CSRF, validation, pagination and PostgreSQL duplicate-create concurrency; CI verifies forward/back/forward migration. PR #154 passed all required checks and PostgreSQL concurrency/migration CI. Member list/role-change/removal now re-resolve server membership, preserve the last owner under a workspace row lock, restrict ownership changes to owners and record transactional audit events. PR #155 passed PostgreSQL concurrent last-owner verification. The login form now applies atomic account/IP attempt caps using expiring keyed fingerprints, generic rate-limit responses and CSRF protection; deployment abuse/recovery review remains open. PR #156 passed PostgreSQL concurrent login-budget verification. Persisted internal entitlements default inactive/zero; usage reserve/settle/release services enforce tenant scope, replay conflicts and atomic hard caps. Signed billing activation/reconciliation remains unavailable; later PRs added internal outbox and explicit manual accounting periods. PR #157 passed PostgreSQL concurrent reservation-cap tests. The isolated quality workflow now includes pinned Ruff lint/format gates, compilation and the existing migration/security/concurrency suite. This is development foundation, not deployed persistence or SaaS production certification.
- M6/M7 evidence: PR #148 separated search eligibility from source-aware export authorization and added export-field policy tests. No provider adapter, customer scheduler, production SaaS database, billing gateway, or deployed web UI is claimed. Draft creation cannot dispatch providers or consume paid usage.
- Existing production collector, Google Sheets delivery and R2 dedupe authority remain isolated from the SaaS work. A separate compatible dependency maintenance change regenerates the reviewed Linux/CPython 3.12 hash locks to replace failed Dependabot #136; collection algorithms/configuration, production secrets and quota claims are unchanged.
- Project-specific tenant identity, draft idempotency and usage requirements now trace to delivered files, migrations, merged PRs and PostgreSQL tests in `config/traceability/requirements-traceability.json`; production/customer acceptance remains partial.
- Overall progress is an engineering planning/implementation indicator, not a claim of customer demand, source rights, coverage, legal compliance, paid-service activation, deployment or launch readiness.

## Daily dated workbook model

Every real event resolves the current date in `Asia/Karachi` and targets
exactly one Google Sheet named:

```
US + Canada Business Leads — YYYY-MM-DD
```

Example:

```
US + Canada Business Leads — 2026-09-24
```

Event behavior:

1. search the configured Drive folder for the exact current-date title;
2. if it exists, reuse it and append new accepted leads;
3. if it is missing, attempt to copy the configured clean daily template into
   the same folder using that exact title;
4. initialize/repair `Overview` plus the 12 category tabs;
5. keep the legacy Master Registry as a frozen migration/audit snapshot; R2 is the permanent cross-day dedupe authority.

Because the configured destination is a user-owned **My Drive** folder, Google
service accounts may be refused permission to create/own a new file even when
they can edit shared files. A user-owned daily precreator is therefore used as
the creation safety net; the GitHub runner still performs exact-title discovery
on every event.

Historical workbooks use a fixed Tracking Date cell instead of `TODAY()`, so a
September 27 workbook continues showing September 27 counts when opened later.

### Daily workbook readiness certification

A dedicated GitHub workflow runs at **07:50 Asia/Karachi** every day, before the
08:00 primary quota window:

1. validate runtime configuration;
2. require the Google service-account credential;
3. resolve the exact current-date workbook;
4. if missing, attempt the normal clean-template copy;
5. self-heal Overview/category tabs and P4 metric rows;
6. read category/country counts and report whether the daily quota is already complete.

The same check is available manually as:

```
python -m vsn_lead_engine.cli workbook-ready
```

If My Drive ownership prevents service-account creation and the user-owned
precreator has not produced the file yet, readiness now enters a bounded recovery
window instead of failing on the first error.

### P6 readiness recovery and incident telemetry

The 07:50 readiness job now runs the recovery command:

```
python -m vsn_lead_engine.cli workbook-ready-recover --attempts 3 --delay-seconds 60
```

Behavior:

- first success returns `ready`;
- a later retry success returns `recovered` and preserves prior failure details;
- production uses at most **3 attempts**, separated by **60 seconds**;
- each failed attempt records timestamp, exception type and message;
- exhausted recovery returns `incident` with the final error and exits non-zero;
- GitHub Step Summary always publishes the readiness state, attempts used, workbook
  details when available, and every recovery failure;
- missing or invalid telemetry is itself treated as an incident;
- no lead discovery, enrichment, quota write or R2 mutation occurs in this recovery path.

### P7 free-source breadth expansion

The free Overture discovery surface now covers **56 configured US/Canada metro
markets** and **16 deterministic candidate partitions**.

Major additions include New York City, San Francisco, San Jose, Sacramento,
Orlando, Washington DC, Baltimore, Raleigh, Pittsburgh, Cleveland, Cincinnati,
Indianapolis, Kansas City, St. Louis, Salt Lake City, New Orleans, Mississauga,
Quebec City, Victoria, Surrey, London (Ontario), Kitchener-Waterloo, Regina and
Moncton.

This increases the available free candidate pool without changing the 1,000
accepted leads/category/day ceiling. Scheduler rotation still limits each cycle
to its configured shard budget, so broader coverage is consumed over repeated
quota events rather than increasing one-run load without bound.

Runtime validation now rejects duplicate markets, unsupported countries,
out-of-range latitude/longitude values and invalid bbox ordering.

### P8 adaptive yield routing

Multi-cycle quota events now learn which **category + metro** combinations are
producing accepted leads and feed that information into the next cycle in the
same GitHub Actions process.

The adaptive router is deliberately in-memory only:

- no new database;
- no additional R2 writes;
- no cross-day hidden state;
- no paid API dependency.

For each attempted category/metro shard the engine accumulates visits,
discovered candidates and accepted leads. P37 makes the default adaptive score
**accepted leads per shard attempt** plus a small exploration bonus, so routing
optimizes daily quota throughput instead of favoring tiny shards with a perfect
accepted/discovered percentage. The legacy conversion-ratio score remains
available through runtime configuration for rollback.

Important fairness rules remain unchanged:

- US/Canada country interleave remains controlled by the existing country-balance
  scheduler;
- underfilled categories still receive the strongest category weight;
- unseen metros receive an exploration bonus, so a previously successful metro
  cannot permanently starve new markets;
- cursor and partition rotation continue to move through fresh source cohorts;
- the adaptive score is emitted per shard for auditability.

Production settings:

- adaptive yield routing: **enabled**;
- exploration bonus: **0.15**.

### P9 compact daily adaptive state

Adaptive routing now keeps its small aggregate state across hourly quota events
for the same Asia/Karachi date.

Storage model:

- key: `<registry-prefix>/adaptive-yield/v1/YYYY-MM-DD.json`;
- payload contains only category/country/region/city routing keys plus
  `visits / discovered / accepted` counters and, when available, one compact
  64-bit same-day candidate-partition mask;
- no business name, phone, email, website or raw lead data is stored;
- one R2 GET at event startup;
- at most one R2 PUT at event completion;
- if the quota is already complete or no shard was attempted, no state PUT is
  performed;
- the next date uses a different object key, so learning resets naturally each
  day;
- production state is capped at **1,500 routing entries**.

The existing GitHub Actions concurrency group serializes runs on `main`, so
scheduled and assistant-triggered production events do not update the same daily
state concurrently.

Adaptive state is non-authoritative optimization data. A missing, malformed or
temporarily unreadable state object fails open: lead collection continues with
fresh in-process learning and telemetry records the state error. If actual shard
work then succeeds, the final single save self-heals the daily state object.

At the normal 08:00–23:00 hourly schedule this adds at most roughly one compact
Class-A state write per productive event, instead of per-lead or per-shard
writes.

### P10 schedule alignment and missed-run recovery

The repo-native GitHub Actions cadence is now aligned to the configured
Asia/Karachi production window:

- primary cron: **03:00–18:00 UTC**;
- local equivalent: **08:00–23:00 PKT**;
- cadence: **hourly at minute 00**;
- scheduled workflow executions call `run --scheduled`.

Scheduled runs pass through a local-time gate before collection. A delayed run
that still lands inside the configured 08:00–23:59 PKT window is allowed to
continue and simply fills the **current live shortfall**. If an old scheduled
event is delayed beyond the production window or into the next date, it exits
cleanly instead of accidentally starting collection against the wrong dated
workbook.

The separate quota supervisor is intentionally offset after the native run. It
checks the live dated workbook later in the hour and only creates an
assistant-trigger commit when quota is still short. This turns the supervisor
into a missed-run / failed-run recovery path instead of a second primary
scheduler.

Because every real run re-reads current Sheet counts, R2 dedupe and same-day
adaptive state, catch-up is idempotent with respect to quota: the next healthy
run resumes the remaining category shortfall rather than replaying a fixed
hourly batch.

### P11 daily incident / health ledger

Operational health is persisted in one compact date-scoped R2 object:

```
<registry-prefix>/health/v1/YYYY-MM-DD.json
```

The ledger records operational metadata only:

- 07:50 readiness status and recovery attempts;
- native scheduled runs;
- :20 recovery-trigger runs;
- manual real runs;
- blocked runs such as a missing Google credential;
- accepted/discovered totals, cycles and category counts/shortfalls;
- schedule delay and same-day catch-up slot;
- adaptive-state load/save health;
- sanitized exception type/message;
- first quota-completion timestamp.

It does **not** accept raw lead payloads. The serializer uses an explicit
allow-list, so business names, phones, emails, websites and arbitrary lead
objects are dropped even if a caller accidentally supplies them.

Production cap: **96 events/day**. Replayed GitHub run IDs are de-duplicated,
so a workflow rerun cannot create duplicate audit events for the same
run-attempt identity.

Useful audit command:

```
python -m vsn_lead_engine.cli health-show
python -m vsn_lead_engine.cli health-show --date 2026-09-28
```

Health logging is non-authoritative and fail-open. A temporary R2 health-ledger
failure is reported in run telemetry but does not block otherwise-valid lead
collection, Google Sheet commits or packed-v2 dedupe.

### P12 protected-main governance

The repository now carries a versioned GitHub ruleset policy at
`.github/main-protection-ruleset.json` plus apply/verify tooling.

Target policy for `main`:

- all changes must reach `main` through a pull request;
- required status check: **validate**;
- required status check policy: **strict / branch must be current with main**;
- allowed merge method: **squash only**;
- unresolved review conversations block merge;
- stale reviews are dismissed after new reviewable pushes;
- force pushes are blocked;
- branch deletion is blocked;
- linear history is required;
- no blanket bypass actor is configured;
- approval count remains **0** so the automated recovery PR path is not dependent
  on a second human reviewer.

The :20 quota recovery supervisor has been moved from direct-main trigger writes
to a feature-branch + PR + CI + exact-head merge flow, so enabling the ruleset
does not break missed-run recovery.

Protection controller:

```
python scripts/apply_main_protection.py
python scripts/apply_main_protection.py --confirm
python scripts/verify_main_protection.py
```

`.github/workflows/main-protection-controller.yml` self-heals and verifies the
live ruleset using repository secret `GH_ADMIN_TOKEN`, which has repository
**Administration: write** permission. Live repository ruleset
`VSN Main Protection` is now active on `main`; the controller continues to
run on policy/controller changes and the daily drift schedule.

### P13 rolling historical yield prior

The first quota run of a new day no longer has to start fully cold. A compact
cross-day routing profile is stored at:

```
<registry-prefix>/adaptive-yield/v2/history.json
```

The profile contains only category/country/region/city routing keys plus
aggregate `visits / discovered / accepted` counters. No lead name, phone,
email, website or raw record is stored.

Behavior:

- one small history GET at event startup;
- historical counters are used with **0.25 prior weight**;
- same-day P9 observations are added at full weight and therefore dominate as
  the current day accumulates evidence;
- country interleave, category completion weighting, exploration bonus and exact
  R2 dedupe remain unchanged;
- previous history decays by **0.75** when a new completed day is learned;
- the rolling profile is capped at **1,500 entries**;
- the profile writes only when the daily quota reaches `complete`;
- the same completion date cannot write the historical profile twice;
- load/save errors fail open and are visible in P11 health telemetry.

This provides a useful 08:00 routing prior while preventing old source behavior
from permanently dominating new-day discovery.

### P14 same-day zero-yield route cooldown

The fixed shard budget now avoids repeatedly spending slots on category+metro
routes that have already produced enough same-day evidence of exhaustion.

Production cooldown threshold:

- at least **2 same-day visits**;
- at least **100 same-day discovered candidates**;
- at least **4 distinct same-day candidate partitions** observed;
- **0 accepted leads**.

When those conditions are met, that category+metro route is deferred from the
current plan if another metro in the same country/category remains available.

Guardrails:

- only **same-day P9 evidence** may trigger cooldown; P13 historical priors can
  influence ranking but can never hard-defer a route;
- if every metro for a country/category meets the cooldown threshold, the
  scheduler automatically falls back and re-enables all of them;
- any route with at least one accepted lead remains eligible;
- US/Canada country interleave and underfilled-category weighting stay
  authoritative;
- the exploration bonus remains active for unseen routes;
- max shard attempts, cycles, candidate limits and API budgets are unchanged.

P11 health telemetry records the number of routes deferred so zero-yield
cooldown behavior can be audited without storing lead PII.

### P15 fair weighted category coverage

Category urgency weights remain **3× / 2× / 1×**, but repeat slots are now
layered instead of clumped.

For example:

```
weights: A=3, B=2, C=1

old: A, A, A, B, B, C
new: A, B, C, A, B, A
```

Operational effect:

- every pending category gets one pass before higher-weight categories consume
  their repeat slots, when the shard budget is large enough;
- categories with lower completion still receive the same total extra weight;
- if the shard budget is smaller than the number of pending categories, the
  existing completion sort still sends the lowest-progress categories first;
- country interleave, metro adaptive scoring, P14 cooldown and partition
  rotation remain unchanged;
- max shard attempts and API budgets do not increase.

With 12 equally underfilled categories and an 18-shard cycle, the first 12
slots can now cover all 12 categories instead of clumping the first six
three times each. P11 health telemetry records `categories_attempted` for
live audit.

### P16 fair enrichment budget distribution

The official-website enrichment budget remains fixed at **160 candidates per
event**, but one shard call can now consume at most **12** of those candidates.
This prevents early category/metro shards from exhausting the entire free
network budget before P15's first-pass category coverage reaches later
categories.

Common Crawl keeps the existing **8 lookups/event** ceiling and adds a
**1 lookup/call** cap.

Budget accounting distinguishes:

- event-budget skips;
- per-call fairness skips;
- Common Crawl event-budget skips;
- Common Crawl per-call skips.

The existing aggregate `Enrichment Budget Skips` metric remains compatible.

No source, timeout, worker, response-size or total event budget was increased;
P16 redistributes the same free enrichment capacity more fairly.

### P17 pre-enrichment R2 duplicate filter

Website-only candidates now receive an advisory **read-only R2 collision check**
before official-site/Common Crawl enrichment.

The prefilter uses fingerprints that already exist before phone recovery:

- provider/source ID;
- normalized website domain;
- business + city + region;
- place ID when available.

If one of those exact permanent/pending fingerprints already blocks the lead,
the candidate is rejected as a duplicate before spending website-enrichment
budget.

Safety model:

- only phone-missing candidates with an official website use the prefilter;
- P17 performs no new R2 Class-A writes;
- the normal post-enrichment R2 collision check still runs for survivors, so a
  recovered phone fingerprint and any race/pending change are checked again;
- final registry reservation remains the authoritative commit-time lock;
- the feature can be disabled with
  `runtime.r2_pre_enrichment_prefilter_enabled=false`.

Overview and P11 health telemetry expose `Remote Prefilter Duplicates` so the
saved network work can be measured separately from total duplicate rejections.

### P18 source-batch pre-enrichment dedupe

Each individual source response is now collapsed locally before any official-site
or Common Crawl enrichment.

The dedupe dimensions match the existing exact lead semantics:

- place ID;
- source/provider ID;
- normalized domain;
- normalized phone + business name;
- business + city + region;
- derived unique key.

When duplicate candidates exist in the same source response, the engine keeps the
strongest representative using this preference order:

1. already-valid phone;
2. official website present;
3. richer public contact metadata;
4. original source order as the deterministic tie-breaker.

Guardrails:

- this is fully in-process and adds **zero** network/R2/Google calls;
- it never replaces P17 cross-day R2 filtering;
- post-enrichment exact collision checks and commit-time R2 reservation remain
  authoritative;
- it can be disabled with `runtime.source_batch_dedupe_enabled=false`.

Overview and P11 health telemetry expose `Source-Batch Duplicates` separately
while those rows still count toward total duplicate rejections.

### P19 packed-v2 advisory read cache

Repeated P17/final collision checks now reuse packed-v2 shard reads inside the
same registry-index lifetime.

Production settings:

- advisory packed-read cache: **enabled**;
- max cached pack objects: **128**.

Correctness boundaries are explicit:

- `collision_keys()` may reuse cached packed reads;
- `reserve_pending()` always uses fresh packed reads under the registry lock;
- pack merge/write paths use fresh reads before writing;
- audit paths remain fresh by default;
- own pack writes refresh the cache immediately;
- smoke namespace cleanup explicitly clears the advisory cache before verifying
  post-cleanup collisions.

This lowers repeated packed-object GETs during the hourly event without allowing
stale advisory state to become commit-time dedupe authority.

### P20 registry cache health telemetry

Each production event now exposes aggregate packed-cache telemetry:

- cache enabled state;
- cached pack entry count;
- advisory cache hits;
- advisory cache misses.

P11 writes only these counters into the PII-free daily health ledger. Pack keys,
fingerprints and lead values are not persisted in health telemetry.

This makes P19 measurable on real production runs without changing the cache,
registry, source, quota or enrichment behavior.

### P21 legacy objects-v1 advisory cache

Historical objects-v1 fingerprints remain authoritative and readable, but
repeated advisory collision checks no longer repeat the same R2 HEAD request
for every unchanged token within one event.

Production behavior:

- event-local legacy existence cache enabled through the existing advisory
  cache switch;
- maximum cached legacy token states: **4,096**;
- positive and negative existence results are cached only for advisory
  `collision_keys()` checks;
- `reserve_pending()` bypasses advisory caches and performs fresh packed-v2
  and legacy-v1 checks under the registry lock;
- audit paths remain fresh;
- `import_rows()` clears legacy advisory state after historical object
  mutations;
- smoke cleanup clears both packed and legacy advisory caches.

P11 health telemetry now records separate legacy cache entries, hits and misses
so the reduction in historical R2 fallback reads can be measured independently
from packed-v2 cache efficiency.

### P22 pending-marker advisory cache

Repeated advisory collision checks also reuse the compact set of currently
reserved pending fingerprints instead of re-listing the R2 `pending/` prefix
for every P17/final dedupe pass.

Correctness boundaries:

- pending cache is event-local and advisory only;
- `collision_keys()` may reuse cached pending tokens;
- `reserve_pending()` always performs a fresh pending scan under the registry
  lock before accepting a reservation;
- own reserve, activate, retryable rollback and reconciliation mutations
  invalidate the pending cache;
- the cache can be disabled independently with
  `registry.pending_read_cache_enabled=false`;
- smoke cleanup clears it together with the packed/legacy advisory caches.

P11 health telemetry records pending cache enabled state, token entries, hits
and misses. This reduces repeated R2 LIST/GET work without allowing stale
pending state to become commit-time dedupe authority.

### P23 contact-stratified Overture cohorts

The fixed Overture shard budget remains **500 candidates**, but candidate
selection now prefers direct-phone businesses while reserving part of the same
cohort for website-only enrichment candidates.

Production split:

- **80% phone-first preferred band**;
- **20% website-only exploration reserve**.

The reserve is a preference, not unused capacity: when either contact band does
not contain enough candidates, the remaining ranked rows can still fill the
existing shard limit.

Guardrails:

- the existing 16 deterministic Overture hash partitions remain authoritative;
- ranking inside each phone/non-phone contact band is deterministic by
  `hash(id)`;
- taxonomy-first classification, country filtering, permanently-closed
  filtering and the Python defense-in-depth classifier remain unchanged;
- website-only candidates still pass P16 bounded enrichment;
- direct phones and recovered phones still pass normal phone validation and
  exact R2 dedupe;
- no extra source query, paid API, shard attempt or candidate budget is added.

The reserve fraction is configurable as
`sources.overture.website_candidate_reserve_fraction` and production uses
**0.20**.

### P24 source contact-mix telemetry

P23's selected cohort is now measurable without adding any source request.

For every source attempt the engine records:

- candidates that arrived with a source-provided phone value;
- candidates that arrived without a phone but with an official website.

The same counters are aggregated across cycles and persisted as:

- `Source Phone Candidates`;
- `Website-Only Candidates`.

P11 stores the PII-free event totals as
`source_phone_candidates` and `website_only_candidates`.

These counters intentionally describe the **raw source contact mix**. Phone
validity and recovered-phone success remain separate existing metrics, so an
invalid source phone cannot be confused with a valid accepted phone.


### P25 partition-aware zero-yield cooldown

P14 cooldown now accounts for the 16 rotating Overture candidate partitions
inside each category + metro route.

A route is not hard-deferred merely because two early partitions produced no
accepted leads. Production cooldown requires the existing zero-yield thresholds
plus at least **4 distinct same-day partitions**.

Implementation:

- P9 daily adaptive state stores an optional compact 64-bit partition mask;
- repeated observations of the same partition do not increase coverage;
- old three-counter P9 payloads remain backward compatible;
- the partition mask is same-day evidence only and is not promoted into the P13
  historical routing prior;
- P11 health telemetry exposes `adaptive_partitions_observed`;
- the existing all-routes fallback still prevents category/country starvation.

This protects unexplored source cohorts without adding source calls, shard
attempts, paid APIs, per-lead state writes or a second daily state object.

### P26 user-owned daily workbook bootstrap

My Drive ownership is handled outside the service-account write path. A
user-owned precreator ensures the exact dated workbook exists before the GitHub
lead engine needs it.

Operational contract:

- the external precreator runs at **07:40 Asia/Karachi**;
- it copies the configured clean native Google Sheets template into the lead
  folder only when the exact dated title is missing;
- duplicate dated workbooks are never intentionally created;
- GitHub/service-account production keeps using the existing workbook once it
  exists;
- when a copied user-owned workbook is still blank and its Overview does not
  use the current engine schema, the engine safely initializes it in place;
- blank bootstrap refreshes category headers, clears stale template lead rows,
  writes the current Overview schema and enforces the configured spreadsheet
  timezone;
- an already-populated dated workbook never has category lead rows reset or
  wiped merely because its Overview is old; only the generated Overview schema
  is rebuilt, with matching operational counters preserved when available;
- the behavior can be disabled with
  `runtime.precreated_workbook_bootstrap_enabled=false`.

This closes the My Drive service-account ownership gap without moving the
production ledger, weakening R2 dedupe, or requiring a paid Drive tier.

### P27 bounded Overture query wall time

Every individual Overture DuckDB/httpfs discovery query now has its own
wall-clock budget instead of relying only on the 30-minute GitHub job timeout.

Production behavior:

- `sources.overture.query_timeout_seconds = 45`;
- a timer calls DuckDB's supported connection `interrupt()` when the budget is
  exceeded;
- the interrupted search raises a bounded timeout error and contributes to the
  normal source-error telemetry;
- source timeouts are **not retried inside the same shard**, avoiding three
  repeated waits on the same stalled remote query;
- ordinary transient source errors keep the existing bounded retry/backoff
  behavior;
- rotated shards and later cycles remain the next exploration opportunity;
- the GitHub job timeout remains the final event-level fail-safe.

This reduces the chance that one remote Parquet/httpfs query monopolizes an
hourly production event while preserving taxonomy, phone validation, quota and
R2 dedupe semantics.

### P28 graceful event wall-clock budget

Production collection now stops itself before GitHub's 30-minute hard job
timeout can terminate the Python process while it owns an R2 lock.

Production behavior:

- `runtime.event_wall_time_seconds = 1500` (25 minutes);
- `runtime.event_deadline_guard_seconds = 60`;
- the engine will not start another shard/source when the remaining event budget
  is inside the guard window;
- already accepted in-memory leads still go through the normal R2 reservation
  and Google Sheets commit path before the run exits;
- the result is marked `partial-budget`, not an incident, so the next hourly
  event can resume from live sheet + R2 state;
- sources, registry clients and enrichers close through the existing `finally`
  path;
- the 30-minute GitHub job timeout remains only the final emergency fail-safe.

This reduces orphan-lock risk from forced runner termination without increasing
paid API usage or weakening exact cross-day dedupe.

### P29 process-level watchdog

P28 remains the graceful in-process budget, but production evidence showed that a
native/blocking call can prevent Python from reaching its deadline checks. A
second, independent parent-process watchdog now wraps every **real** lead event.

Production behavior:

- the normal engine still gets **25 minutes** to stop cleanly and commit any
  accepted in-memory leads;
- the parent watchdog allows **26 minutes** for the child process;
- if the child is still blocked, the parent sends termination to the whole child
  process group, waits up to **20 seconds**, then force-kills it if required;
- watchdog expiry returns exit code `124` so GitHub marks the event failed and
  the existing recovery supervisor can retry the live shortfall;
- the parent records a date-scoped health incident after regaining control;
- R2 pending markers and stale-lock recovery remain the crash-recovery authority
  for a child that is terminated during a write boundary;
- GitHub's 30-minute job timeout remains the final platform fail-safe, with
  several minutes reserved for watchdog cleanup and incident persistence.

Scheduled, assistant-triggered and manual **real** runs use
`supervised-run`. Manual dry runs remain direct because they do not own the
production write path.

### P30 live execution heartbeat telemetry

Production runs now emit compact flushed JSON heartbeats at expensive execution
boundaries so a stalled GitHub Actions job can be localized from its last
completed phase instead of waiting for a final result.

Telemetry includes only operational fields such as phase, category, country,
region/city, source name, partition number, candidate counts, collision counts,
retry counts and elapsed time. It does **not** emit business names, phones,
emails, websites, addresses or other lead payloads.

Instrumented boundaries include:

- event and cycle start/end;
- dated-workbook/quota state loaded;
- every source search start/end;
- R2 prefilter and final collision checks;
- enrichment start/end;
- per-category Registry/Sheet commit start/end;
- event cleanup start/end.

Each line is flushed immediately. If a native call blocks, the final visible
heartbeat identifies the active boundary while P29 remains the independent
hard process watchdog. The telemetry is logs-only and adds no R2, Google API,
paid-source or per-lead storage writes. It can be disabled with
`runtime.progress_telemetry_enabled=false`.

### P31 read-only Overture taxonomy breadth audit

Motorbikes is currently the extreme quota outlier, so category expansion is now
driven by live taxonomy evidence instead of guessed labels.

The command:

```
python -m vsn_lead_engine.cli taxonomy-audit --max-geographies 8 --rows-per-geography 250
```

reads the current Overture Places release across a deterministic US/Canada
balanced metro sample and reports aggregated taxonomy buckets for
motorcycle/motorbike/scooter/powersports/ATV-like records.

Safety and cost properties:

- no Google Drive or Sheets access;
- no R2 access or mutation;
- no lead writes or quota changes;
- no paid API;
- no raw business names, phones, emails, websites or addresses in output;
- bounded per-geography rows and the existing Overture query timeout;
- output identifies current-rule coverage vs unrecognized taxonomy buckets and
  their aggregate phone/web availability.

A dedicated `Overture Taxonomy Audit` workflow can run this evidence probe
without starting the production lead engine. Any Motorbikes taxonomy expansion
must be justified by this audit before entering the production classifier.

### P32 evidence-backed Motorbikes rental taxonomy correction

The P31 live Overture audit on release `2026-09-23.1` found two canonical
Motorbikes-adjacent business taxonomies that the production classifier was
missing:

- `motorcycle_rental_service`;
- `scooter_rental`.

Across the bounded eight-metro P31 sample these two exact taxonomy buckets
contained **40 rows**, including **39 phone-bearing rows**. They are now accepted
as Motorbikes because they are explicit vehicle rental taxonomies, not merely
business names containing motorcycle-related words.

The expansion deliberately does **not** include adjacent or name-only buckets
such as ATV tours, driving schools, auto dealers, coffee shops, bicycle stores
or general automotive repair. Taxonomy-first precision remains authoritative.

P31 also showed that the existing classifier already recognized hundreds of
phone-bearing motorcycle dealer/repair/parts rows in the small audit sample.
Therefore this correction is a real coverage fix, but it is not treated as the
full explanation for the low daily Motorbikes count. P30 heartbeat evidence from
the next current-main production run remains the next root-cause step.

### P33 production-equivalent Motorbikes source probe

P31 proved that the current Overture release contains hundreds of relevant
phone-bearing motorcycle businesses in a small metro sample, while the dated
workbook still showed only a handful of accepted Motorbikes leads. P33 isolates
the production discovery layer without touching quota state.

The probe calls the same `OverturePlaceSource.search("Motorbikes")` method used
by real collection, with the same **16-way hash partition**, candidate limit and
query timeout. It samples four country-balanced metros and two deterministic
partitions per metro.

The output is aggregate-only:

- candidates returned;
- source-phone vs website-only candidates;
- partition and metro;
- elapsed query time;
- bounded error type/message.

It never emits lead names or contact payloads and performs **zero Google Sheet
or R2 operations**. The isolated `Overture Production Source Probe` workflow
can therefore distinguish partition/query failure from later dedupe/enrichment
or commit loss before changing production routing.

### P34 read-only Motorbikes R2 collision probe

P33 certified the exact production Overture source path: eight real 16-way
partition queries returned **112 Motorbikes candidates**, including **109 with
source phones**, with zero query failures. P34 moves the diagnostic one boundary
downstream.

The collision probe runs those production-equivalent searches and checks the
resulting candidates through the production packed-v2 `collision_keys()`
lookup. It reports per metro/partition and in aggregate:

- candidate unique tokens;
- R2 collisions;
- surviving unique candidates;
- collision rate;
- source and collision-check timing.

This operation is strictly read-only: it does not reserve pending rows, acquire
the packed write lock, activate fingerprints, modify R2 objects, touch Google
Sheets, or change quota state.

### P35 critical-deficit rescue scheduling

P34 proved that the Motorbikes bottleneck is not an empty Overture source and
not primarily an R2 exhaustion problem: the bounded production-equivalent
probe returned 111 unique candidates with 84 R2 survivors. The remaining
problem is allocation: a category at only a few percent of quota previously
received at most the same 3x weight used for every category below 25%.

P35 keeps the existing layered fairness invariant—every pending category gets
one shard before any category repeats—but adds configurable urgency tiers inside
the same fixed shard/event budget:

- below 10% complete: **6x**;
- 10% to below 25%: **4x**;
- 25% to below 50%: **2x**;
- 50% or more: **1x**.

This does not increase `max_shard_attempts`, the 25-minute event budget, Google
Sheet writes, R2 writes or paid API usage. It only reallocates existing shard
slots toward the categories that are furthest from their required 1,000/day
quota. The feature is runtime-configurable and can be disabled to restore the
legacy 3x/2x/1x behavior.

### P36 partition-level adaptive yield routing

P34 showed that Motorbikes performance can differ dramatically between hash
partitions inside the same metro: sampled partitions ranged from fully collided
to dozens of R2 survivors. Before P36, adaptive routing learned only at the
category+metro level; the 16-way partition id was retained only as a coverage
bitmask.

P36 reuses the existing compact daily/historical adaptive-yield objects and
adds partition-scoped keys for every actually queried cohort. Each partition
tracks visits, discovered candidates and accepted leads. At search time:

- productive known partitions can outrank weak ones;
- unseen partitions keep the normal exploration bonus and are preferred over
  repeatedly observed zero-yield partitions;
- cursor rotation remains the tie-breaker, so equal/unseen cohorts still move;
- disabling `runtime.adaptive_partition_yield_routing` restores the previous
  deterministic cursor+attempt partition choice.

No new database, bucket, Google Sheet write, paid API call or event-time
increase is introduced. P36 changes only which already-budgeted Overture hash
cohort is queried.

### P37 quota-throughput adaptive scoring

Production diagnostics exposed a scoring mismatch for sparse categories.
The older adaptive score used accepted/discovered. That is a conversion
percentage, not a quota-throughput metric: a shard returning 2 accepted leads
from 2 candidates could outrank a shard returning 30 accepted leads from 40
candidates even though the latter closes the 1,000/day target much faster.

P37 changes the default adaptive score to accepted leads per attempted shard
plus the existing exploration bonus. The same score is used for metro ranking
and P36 partition ranking. Existing daily and historical R2 counters are reused,
so no migration or extra state writes are required.

Rollback is configuration-only: setting
runtime.adaptive_yield_score_mode to "conversion" restores the previous
accepted/discovered ranking. Config validation rejects unknown modes.

No source limit, shard-attempt limit, event duration, Google write, R2 write or
paid API budget is increased.

### P38 parallel packed-registry commit

P30 heartbeat evidence from production run #104 isolated the dominant runtime
cost to category commit, not source discovery. Real category commits repeatedly
spent tens of seconds after discovery had already completed, and the P29
watchdog ultimately stopped the event during a later category commit.

Packed-v2 activation previously read, merged and wrote every touched pack shard
serially while holding the global packed-registry lock. A category can touch
dozens of independent pack objects because each permanent lead has multiple
fingerprint kinds distributed across hash shards.

P38 keeps the same global lock and exact transaction/recovery model, but merges
distinct pack keys concurrently with a bounded worker pool. The production
default is 16 pack-commit workers, capped by registry.max_workers. Pack keys are
independent inside one lock ownership window, so no concurrent writer can race
these merges.

P38 also emits separate flushed timings for reservation, Google Sheet append
and R2 activation. The next production event can therefore measure whether any
remaining commit latency is in Google Sheets, reservation, or permanent pack
activation.

No dedupe semantics, pending-marker recovery, quota target, source limit, paid
API use or event timeout is changed.

### P39 commit-start deadline guard

Run #104 proved that the event could remain healthy through discovery and still
reach the P29 watchdog because a new category commit was allowed to start late
in the event. P38 reduces packed-registry activation time, while P39 prevents a
new category transaction from starting when the event has too little safe time
left.

The default commit-start guard is **180 seconds** before the 25-minute event
deadline. It can never be lower than the existing general event deadline guard.
When the guard is reached, the current cycle stops before reserving or writing
the next category and emits a `category_commit_deferred` heartbeat.

Already committed categories remain authoritative. Leads discovered for a
deferred category are not reserved and are safe to rediscover in the next
serialized hourly/recovery event. Existing R2 pending-marker recovery continues
to protect any transaction that had already started before an unexpected
process failure.

This changes no daily quota, source limit, paid API usage, dedupe authority or
watchdog duration.

### P40 quota recovery supervisor

The production engine is intentionally bounded to a 25-minute child event, but
the daily business requirement is not bounded to one event: every category
should keep progressing toward 1,000 accepted leads for the current dated
workbook. Before P40, only the hourly native schedule and manually changed
lead-run trigger could start another real event.

P40 adds a separate `Lead Engine Recovery Supervisor` workflow. After a
default-branch non-PR Lead Engine run completes—successfully or through a
controlled P29 watchdog exit—the supervisor:

- checks the existing configured Asia/Karachi run window;
- reads the live dated workbook with the existing readiness recovery command;
- stops immediately when all category quotas are complete;
- checks GitHub Actions for an already queued/in-progress real main-branch run;
- dispatches exactly one `workflow_dispatch` recovery run only when shortfall
  remains and no real run is already active.

The supervisor uses the repository `GITHUB_TOKEN` with only `actions: write`
and `contents: read`. GitHub permits workflow-dispatch events created with
`GITHUB_TOKEN`, while ordinary token-generated events remain
recursion-protected. The time-window gate bounds the recovery chain, and the
Lead Engine concurrency group continues to serialize real execution.

A runtime kill switch, `recovery_supervisor_enabled`, can stop automatic
continuation without removing the workflow.

### P41 partition exhaustion cooldown

P40 recovery certification showed a new late-day bottleneck: a recovery event
discovered 290 Motorbikes candidates but accepted 0 new unique leads, with 268
duplicate rejections. P36 already stores post-R2 accepted yield for each
category+metro+partition, so P41 uses that evidence directly instead of adding a
new store.

A partition is temporarily deferred when all of the following are true:

- it has at least 2 observed visits;
- it has discovered at least 20 candidates;
- it has accepted 0 post-R2 unique leads.

The selector only applies the cooldown when at least one alternative partition
remains. If every partition looks exhausted, normal adaptive-score ordering is
restored so the category can never be starved.

The thresholds and kill switch are runtime-configurable. P41 does not increase
event duration, source limits, Google writes, R2 writes or paid API use; it only
avoids repeatedly spending existing shard budget on cohorts already proven to
produce no new unique leads.

### P42 same-day partition exhaustion authority

P41 production certification completed successfully at the process level but
still produced 290 Motorbikes discoveries, 268 duplicate rejections and 0 new
unique accepted leads. The routing logs exposed why: partition scoring uses a
blend of historical and same-day yield, and P41 reused that same blended object
for exhaustion decisions. A partition that was productive historically could
therefore avoid cooldown even after repeated zero-unique results today.

P42 separates the two decisions:

- adaptive ranking still uses blended historical + same-day yield, preserving
  useful cross-day priors;
- partition exhaustion cooldown uses only the current day's post-R2 partition
  observations;
- if a caller does not provide a separate same-day evidence object, the selector
  preserves backward-compatible fallback to the blended hints.

This requires no new state object or migration. The existing date-scoped P9/P36
adaptive-yield state already contains the needed visits, discoveries and
post-R2 accepted counts.

No event duration, shard count, source limit, Google write, R2 write or paid
API budget is increased.

### P43 critical-category metro-outskirts expansion

P42 production certification proved the same-day partition cooldown works: the
first routing pass added 3 new Motorbikes leads, moving the category from 71 to
74. The following cycles again saturated, with 239–244 discoveries and zero new
accepted leads. This is now evidence of geographic coverage saturation across
the configured 56 metro boxes rather than only partition selection.

P43 widens the search box only for categories below 10% of their daily target.
The default factor is **1.75x around the existing metro center**. Categories at
or above the threshold keep their exact existing boxes.

Safety properties:

- expansion is bounded to 1x–3x and clamped to valid longitude/latitude limits;
- Overture's existing address-country check still rejects cross-border rows;
- actual lead city and region continue to come from Overture address data;
- scheduler/yield identity remains the original category+metro route, so no
  state migration is required;
- the expansion factor is emitted in source-attempt telemetry;
- the feature, threshold and factor are runtime-configurable.

P43 adds no new data provider, paid API, database, event duration, shard count,
or Google/R2 write budget. It spends the existing critical-category shard slots
over a wider suburban/exurban footprint.

### P44 graduated critical-category geography expansion

P43 proved that wider metro outskirts can still produce new Motorbikes leads,
but its expansion stopped as soon as a category reached 10% completion. After
P41/P42/P43, Motorbikes crossed that boundary while still carrying an 896-lead
shortfall, so abruptly reverting to the original metro boxes would discard the
coverage benefit too early.

P44 turns the single threshold into a graduated search horizon:

- below 10% complete: **2.25x** bbox around the existing metro center;
- 10% to below 25% complete: **1.75x** bbox;
- 25% or more complete: original bbox.

Both thresholds and factors remain runtime-configurable and are clamped to safe
world-coordinate bounds. Overture country-address validation still rejects
cross-border rows, and scheduler/yield identity remains the original metro
route.

P44 does not add shards, event time, providers, paid API usage, Google writes or
R2 writes. It only changes the geographic footprint of already-budgeted
critical-category searches.

### P45 recent zero-unique partition cooldown

P44 production certification completed successfully but discovered 303
candidates and accepted 0 new leads, with 285 duplicate rejections. The
remaining flaw was recency: partition cooldown used cumulative same-day
acceptance. A partition that produced unique leads earlier in the day could
therefore remain eligible indefinitely even after repeated later passes
produced only already-known businesses.

P45 extends the existing date-scoped adaptive-yield object with two compact
partition-only counters:

- `zero_unique_streak`: consecutive discovered passes with zero post-R2
  accepted leads;
- `recent_discovered`: candidates observed since the last unique acceptance.

Any unique acceptance resets both counters. By default, a partition is eligible
for cooldown after **2 consecutive zero-unique passes covering at least 20
recent discoveries**, even if that partition has historical or earlier
same-day accepted leads. The existing aggregate zero-yield rule remains as a
fallback, and if all partitions are cooled the selector still restores normal
ranking to prevent starvation.

The daily R2 state remains backward compatible with existing compact list
entries; only hints carrying recency data are serialized as compact objects.
Historical profiles intentionally discard the recency counters so a new day
starts clean.

No new object family, provider, paid API, event duration, shard count, Google
write or permanent lead-state write is introduced.

### P46 independent quota-recovery heartbeat

P45 certification and its follow-up recovery proved the remaining quota can
continue progressing, but the chain exposed a controller weakness: a
`workflow_run` supervisor can dispatch one `workflow_dispatch` recovery, yet
that token-created recovery completion is not a reliable source for another
supervisor continuation. The dated workbook still had a shortfall while no
real Lead Engine run remained queued or active.

P46 makes recovery continuation independent of that recursion behavior by
adding a **10-minute supervisor heartbeat** during the configured Pakistan run
window. Each heartbeat still performs the existing gates before any dispatch:

- recovery supervisor kill switch must be enabled;
- current Asia/Karachi time must be inside 08:00-23:59;
- Google credentials must be ready;
- live dated workbook must still have category shortfall;
- no real main-branch Lead Engine run may be queued, in progress, waiting,
  requested or pending.

Only then is one serialized recovery run dispatched. The existing
`workflow_run` trigger remains for immediate continuation after ordinary
eligible runs, while the heartbeat guarantees eventual continuation if
GitHub's token-recursion protection suppresses that path.

This does not increase per-run shard limits, event duration, source requests,
Google writes or R2 writes. It only guarantees that the existing bounded
recovery engine is revisited while quota remains incomplete.

### P47 tail-mode cycle extension

Production certification runs consistently completed in roughly five to seven
minutes while the supervised child budget allows up to 25 minutes. Once the
daily workbook reaches the tail, startup and recovery-heartbeat overhead becomes
a larger share of elapsed time than discovery itself.

P47 keeps the normal broad-day event at the existing **3 cycles**, but when the
live workbook has **4 or fewer incomplete categories**, the same process may
continue up to **8 cycles**. Every extended cycle still re-reads live quota and
dedupe state, rotates its cursor, and remains bounded by the existing event
deadline.

Safety remains unchanged:

- the 25-minute event wall-time and deadline guards still stop the process;
- 3 consecutive zero-progress cycles still stop exploration early;
- per-cycle shard attempts and candidate limits are unchanged;
- no paid provider, Google-write budget or R2-write semantics are added;
- disabling `tail_cycle_extension_enabled` restores the previous 3-cycle
  behavior.

This uses otherwise-idle free runner time to close tail shortfalls faster,
especially the remaining Motorbikes quota.

### P48 tail country-yield routing

Production logs showed a tail-routing imbalance for Motorbikes. In the
three-cycle recovery immediately before P47, the scheduler issued exactly
21 Motorbikes attempts to the United States and 21 to Canada. Both countries
were productive, but the US attempts returned 35 unique accepted leads versus
14 from Canada.

P48 preserves country coverage while allowing evidence-backed tail weighting:

- it activates only when 4 or fewer categories remain incomplete;
- both countries need at least 4 category-specific observed visits before any
  preference is applied;
- the stronger country must show at least a 1.5x accepted-per-visit advantage;
- the preferred country receives at most **2x** weight;
- every country still receives a guaranteed base layer of attempts.

With insufficient evidence or a small yield difference, routing remains the
existing balanced sequence. The feature is runtime-configurable and does not
change per-cycle shard limits, event time, providers, Google writes or R2
dedupe semantics.

### P49 combined daily state snapshot

P47 tail mode can run up to eight cycles in one process. Each production cycle
previously read live category totals and live country totals with two separate
Google Sheets `batchGet` requests at cycle start and again after commit.

P49 adds `daily_state_snapshot()`, which reads each category's date+country
columns and review status once and derives both views from the same response.
The engine now uses one snapshot for workbook readiness, one at cycle start,
and one after commit.

Existing `category_counts()` and `daily_country_counts()` methods remain
available for backward compatibility. Lead writes, R2 dedupe, quota logic and
the Google workbook schema are unchanged.

For tail events this removes one full Sheets state request at every state-read
boundary, reducing free API pressure and latency without relaxing freshness.

### P50 centralized runtime identity

P50 removes version drift between package releases and outbound public-network
requests. Overture STAC resolution and official-site/Common Crawl enrichment now
derive their default `User-Agent` from the package `__version__` through one
canonical helper.

The stale version-pinned enrichment override was removed from production config.
An explicit operator-provided `enrichment.user_agent` is still honored, while
normal releases now advance network identity automatically with the package
version.

This is a reliability and observability hardening only: discovery scope, quota
logic, R2 dedupe, Google writes, enrichment budgets and provider selection are
unchanged.

### P51 single-source release version

P51 removes the remaining duplicate release-version source. Packaging metadata
now derives `project.version` dynamically from `vsn_lead_engine.__version__`
through setuptools, so one version bump controls installed package metadata and
the P50 canonical outbound identity together.

A regression test verifies that `importlib.metadata.version("vsn-lead-engine")`
always matches the runtime `__version__`.

This is release-process hardening only; lead discovery, quota scheduling,
enrichment, R2 dedupe and Google write behavior are unchanged.

### P52 tail geography retention

The 2026-09-28 live workbook reached **11,829 / 12,000** accepted daily rows
with every category complete except Motorbikes at **829 / 1,000**. Motorbikes
was already highly dedupe-saturated, while the existing P43/P44 geography
helper stopped widening metro bounds once category completion rose above 25%.

P52 keeps a bounded **1.5x metro bbox** active when four or fewer categories
remain incomplete, until the category reaches quota. Existing low-completion
expansion still wins: 1.75x and 2.25x critical expansion are never reduced by
tail mode.

This expands tail discovery into nearby suburbs/outskirts without adding paid
sources, increasing per-shard limits, weakening taxonomy checks, or changing
R2/Google write semantics.

Production certification on 2026-09-28 used protected-main trigger sequence 31.
GitHub Actions run #162 completed successfully in **616.207 seconds**. Runtime
telemetry recorded **236** source-search events with
`bbox_expansion_factor=1.5`, and the live workbook finished at:

- **12,000 / 12,000** accepted daily rows;
- **Motorbikes 1,000 / 1,000** with shortfall **0**;
- **United States 7,459** and **Canada 4,541** accepted rows;
- final workbook status **Complete**.

A proposed 2.0x follow-up widening was intentionally not promoted because P52
closed the quota with the smaller bounded horizon.

### P54 Node 24 workflow runtime modernization

GitHub Actions production logs on 2026-09-28 emitted deprecation warnings
because the repository still referenced `actions/checkout@v4` and
`actions/setup-python@v5`, both Node 20-era action majors.

P54 upgrades all nine repository workflows to `actions/checkout@v7` and
`actions/setup-python@v7`. Their current upstream action metadata uses
`node24`, matching the GitHub-hosted runner runtime instead of relying on
GitHub's compatibility override.

A repository regression test now asserts that every managed workflow stays on
the Node 24 action majors and rejects the previous v4/v5 pair. Workflow
triggers, permissions, schedules, secrets, Python version, commands and quota
logic are otherwise unchanged.

### P55 immutable GitHub Actions pinning

P54 moved repository workflows onto the Node 24 action line. P55 closes the
remaining CI supply-chain gap by replacing mutable action tags with immutable
release commit SHAs across all nine managed workflows.

Pinned releases:

- `actions/checkout v7.0.1` → `3d3c42e5aac5ba805825da76410c181273ba90b1`
- `actions/setup-python v7.0.0` → `5fda3b95a4ea91299a34e894583c3862153e4b97`

Version comments remain beside each pinned SHA for maintainability, while the
actual executable reference is immutable. A regression test requires these
exact SHAs and rejects both mutable `@v7` refs and the previous v4/v5 majors.

This changes only CI dependency integrity. Workflow triggers, permissions,
schedules, Python version, secrets, quota behavior, R2 dedupe and Google writes
are unchanged.

### P56 persistent AI supervisor resume state

P56 adds a repository-native compact recovery layer so future supervisor
sessions do not depend on chat history or broad re-audits before resuming work.

Canonical resume files:

- `.ai/state/CURRENT-STATE.yaml` — <= 12 KiB machine-readable snapshot/index;
- `.ai/state/LAST-CHECKPOINT.md` — <= 16 KiB last verified checkpoint;
- `.ai/state/RECOVERY-PROTOCOL.md` — deterministic resume/reconciliation order;
- `AGENTS.md` — repository-local supervisor execution and safety contract.

On every fresh session, `continue`, timeout, or connector recovery, the
supervisor must read the compact state/checkpoint first, resolve live protected
`main`, reconcile open Issues before open PRs, and let live GitHub/CI/R2/
workbook evidence override stale compact state or chat memory.

A CI regression test enforces required fields, size bounds, recovery headings,
resume ordering and the immutable GitHub Actions security rule. This milestone
does not change lead discovery, quota logic, R2 dedupe, Google writes, schedules
or production runtime behavior.

### P57 automated dependency update PRs

P55 made GitHub Actions execution immutable by pinning reviewed release SHAs.
P57 adds the update path needed to keep those pins and Python dependencies from
silently aging.

`.github/dependabot.yml` now monitors:

- GitHub Actions at the repository root, weekly;
- Python/pip dependencies from the root `pyproject.toml`, weekly;
- both schedules in `Asia/Karachi`;
- grouped updates to reduce PR noise;
- a small open-PR ceiling so automation cannot flood protected main.

Dependabot only proposes changes. Every generated PR must still pass the normal
protected-main validation before it can merge. The pip policy uses
`increase-if-necessary`, so version constraints are only raised when the
existing manifest does not already allow the update.

A repository regression test guards the required ecosystems, weekly schedule,
timezone, grouping and PR limits.

### P58 reproducible Python dependency installs

P58 removes install-time transitive dependency drift from the Python 3.12
GitHub-hosted Ubuntu execution path.

A clean `pip --dry-run --ignore-installed --report` resolver run on PR #104
produced the exact transitive environment. The resulting `requirements.txt`
locks **35 runtime/dev packages** while `pyproject.toml` remains the source of
the project's supported direct dependency ranges.

Build isolation is also deterministic:

- `setuptools==84.0.0`;
- `wheel==0.48.0`.

Every workflow that installs VSN Lead Engine now uses
`-c requirements.txt`, so the project metadata is still installed normally
but all resolved runtime/dev packages must match the reviewed lock. The primary
CI and production workflow also runs `pip check` before application
validation or lead execution.

Dependabot's pip updater can maintain both PEP 621 `pyproject.toml` metadata
and `.txt` dependency files; generated update PRs still have to pass protected
main CI before merge.

Repository tests enforce exact lock syntax, declared-dependency coverage,
build-backend pins, constrained editable installs and dependency-integrity
preflight coverage.

### P59 hash-verified Python dependency artifacts

P58 pinned exact dependency versions. P59 additionally verifies the bytes of
every external package artifact used by the GitHub-hosted Ubuntu / CPython 3.12
CI and production paths.

Three reviewed hash surfaces are authoritative:

- `requirements-bootstrap.txt` — pip, setuptools, wheel and packaging;
- `requirements-runtime.txt` — 30 runtime packages;
- `requirements-dev.txt` — runtime plus 5 test-only packages.

Each package line is exact-version pinned and carries the SHA-256 of the
artifact selected on a clean PR #105 GitHub runner. The old unhashed
`requirements.txt` has been retired so there is no parallel dependency lock.

All project-installing workflows call `scripts/install_locked.py`. That
installer fails closed unless it is running on Linux + CPython 3.12, installs
external artifacts with `pip --require-hashes`, then installs the local VSN
package with `--no-deps --no-build-isolation` and runs `pip check`.

This means normal production execution cannot silently resolve a different
transitive version or accept different bytes for the selected dependency
artifacts. Dependency-update PRs must regenerate reviewed hashes when the
selected artifact set changes.

The main-protection controller is intentionally excluded because it does not
install the project or third-party Python dependencies.

### P60 controlled hash-lock regeneration

P59 made external Python artifacts hash-verified. P60 adds the controlled update
path required when dependency versions change.

The lock generator is now repository-native:

- `scripts/regenerate_hash_locks.py --check` resolves the current
  `pyproject.toml` runtime/dev dependency graph and fails with a unified diff
  when committed SHA-256 locks are stale;
- `--write` regenerates bootstrap, runtime and dev lock files in one
  deterministic pass;
- generation is Linux + CPython 3.12 only;
- the resolver itself is fixed by
  `.github/dependency-resolver.txt` at hash-verified `pip==25.2`.

`.github/workflows/dependency-lock.yml` runs the drift check only when the
dependency surface changes. Its manual regeneration job has job-scoped
`contents: write`, rejects `main`/`master`, and accepts only an existing
`dependabot/*` or `deps/*` target branch. It regenerates locks, re-checks
them, performs a hash-verified dev install, validates runtime configuration,
runs the full test suite, and only then commits the three generated lock files
back to that update branch.

There is no automatic merge and no direct-main regeneration path. Normal branch
protection and PR CI remain the release gate.

The pre-P59 Dependabot PR #103 was closed as stale because it targeted the
retired unhashed `requirements.txt` model. Future dependency PRs are required
to reconcile against the P60 generator instead.

### P61 dependency-update certification

P61 used the first post-P60 Dependabot update as a real end-to-end certification
of the dependency integrity workflow.

Dependabot proposed:

- `phonenumbers 8.13.55 -> 9.0.40`;
- `pytest 8.4.2 -> 9.1.1`;
- direct dependency range widening to allow the new majors.

The initial bot-generated lock lines carried multiple hashes and were rejected
by both the repository lock contract and the fresh-resolver drift check, as
designed. P60's pinned pip 25.2 resolver then produced the canonical selected
artifacts:

- `phonenumbers==9.0.40` →
  `sha256:189c028c4acd41ee80782e50f74a91260bd76d9115c83be94302509e1cdb5e84`;
- `pytest==9.1.1` →
  `sha256:37a86b45efb9a47a61a36449063e8e18d0cab3161329fc099eb21783169c4f0c`.

After canonical normalization, Dependency Lock Integrity matched a fresh
resolver result and Lead Engine CI passed the complete suite. Phone
normalization remains covered for US/Canada E.164 behavior, so the
`phonenumbers` major upgrade is certified rather than blindly accepted.

This establishes the intended update path:

Dependabot proposal → fail-closed drift detection → canonical regeneration →
full application validation → protected-main merge.

### P62 next-day workbook preflight and early recovery

P62 moves daily workbook readiness from a single last-minute check into a
two-stage preflight without changing lead collection or dedupe behavior.

Readiness cadence in `Asia/Karachi`:

- **20:50 PKT (15:50 UTC)** — preflight the **next day's** workbook;
- **07:50 PKT (02:50 UTC)** — re-check/recover the **current day's** workbook;
- **08:00 PKT** — normal primary lead-collection window begins.

The earlier preflight creates or repairs tomorrow's dated workbook through the
existing readiness path roughly eleven hours before production. If My Drive
ownership or template-copy permissions block creation, the incident is visible
well before the morning run instead of leaving only a ten-minute recovery
window.

CLI readiness is now date-aware but intentionally bounded:

```
python -m vsn_lead_engine.cli workbook-ready --next-day
python -m vsn_lead_engine.cli workbook-ready-recover --next-day --attempts 3 --delay-seconds 60
python -m vsn_lead_engine.cli workbook-ready --date YYYY-MM-DD
```

Explicit dates must be strict `YYYY-MM-DD` and may target only local **today**
or **tomorrow**. Historical dates and dates beyond tomorrow are rejected, which
prevents this repair path from mutating arbitrary workbooks.

The readiness workflow also supports a manual `today` / `next-day` target
choice. Next-day readiness events use distinct `prestart-next-day` health
telemetry and persist `target_kind`, while the morning readiness event keeps
the existing `prestart` origin.

This path still performs no lead discovery, no R2 dedupe mutation, no quota
lead writes, and no source/enrichment work.

### P63 deployment catch-up next-day readiness

P62 added a 20:50 PKT next-day preflight, but its first production deployment
landed after that day's scheduled slot. That exposed a deployment-timing gap:
new readiness logic could be correct and CI-green while tomorrow's workbook
still remained unprepared until the next scheduled readiness run.

P63 adds a bounded **main-push catch-up trigger** to the Daily Workbook
Readiness workflow. It runs only when readiness-related production files change:

- `.github/workflows/daily-workbook-readiness.yml`;
- readiness CLI/schedule/health/engine/Sheets modules.

A qualifying main deployment always targets **next-day** readiness. Unrelated
README/docs-only pushes do not trigger the workflow.

The catch-up uses the same bounded readiness repair path introduced by P62:
no lead discovery, no source/enrichment work, no quota lead writes, and no R2
dedupe mutation. It exists only to ensure a readiness deployment cannot miss
the evening preflight window.

### P64 ownership-safe Google My Drive authentication

P63 certified the deployment catch-up trigger in production, but the real
next-day readiness run exposed the Google ownership boundary: the target folder
is **My Drive**, owned by the VSN user account, while the GitHub service account
is only a writer. The push catch-up correctly targeted `2026-09-29`, retried
three times, recorded the incident in the target-date health ledger, and failed
closed when the service account could not create the missing file.

Google's Drive model does not give service accounts personal Drive storage
quota. P64 therefore adds an ownership-safe human-user OAuth path.

Credential priority:

1. `GOOGLE_OAUTH_USER_JSON` — Google authorized-user JSON; preferred for
   My Drive reads/writes and new dated workbook creation;
2. `GOOGLE_SERVICE_ACCOUNT_JSON` — preserved as a fallback for existing
   shared files and backward compatibility.

The OAuth secret is never logged. `validate` reports only the non-secret mode:
`user-oauth`, `service-account`, or `missing`.

All Google-write workflows expose both credential options and their credential
gates accept either one. Runtime version is **0.60.0**.

As immediate incident recovery, the connected user-owned Drive authority
precreated `US + Canada Business Leads — 2026-09-29` in the configured folder.
The file is owned by the VSN Google user and shared to the service account as
writer, so existing-file readiness can proceed while user OAuth is configured
for future autonomous creation.

### P65 OAuth onboarding and Drive creation certification

P64 added an OAuth-first runtime path, but a refresh-token credential still has
to be provisioned once by the VSN Google user. P65 makes that onboarding and
future creation verification repository-native.

#### Local OAuth onboarding

Create a Google Cloud **Desktop application** OAuth client with Drive + Sheets
access, download its client JSON, then run:

```bash
python scripts/google_oauth_onboard.py client_secret.json
```

The helper uses a localhost callback, PKCE, offline access and explicit consent.
It writes the resulting authorized-user credential to
`.google-oauth-user.json` with private file permissions where supported. It
does **not** print the refresh token or client secret.

Both `.google-oauth-user.json` and `client_secret*.json` are git-ignored.

After local authorization, add the complete generated JSON to the repository
secret `GOOGLE_OAUTH_USER_JSON`.

#### Production capability certification

P65 adds:

```bash
python -m vsn_lead_engine.cli google-drive-capability --next-day --probe-create
```

and a manual **Google Drive Capability** GitHub Actions workflow. The probe
creates a temporary Google Sheet in the configured lead folder and immediately
moves it to trash. A successful probe proves the active credentials can create
new files in the actual production location.

Normal readiness does not perform the destructive-safe probe on every run.
Instead, when a dated workbook is missing it first inspects target-folder
capability. A service-account + My Drive ownership blocker is now classified as
permanent and fails after **one attempt** rather than waiting through three
60-second retries. Shared-drive/service-account and user-OAuth paths remain
eligible for creation.

Runtime version is **0.61.0**.

### P66 strict user-OAuth autonomy certification

P65 added the onboarding helper and create/trash capability probe. P66 makes
the final production certification **strict** so service-account fallback can
never be mistaken for autonomous My Drive readiness.

The `google-drive-capability` CLI now supports:

```bash
python -m vsn_lead_engine.cli google-drive-capability \
  --next-day \
  --require-user-oauth \
  --probe-create
```

With `--require-user-oauth`, any active mode other than `user-oauth`
returns a permanent blocked result **before** a probe is attempted.

The manual **Google Drive Capability** workflow now also:

- fails immediately if `GOOGLE_OAUTH_USER_JSON` is missing;
- refuses service-account fallback as certification evidence;
- requires the strict user-OAuth CLI gate;
- performs the real production-folder create → trash probe only after the
  secret is present.

This keeps existing service-account fallback available for normal operations on
already-shared files, while autonomous missing-workbook creation is certified
only with the intended user-owned OAuth authority.

Runtime version is **0.62.0**.

### P67 midnight-safe recovery runway

P67 closes an end-of-day boundary gap in the production/recovery scheduler.

Before P67, the local-hour gate considered the entire **23:00-23:59 PKT**
hour valid. The recovery supervisor also used a separate hour-only gate, so a
late dispatch could start close to midnight while the process watchdog still
allowed roughly 26 minutes of execution.

Scheduled production and recovery runs now require enough time to finish or be
terminated **before local midnight**.

The required runway is derived from the active runtime budgets:

- process watchdog: `1560s`;
- kill grace: `20s`;
- event budget: `1500s + 60s guard`;
- midnight safety buffer: `60s`.

Current minimum runway is therefore **1640 seconds (27m20s)**.

Under the current configuration:

- **23:30 PKT** → allowed;
- **23:32:40 PKT** → exact threshold, allowed;
- **23:32:41 PKT and later** → blocked by
  `insufficient-midnight-runway`;
- 23:40 / 23:50 recovery heartbeats can still run their lightweight quota
  checks, but they cannot dispatch a real lead process.

The same `scheduled_run_window()` gate is used by both the native Lead Engine
schedule and the Recovery Supervisor. Recovery-supervisor and recovery-push
runs also re-check the gate at **actual execution start**, protecting against
GitHub queue delay after dispatch.

Recovery origin telemetry is preserved through the scheduled gate. Explicit
human `manual` workflow runs remain operator-controlled and are not silently
reclassified as scheduled recovery.

Runtime version is **0.63.0**.

### P68 health-ledger recovery and schedule-gate telemetry

P68 makes the operational health ledger accurately distinguish **real recovery
runs** from **recovery attempts intentionally blocked by schedule policy**.

Recovery accounting now includes both production origins:

- `recovery-push`;
- `recovery-supervisor`.

The summary exposes:

- `recovery_runs` — combined executed recovery runs;
- `recovery_push_runs`;
- `recovery_supervisor_runs`;
- `schedule_blocks`;
- `midnight_guard_blocks`;
- `latest_schedule_block_reason`.

A `scheduled-window-skipped` event is **not** counted as an executed run.

Run-health events now persist the P67 schedule evidence:

- schedule status / block reason;
- within-hours and midnight-safe flags;
- seconds remaining to local midnight;
- required watchdog runway;
- configured safety buffer.

P68 also adds a PII-free `schedule-gate` health event and
`health-schedule-gate` CLI command. The Recovery Supervisor records a blocked
pre-dispatch gate directly into the existing R2 daily health ledger, so a
23:40/23:50 intentional midnight guard is auditable even though no Lead Engine
child process starts.

Telemetry failure is non-blocking for the Recovery Supervisor itself; it does
not turn an intentional safe skip into an operational outage.

Runtime version is **0.64.0**.

### P69 serialized daily-workbook lifecycle

P69 removes a race between the Daily Workbook Readiness workflow and real Lead
Engine runs.

Before P69, both workflows could operate on the same dated Google workbook at
the same time because they used different GitHub Actions concurrency groups.
That becomes more important once user OAuth enables autonomous workbook
creation: a delayed 07:50 readiness run and the 08:00 production run could both
observe a missing workbook and race to create the same dated file.

Production workbook-mutating runs now share the repository-wide concurrency
group:

`vsn-lead-engine-production`

Both Lead Engine production events and Daily Workbook Readiness use
`queue: max`, so overlapping production work waits instead of replacing an
already pending run. Pull-request validation remains isolated in a
PR-number-specific concurrency group and does not block production.

Drive lookup is also fail-closed:

- zero exact active matches → creation is allowed through the existing
  capability/auth controls;
- one exact active match → use it;
- more than one exact active match → raise
  `DuplicateDailyWorkbookError` and stop before writes;
- after a new copy is created, a second exact lookup verifies that the created
  file is still the sole canonical dated workbook before further sheet writes.

This protects against both GitHub workflow overlap and an external/manual file
appearing during the create window.

The current `2026-09-29` production folder was checked before rollout and has
exactly one active dated workbook.

Runtime version is **0.65.0**.

### P70 day-boundary-aware deployment readiness

P70 corrects the deployment catch-up target around local midnight.

Before P70, every readiness-related push to protected main forced
`next-day`. A deployment at 00:20 PKT therefore skipped the current upcoming
production day and targeted tomorrow instead.

Deployment catch-up now uses the configured **20:50 PKT evening preflight
cutoff**:

- **00:00–20:49:59 PKT** → target local **today**;
- **20:50:00–23:59:59 PKT** → target local **next-day**.

At midnight the rule naturally resets to the new local day. This means a
00:20 deployment on September 29 targets **September 29**, not September 30.

The cutoff is explicit in runtime configuration:

- `readiness_evening_preflight_hour = 20`;
- `readiness_evening_preflight_minute = 50`.

The workflow target-resolution step now uses the shared Python schedule module
instead of duplicating push-date logic in Bash. It records the resolved target
kind, run date, resolution reason and local resolution time in the Actions log.

Scheduled semantics remain unchanged:

- 07:50 PKT schedule → today;
- 20:50 PKT schedule → next-day;
- manual `today` / `next-day` selection remains explicit.

P69's first post-merge catch-up at 00:20 PKT correctly exposed the old behavior
by targeting September 30. That run hit the already-known My Drive
service-account creation blocker; September 29 remained intact with exactly
one active workbook. September 30 was then precreated under the VSN user owner
so the OAuth blocker cannot disrupt its evening readiness.

Runtime version is **0.66.0**.

## Primary free source

Production discovery uses **Overture Maps Places**, queried directly from its
public GeoParquet release with DuckDB. The dataset exposes place names,
taxonomy, phones, websites, emails, socials and addresses when available.

The engine resolves the current Overture release from the official STAC
catalog instead of hardcoding a release.

See [DATA_SOURCES.md](DATA_SOURCES.md) for licensing/compliance notes.

## Taxonomy-first category precision

Category selection uses Overture's canonical `taxonomy.primary`,
`taxonomy.hierarchy` and `basic_category` fields.

Rules:

- taxonomy entries are matched as complete tokens, never loose substrings;
- a business name cannot override a conflicting taxonomy;
- name fallback is allowed only when taxonomy is missing and the phrase is
  category-specific;
- the accepted lead note records the classification reason for later audits;
- the Python classifier re-checks every SQL result before it can become a lead;
- rows quarantined as `Needs Review` are excluded from daily target counts and
  Overview totals;
- matching Master Registry rows use `NeedsReview`, which no longer blocks
  dedupe, so a business may be rediscovered later into the correct category.

## Country-balanced priority scheduler

Every workflow run gets an independent cursor (GitHub run number in Actions).

1. US and Canada metros are interleaved; the underrepresented country runs first.
2. Categories below 25% of target receive 3× shard weight, 25-50% receive 2×,
   and categories above 50% receive normal weight.
3. Metro order rotates with the run cursor.
4. Each shard also receives a rotating deterministic Overture candidate
   partition, so repeated runs do not keep replaying the same first limited
   cohort.

Each collection cycle can try up to 18 category/geography shards with a
1,000-lead accepted ceiling. One production event can execute up to **3
controlled cycles**, re-reading live quota state between cycles, so it can add
up to 3,000 accepted leads without waiting for the next hourly event.

## Pipeline

```
GitHub event / schedule
 -> GitHub-hosted ubuntu runner
 -> resolve Asia/Karachi date
 -> find/create US + Canada Business Leads — YYYY-MM-DD
 -> Overture Places discovery
 -> country/category priority scheduler
 -> taxonomy-first classification
 -> official website / bounded Common Crawl contact enrichment
 -> normalize phone
 -> Registry dedupe (Sheets migration source; R2 permanent ledger)
 -> Registry PendingDaily
 -> dated workbook append
 -> Registry Active
 -> dated Overview counters
```

## Reliability and schedule

GitHub Actions is the primary hourly controller at **:00** from 08:00 through
23:00 Asia/Karachi. The separate recovery supervisor runs at **:20** and checks
the live dated workbook before acting. It creates a protected-main-compatible
recovery PR only when the native run is missing/failed or the live quota still
has a shortfall. It does not create a competing trigger while the native run is
queued or in progress.

P0 reliability controls:

- one Asia/Karachi `run_date` is frozen at process start and reused for the
  workbook, rows and counters;
- in R2 authority mode, every real run reconciles only compact R2 `pending/`
  transaction markers before discovery;
- written pending leads keep their permanent R2 fingerprints, while missing
  writes roll back only the fingerprint objects owned by that reservation;
- Google Drive/Sheets calls use bounded API retries;
- source queries use bounded exponential retry/backoff;
- GitHub validation and production jobs have hard execution timeouts;
- the dated workbook is resolved before discovery begins.

P1 performance controls:

- PRs run the full pytest suite; production events use one runner with a
  lightweight runtime-config preflight instead of starting a second test runner;
- Overture reuses one DuckDB/httpfs connection across all shards/cycles in the
  process;
- one event can run up to 3 quota-aware cycles, stopping immediately on daily
  completion while bounded zero-progress cycles may continue into rotated cohorts;
- the same source objects, Google clients and frozen run date are reused across
  cycles while live Sheet/Registry state is re-read for safety;
- Overture website-only businesses are retained as enrichment candidates instead
  of being discarded at SQL selection time;
- official website enrichment is capped by per-run candidate budget, worker
  count, response bytes, page count and timeout;
- Common Crawl is a small serial archival fallback only, never a broad parallel
  discovery source;
- recovered phones still pass the normal US/Canada validation and final exact
  R2 dedupe before a lead can be accepted.

P2/P7 source-yield controls:

- Overture candidates are split into **16 deterministic hash partitions**;
- the partition advances with the GitHub run cursor and with each shard attempt;
- the three controlled cycles in one event therefore naturally reach different
  candidate cohorts instead of replaying one `LIMIT 500` slice;
- source attempt telemetry records the active partition and total partition
  count for auditability;
- partitioning changes discovery breadth only—classification, phone validation,
  enrichment, quota ceilings and exact R2 dedupe remain authoritative;
- a zero-yield partition no longer stops the event immediately: the runner can
  continue through the configured bounded zero-progress cycle budget so the next
  rotated cohorts still get a chance;
- production currently allows all 3 controlled cycles before a zero-progress
  stop, while an already-complete daily quota still exits immediately.

P4 quality observability:

- the Overview tab now persists accepted-lead, discovery, duplicate, invalid-phone,
  enrichment-candidate, phone-recovery, Common Crawl, budget-skip and enrichment-error
  counters;
- the previously emitted `Phones Recovered` metric is now part of the workbook schema
  instead of being silently ignored;
- every active cycle emits a structured `quality` object in Actions JSON with
  acceptance rate, phone-recovery rate and unique candidate partitions visited;
- Overview keeps latest-cycle acceptance/recovery percentages plus partition count;
- existing dated workbooks self-heal missing P4 metric rows through
  `_ensure_overview_metrics`, while newly created daily workbooks receive them from
  the seed schema automatically.

## P2 permanent R2 dedupe ledger

The long-term duplicate history is object-storage based, not database based.
Full lead records continue to live in dated Google Sheets. Cloudflare R2 stores
only compact hashed fingerprints needed to answer: "have we already accepted
this business?"

Registry modes in `config/runtime.json`:

- `sheets` — current Google Master Registry is the authority.
- `dual` — migration-observation mode: Google Registry remains authority and
  accepted rows shadow into R2.
- `r2` — **current production mode**: R2 is the permanent cross-day dedupe
  authority; Google Master Registry is frozen while dated daily workbooks
  continue normally.

### Exact duplicate dimensions

A lead is rejected when any permanent blocking fingerprint matches:

- provider/source ID;
- Google Place ID when available;
- normalized domain;
- normalized phone + normalized business name;
- normalized business + city + region.

The canonical Unique Key is derived from place/domain/phone-name/business-location,
so it is used as transaction identity without writing a redundant sixth
permanent R2 object.

Each raw value is normalized and converted on the runner to a type-separated
96-bit BLAKE2 token before R2 access. R2 object keys therefore contain no raw
phone number, business name, domain, email, address or social profile.

### Object layout

```
<bucket>/
  vsn-lead-ledger/v1/
    fp/                         # historical objects-v1; read-only compatibility
      p/<prefix>/<digest>
      s/<prefix>/<digest>
      d/<prefix>/<digest>
      n/<prefix>/<digest>
      l/<prefix>/<digest>
    packs/v2/                   # current permanent write layout
      p/<shard>.bin
      s/<shard>.bin
      d/<shard>.bin
      n/<shard>.bin
      l/<shard>.bin
    pending/
      <batch-id>.json
    locks/
      packed-v2.lock
```

Packed-v2 stores exact 96-bit digests as fixed-width binary records. With the
production one-nibble shard setting, each fingerprint type has at most 16 pack
objects, so the five normal dimensions use at most 80 active pack shards.
Historical objects-v1 remain readable and blocking; the cutover does not delete
or weaken the already-certified dedupe history.

### Registry-first transaction and crash recovery

For each category batch in packed-v2:

1. acquire the short-lived exact Registry lock;
2. check permanent packed-v2 hashes, historical objects-v1 hashes and all live
   pending reservations;
3. write one compact pending transaction marker for the accepted reservation;
4. release the lock and append only reserved leads to the dated Google Sheet;
5. after the Sheet write succeeds, re-acquire the lock, merge the reserved
   fingerprints into the touched binary pack shards, then clear the marker.

If a runner dies, the next real run scans only the small `pending/` prefix.
For each pending lead it hashes the dated Sheet Unique Key column:

- written lead -> idempotently merge its fingerprints into packed-v2 and clear
  pending state;
- missing lead -> discard its pending reservation without adding a permanent
  packed fingerprint.

Legacy pending markers are still reconciled with their original objects-v1
ownership rules. This preserves crash recovery while removing per-lead permanent
object writes from the normal production path.

### Migration

The cutover is zero-downtime:

```
sheets
  -> registry-check
  -> registry-backfill --dry-run
  -> registry-backfill
  -> registry-audit   # missing_fingerprints must be 0
  -> registry-migrate # one-shot check + dry-run + backfill + audit + stats
  -> registry-smoke   # isolated live reserve/collision/rollback cleanup
  -> dual
  -> r2  # CURRENT PRODUCTION AUTHORITY
```

The backfill imports only blocking Google Registry rows. `NeedsReview`,
`Retryable`, rejected, invalid and quarantined rows are intentionally skipped,
so bad historical rows do not block future rediscovery.

Server-only GitHub secrets:

- `R2_ACCOUNT_ID`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_BUCKET`

The bucket name is never hard-coded; `R2_BUCKET` is the authority.

### Scale model

R2 is used as an exact object ledger, so there is no fixed SQL database-size
ceiling and no index rebuild/vacuum requirement. Packed-v2 removes the old
worst-case pattern of up to five permanent `PUT` operations per accepted lead.
One category activation now rewrites only the pack shards actually touched by
that batch; with one-nibble sharding the absolute shard ceiling is 80 across
all five normal fingerprint dimensions, even for a 1,000-lead category batch.

Collision checks remain exact. Packed-v2 is checked first and historical
objects-v1 are checked as a fallback, so the certified pre-cutover history
continues blocking duplicates. The ledger never expires accepted-history
fingerprints merely to save space, because deleting them would allow old
businesses to re-enter as duplicates.

## Production credential

The Google service account needs access to:

- the configured lead folder / dated workbook
- the legacy Master Registry only for migration/audit maintenance

Google Sheets API and Google Drive API must remain enabled. The JSON key is
stored as GitHub secret `GOOGLE_SERVICE_ACCOUNT_JSON`.

## Current status

- Runtime package version: **0.66.1**
- ANPOS child control plane: **1.4.0 ACTIVE — STATE RECONCILED TO PRODUCTION OPERATIONS**

- User consent: **APPROVED**
- Google integration: **VERIFIED**
- Daily dated workbook routing: **ENABLED**
- P0 reliability hardening: **ENABLED**
- P1 runner performance + quota cycles: **ENABLED**
- P2 permanent R2 dedupe ledger: **R2 AUTHORITY — LIVE**
- P0 free-tier R2 write hardening: **PACKED-V2 ACTIVE**
- P1 public contact enrichment: **OFFICIAL WEBSITE + BOUNDED COMMON CRAWL ACTIVE**
- P2 rotating Overture cohorts: **16 HASH PARTITIONS ACTIVE**
- P3 partition-aware zero-progress retry: **3 BOUNDED CYCLES ACTIVE**
- P4 quality observability: **FUNNEL + ENRICHMENT METRICS ACTIVE**
- P5 daily workbook readiness: **07:50 PKT PRE-START CERTIFICATION ACTIVE**
- P6 readiness recovery: **3-ATTEMPT RETRY + INCIDENT TELEMETRY ACTIVE**
- P7 free-source breadth: **56 METROS + 16 OVERTURE PARTITIONS ACTIVE**
- P8 adaptive yield routing: **IN-PROCESS LEARNING + EXPLORATION ACTIVE**
- P9 daily adaptive state: **ONE COMPACT R2 OBJECT/DAY ACTIVE**
- P10 schedule/catch-up: **08:00–23:00 PKT NATIVE + OFFSET SUPERVISOR ACTIVE**
- P11 daily health ledger: **READINESS + RUN + INCIDENT AUDIT ACTIVE**
- P12 protected-main governance: **LIVE RULESET ACTIVE — PR + STRICT VALIDATE + REPOSITORY-INTEGRITY + SQUASH-ONLY**
- P13 rolling historical yield prior: **CROSS-DAY COLD-START ROUTING ACTIVE**
- P14 zero-yield cooldown: **SAME-DAY EXHAUSTION DEFERRAL ACTIVE**
- P15 fair category weighting: **LAYERED 3×/2×/1× COVERAGE ACTIVE**
- P16 enrichment fairness: **160/EVENT + 12/CALL + COMMON CRAWL 1/CALL ACTIVE**
- P17 pre-enrichment dedupe: **READ-ONLY R2 NETWORK-SAVING PREFILTER ACTIVE**
- P18 source-batch dedupe: **LOCAL BEST-REPRESENTATIVE COLLAPSE ACTIVE**
- P19 packed registry cache: **ADVISORY READ CACHE ACTIVE; RESERVATIONS FRESH**
- P20 cache observability: **P11 HIT/MISS/ENTRY TELEMETRY ACTIVE**
- P21 legacy fallback cache: **ADVISORY OBJECTS-V1 HEAD CACHE ACTIVE; RESERVATIONS FRESH**
- P22 pending-marker cache: **ADVISORY PENDING LIST/GET CACHE ACTIVE; RESERVATIONS FRESH**
- P23 Overture contact stratification: **80% PHONE-FIRST + 20% WEBSITE EXPLORATION RESERVE ACTIVE**
- P24 contact-mix observability: **SOURCE-PHONE + WEBSITE-ONLY FUNNEL TELEMETRY ACTIVE**
- P25 partition-aware cooldown: **4-DISTINCT-PARTITION FLOOR ACTIVE**
- P26 user-owned workbook bootstrap: **07:40 PRECREATE + SAFE BLANK INIT ACTIVE**
- P27 Overture query guard: **45S INTERRUPT + NON-RETRYABLE TIMEOUT ACTIVE**
- P28 graceful event budget: **25-MIN CLEAN STOP + 60S START GUARD ACTIVE**
- P29 process watchdog: **26-MIN CHILD DEADLINE + 20S KILL GRACE ACTIVE**
- P30 live heartbeat telemetry: **SOURCE/ENRICHMENT/R2/COMMIT PHASE TIMING ACTIVE**
- P31 taxonomy breadth audit: **READ-ONLY MOTORBIKES COVERAGE PROBE ACTIVE**
- P32 Motorbikes canonical rentals: **MOTORCYCLE RENTAL + SCOOTER RENTAL ACTIVE**
- P33 production source probe: **EXACT 16-PARTITION MOTORBIKES READ-ONLY PROBE ACTIVE**
- P34 R2 collision probe: **PACKED-V2 MOTORBIKES READ-ONLY COLLISION AUDIT ACTIVE**
- P35 critical-deficit rescue: **LAYERED 6×/4×/2×/1× FAIR SLOT REALLOCATION ACTIVE**
- P36 partition yield routing: **PERSISTED CATEGORY+METRO+PARTITION LEARNING ACTIVE**
- P37 quota-throughput scoring: **ACCEPTED-PER-SHARD + EXPLORATION ACTIVE**
- P38 packed commit throughput: **16-WORKER DISTINCT-SHARD MERGE + SUBSTAGE TIMING ACTIVE**
- P39 commit deadline guard: **180S CLEAN COMMIT-START RESERVE ACTIVE**
- P40 quota recovery supervisor: **LIVE SHORTFALL CHECK + SINGLE SERIALIZED REDISPATCH ACTIVE**
- P41 partition exhaustion cooldown: **POST-R2 ZERO-UNIQUE COHORT DEFERRAL ACTIVE**
- P42 same-day exhaustion authority: **CURRENT-DAY POST-R2 EVIDENCE CONTROLS PARTITION COOLDOWN**
- P43 critical geography expansion: **<10% QUOTA METRO BBOX 1.75× OUTSKIRTS COVERAGE ACTIVE**
- P44 graduated geography expansion: **DEFICIT-TIERED BBOX EXPANSION ACTIVE**
- P45 recent zero-unique cooldown: **RECENCY-AWARE PARTITION DEFERRAL ACTIVE**
- P46 recovery heartbeat: **INDEPENDENT QUOTA-RECOVERY HEARTBEAT ACTIVE**
- P47 tail-cycle extension: **UP TO 8 BOUNDED TAIL CYCLES ACTIVE**
- P48 tail country-yield routing: **EVIDENCE-GATED COUNTRY WEIGHTING ACTIVE**
- P49 combined daily state snapshot: **SINGLE SHEETS STATE READ PER BOUNDARY ACTIVE**
- P50 runtime identity consistency: **PACKAGE-VERSIONED OUTBOUND IDENTITY ACTIVE**
- P51 single-source release version: **SETUPTOOLS METADATA DERIVED FROM RUNTIME VERSION ACTIVE**
- P52 tail geography retention: **PRODUCTION CERTIFIED — 12,000/12,000 DAILY QUOTA CLOSED WITH 1.5× TAIL COVERAGE**
- P53 progressive tail geography: **EVALUATED / NOT PROMOTED — P52 CLOSED QUOTA WITHOUT 2.0× EXPANSION**
- P54 workflow runtime modernization: **NODE 24 FIRST-PARTY ACTION MAJORS v7 ACTIVE**
- P55 CI supply-chain pinning: **IMMUTABLE CHECKOUT/SETUP-PYTHON RELEASE SHAS ACTIVE**
- P56 persistent AI resume state: **COMPACT STATE + CHECKPOINT + RECOVERY CONTRACT ACTIVE**
- P57 dependency update automation: **DEPENDABOT ACTIONS + PIP WEEKLY GROUPED PRS ACTIVE**
- P58 reproducible dependencies: **35-PACKAGE PYTHON 3.12 LOCK + EXACT BUILD BACKEND + PIP CHECK ACTIVE**
- P59 artifact integrity: **SHA-256 REQUIRE-HASHES BOOTSTRAP/RUNTIME/DEV INSTALLS ACTIVE**
- P60 lock regeneration: **PINNED RESOLVER + PR DRIFT CHECK + MANUAL BRANCH-ONLY REGENERATION ACTIVE**
- P61 dependency-update certification: **PHONENUMBERS 9 + PYTEST 9 PASSED CANONICAL HASH REGENERATION AND FULL CI**
- P62 next-day readiness: **20:50 PKT TOMORROW PREFLIGHT + 07:50 PKT SAME-DAY RECOVERY ACTIVE**
- P63 readiness deployment catch-up: **MAIN READINESS CHANGES IMMEDIATELY PREFLIGHT TOMORROW**
- P64 My Drive ownership auth: **USER OAUTH PREFERRED + SERVICE-ACCOUNT FALLBACK + AUTH-MODE TELEMETRY**
- P65 OAuth autonomy tooling: **LOCAL PKCE ONBOARDING + FAIL-FAST OWNERSHIP CHECK + CREATE/TRASH CERTIFICATION**
- P66 strict OAuth certification: **USER-OAUTH-ONLY PRODUCTION PROBE; SERVICE-ACCOUNT FALLBACK CANNOT CERTIFY AUTONOMY**
- P67 midnight-safe recovery: **DYNAMIC WATCHDOG RUNWAY + EXECUTION-START RECHECK ACTIVE**
- P68 health telemetry: **RECOVERY-SUPERVISOR ACCOUNTING + MIDNIGHT-GATE R2 EVIDENCE ACTIVE**
- P69 workbook lifecycle: **SHARED PRODUCTION FIFO QUEUE + DUPLICATE DATED-WORKBOOK FAIL-CLOSED GUARD ACTIVE**
- P70 deployment boundary targeting: **TODAY BEFORE 20:50 PKT; NEXT-DAY AT/AFTER 20:50 PKT**
- Master Registry cross-day dedupe: **FROZEN MIGRATION/AUDIT SNAPSHOT**
- Overture Places source: **ENABLED**
- Country-balanced priority scheduling: **ENABLED**
- Taxonomy-first classification: **ENABLED**
- Public community Overpass production use: **DISABLED**
- Paid discovery APIs: **DISABLED**


## Final R2 cutover certification

Final production cutover evidence:

- historical backfill: **12,815 blocking rows**;
- exact permanent fingerprints: **47,849 / 47,849 present**;
- historical collisions during idempotent re-import: **0**;
- missing historical fingerprints: **0**;
- pending historical transactions: **0**;
- isolated live transaction smoke: reserve **1**, collision-during **1**,
  rollback **1**, collision-after **0**;
- smoke cleanup: pending transactions **0**, leftover smoke fingerprints **0**.

After this certification, `registry.mode = r2`. New accepted leads no longer
append to the legacy Google Master Registry. Full lead records continue to be
written only to their dated Google workbooks; R2 keeps permanent hashed
cross-day dedupe fingerprints.

### Durable job intent development checkpoint

PR #159 restored canonical reviewed hash locks with all CI gates passing and superseded the failed #136 update. The additive SaaS app now implements internal transactional enqueue and pre-dispatch cancellation: membership/revision/source-policy gates, server-derived usage caps and a unique job outbox commit together. Default source policies remain disabled; synthetic test evidence is never seeded as real rights approval. Local regression verification covers rollback, tenant/role/revision denial, source/entitlement failure, replay and cancellation; real PostgreSQL CI additionally verifies concurrent duplicate enqueue and enqueue/cancel races. This advances M6 implementation only. No worker/provider/scheduler/payment/production launch is activated; lease recovery, dispatch-time rechecks, reservation expiry and web/billing/release acceptance remain open.

### Pre-dispatch lease development checkpoint

PR #160 passed all required checks, CodeQL and real PostgreSQL enqueue/cancel concurrency/migration gates before merge. Internal attempt leases now have fixed 60-second deadlines, one active token per intent and a three-attempt ceiling. Claim/check revalidate submitted-actor membership, entitlement, total outstanding and settled usage, search hash, source version/fingerprint and cancellation. Source kill switches, policy drift, reduced caps and expired/stale tokens fail closed. Cancelling queued work invalidates the active lease and releases pre-dispatch capacity. Local tests cover deadline expiry during preflight and bounded reclaim; PostgreSQL CI verifies concurrent lease exclusion. No provider execution, running-work failover, automated retry loop or background process is activated; dispatch-start/idempotency/uncertain-outcome recovery and reservation expiry remain open.

### Pre-dispatch recovery development checkpoint

PR #161 passed all required checks, CodeQL and real PostgreSQL lease exclusion/earlier concurrency/migration gates before merge. New internal intents now have one-day server deadlines, and leases cannot extend beyond them. The trusted `expire_pending_intents` command processes at most 100 overdue pre-dispatch intents per invocation, transactionally cancelling jobs/outbox/active tokens and releasing unused reservations. Running, settled, mismatched-tenant and unknown legacy deadlines are skipped. Local failure-injection tests verify rollback and safe replay; PostgreSQL CI verifies duplicate cleanup commits once. No cleanup schedule, consumer, external provider execution or ambiguous-outcome refund is activated. Next implementation boundaries are dispatch-start/idempotency/reconciliation, operational scheduling and complete web/billing workflows; external rights/customer/privacy/deployment/launch evidence remains open.

### Usage visibility development checkpoint

PR #162 passed all required checks, CodeQL and PostgreSQL duplicate cleanup/earlier concurrency/migration gates before merge. The isolated app now exposes a read-only workspace usage API and session page showing server-derived settled/reserved counters and limits, with membership checks and no balance mutation. Missing entitlement/counter rows remain inactive/zero without provisioning; billing period/reset fields are null. Route/template tests verify tenant boundaries, revoked access, viewer reads, method rejection and escaped workspace names. This starts independent web visibility work while full lead workflows, browser/accessibility/customer task validation and provider/data/billing/release acceptance remain open.

Current resume checkpoint stays within its existing compact-state size contract; prior checkpoint history is preserved in `docs/ai/CHECKPOINT-HISTORY-20261008.md`. No validator limits were relaxed.


### Read-only job history and details (development)

PR #163 passed all required checks, CodeQL and SaaS PostgreSQL regression/concurrency/migration gates (SaaS Quality run 37692371317). The session overview now links to tenant-scoped job history and saved-search details. History uses newest-first ordering, a 25-row bound and signed workspace-bound expiring continuation with a timestamp/UUID tie breaker. Reads recheck membership under the workspace lock; foreign and revoked access returns 404, viewers can read, and mutation methods are unavailable. Detail exposes saved scope, recorded status/counts and UTC timestamps without request hashes, lease tokens, provider errors or credentials. Draft/queued intent is not represented as execution or achieved results. No migration, provider call, retry/cancel/export control or schedule is introduced. Local route tests cover tenant isolation, escaping, pagination ties/inserts, malformed/expired/cross-workspace cursors and method rejection; full browser/accessibility/customer acceptance remains separate.


### Saved-search draft form (development)

PR #164 job history/detail passed repaired exact-head required checks, CodeQL and real PostgreSQL SaaS regression/migration gates (SaaS Quality 37695051762). Users with owner/admin/member roles can now save normalized searches from a CSRF-protected session form; viewers have no form control and server rejection remains authoritative. A signed expiring actor/workspace-bound token drives the existing transactional idempotency contract. Duplicate POST replays one draft; changing an already-used payload returns 409. Field validation reuses the API serializer, preserves invalid input and always includes phone qualification. Successful saves use a 303 redirect to job detail. The form does not queue, reserve usage, schedule, call providers or charge. Local SaaS suite is 65 passed plus 8 explicit PostgreSQL-only skips; final-head real PostgreSQL and required checks remain merge gates. Browser download failure remains isolated and full responsive/WCAG/customer validation open. Engineering assessment: `docs/ai/SAAS-JOB-WEB-ENGINEERING-REVIEW-20261008.md`.


### Confirmed pending-job cancellation (development)

PR #165 draft form passed exact-head required checks, CodeQL and SaaS PostgreSQL/migration gates (SaaS Quality 37695370079). Owner/admin/member users can review cancellation from draft/queued job details, then submit a CSRF-protected confirmation bound to actor/workspace/job/revision with a ten-minute expiry. Existing transactional cancellation rechecks role/state/revision, preserves the saved job and releases only unused pre-dispatch reservations while invalidating active leases. Duplicate submissions replay safely; stale/running/completed/unsupported states return conflict without cancelling or refunding settled usage. Viewers have no cancellation control and server authorization remains authoritative. Local SaaS suite is 72 passed with 8 explicit PostgreSQL-only skips; final-head required/CodeQL/PostgreSQL checks remain merge gates. No running cancellation, retry, provider dispatch, schedule or billing activation is added. Browser/WCAG/customer validation remains open after the documented browser-runtime/download failure.


### Source configuration preview (development)

PR #166 pending cancellation passed required checks, CodeQL and real PostgreSQL regression/concurrency/migration gates (SaaS Quality 37695788773). A session-only source page now shows at most 100 application policy codes/versions and recorded switch, free-collection declaration and capability values after tenant membership checks. It explicitly distinguishes configuration from live availability, collection/storage/export rights, entitlement eligibility, freshness and coverage. It creates no policy rows, seeds no synthetic rights, activates no source and exposes no private evidence/control references. Invalid/oversized capability metadata is unknown, all text is escaped, viewers can read and mutation methods are rejected. Local SaaS suite is 76 passed with 8 explicit PostgreSQL-only skips; final-head PostgreSQL/required/CodeQL gates remain required. Source activation, live adapters, dispatch reconciliation, browser/WCAG/customer acceptance and launch remain open. Engineering progress remains foundation 80%, orchestration 55%, web 40%; this bounded preview does not complete source feasibility or collection.


### Verified SaaS checkpoint and next frontier

PRs #175–#189 delivered internal zero-lead receipts, manual periods, disabled daily occurrences, native Next account/job workflows, signed candidate validation and the redacted candidate-event ledger. Django retains session, tenant/role/CSRF and transactional authority; Next.js remains the frontend.

PR #191 adds internal version-2 accepted-result storage and atomic actual usage settlement. Original candidate evidence plus two independent source/dedupe signatures bind a single-source complete 1–25-row batch. Workspace-unique fingerprint constraints, same-byte replay and v1/v2 terminalization exclusion prevent duplicate storage/accounting. Version-1 receipts keep zero-lead semantics. Signing registries default empty; tests do not prove a real R2 signer or provider rights.

PR #192 adds a bounded GET-only tenant/job results API and native Next server page. Current membership, source rights/fingerprint, allowed fields/lineage and retention deadlines are checked again. Revoked access is denied; expired or changed records are withheld without rewriting historical counts or usage. Plain escaped values and source/policy/retention metadata are displayed; raw source references, signatures and dedupe tokens are excluded.

PR #191 merged at 1d11e078a9a784f964c4743fc7b523b0f05307ed; head d7cabfae2fa53cf5daba19f0432bdb11b022b03b passed required checks/Actions CodeQL, PostgreSQL 37774522114 (all 202 tests, three acceptance races, migrations/settings) and Next/HTTP 37774522030 (nine transport tests/build/type and native flows).

PR #192 merged at 1f63f0283b68c7e005677d31157e77e26a84c366; head 5903e2d71c592ec03bdcb5c50939118a62b39fe3 passed required checks/Actions CodeQL, PostgreSQL 37776196602 (all 208 tests, concurrency, migrations/settings) and Next/HTTP 37776195589 (10 transport tests/build/type and stored-result, viewer/revocation/expiry/escaped-text flows).

All 208 SaaS tests pass on PostgreSQL, including acceptance/terminalization races, migrations and production settings checks. Local SQLite: 186 passed/22 PostgreSQL-only skips. Next lint/format/10 transport tests/build/type and real Django-to-Next HTTP flows pass. Root: 376 passed/1 skipped/28 subtests; Ruff/ANPOS pass. Actions-only CodeQL does not certify application source semantics. Browser/responsive/WCAG/customer acceptance remains open.

Engineering indicators: M5 85%, M6 75%, M7 75%, overall approximately 47%. These advance because internal accepted storage/accounting and authorized result viewing are verified. Of 21 work units: 9 complete, 5 in progress, 1 blocked, 2 deferred, 4 not started; full results/export work remains in progress. [Acceptance review](docs/ai/SAAS-ACCEPTED-RESULTS-REVIEW-20261008.md), [results view review](docs/ai/SAAS-NEXT-RESULTS-REVIEW-20261008.md) and [next slice](docs/ai/SAAS-NEXT-MUTATIONS-NEXT-SLICE.md) record boundaries.

Next: source-aware guarded export and retention-safe payload cleanup/tombstones. Real isolated R2 signer integration, signing-key lifecycle/crash reconciliation, multi-source/multi-batch pagination, billing events, recovery/signup, encryption/backups, shared-origin TLS/proxy and deployment acceptance remain open. Hiding expired payloads does not physically erase them. No live provider/payment/scheduler consumer or production Next deployment is activated. Production US/CA phone qualification, exact R2 dedupe, Google delivery and the 12,000/day target retain their contracts. Latest retained production evidence remains 6,855/12,000 on October 4; no new quota observation or work after turn end is claimed.

### Guarded CSV export (verified bounded API)

PR #194 merged at 6f9ad2b7808471c67523e31f1b42d37a710d9cd8; head 5dde3934edb0fdc2424b2fe4bb0d5e41e2eb9a46 passed required checks/Actions CodeQL, PostgreSQL 37779435828 (223 tests/export races/migrations/settings) and Next/HTTP 37779435876 (10 transport tests/build/type and CSRF CSV/replay/viewer denial). One export unit is one prepared CSV of at most 25 explicitly selected records; it does not certify delivery. Next preview/confirmation, physical payload cleanup and production rights remain open. [Review](docs/ai/SAAS-GUARDED-EXPORT-REVIEW-20261008.md).

### Source-deadline payload erasure (verified bounded command)

PR #195 merged at 92657c5c8bbdb27115e95f5642f841e8a1c975c3; head dc84dce770bf14580e9d2691880510fc6615ba14 passed required checks/Actions CodeQL, PostgreSQL 37780165591 (235 tests/expiry races/migrations/settings) and Next/HTTP 37780165669 (10 transport tests/build/type and payload erasure/tombstone flow). Cleanup is explicitly operator-invoked for one authorized workspace, at most 100 rows; no automated scheduler or backup-erasure certification is added. [Review](docs/ai/SAAS-RESULT-RETENTION-REVIEW-20261008.md).

### Native Next export preview (implementation awaiting CI)

Native Next export preview/confirmation implemented: bounded field omissions/attribution/count/deadline/one-unit notice, actor/job/selection/expiry-bound confirmation, direct CSRF POST CSV/replay and safe failure review. Full local/CI evidence pending. One initial batch at most 25; no row selection/pagination extension or browser certification. [Review](docs/ai/SAAS-NEXT-EXPORT-REVIEW-20261008.md).
