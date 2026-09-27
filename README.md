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
 -> normalize phone
 -> Registry dedupe (Sheets migration source; R2 permanent ledger)
 -> Registry PendingDaily
 -> dated workbook append
 -> Registry Active
 -> dated Overview counters
```

## Reliability and schedule

The quota supervisor is the primary hourly controller at **:00** from 08:00
through 23:00 Asia/Karachi. GitHub Actions keeps a staggered **:30 fallback**
from 08:30 through 22:30, avoiding same-minute duplicate triggers while retaining
an independent recovery path.

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
  completion or zero accepted progress;
- the same source objects, Google clients and frozen run date are reused across
  cycles while live Sheet/Registry state is re-read for safety.

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
