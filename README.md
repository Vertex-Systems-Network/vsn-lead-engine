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
- P12 protected-main governance: **LIVE RULESET ACTIVE — PR + STRICT VALIDATE + SQUASH-ONLY**
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
