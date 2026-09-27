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
discovered candidates and accepted leads. The scheduler uses an empirical yield
rate plus a small exploration bonus to rank metros **inside the same country**.

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
  `visits / discovered / accepted` counters;
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
