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
- Cross-day dedupe through the Master Registry
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
5. keep the Master Registry separate as the cross-day dedupe source.

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

A run can try up to 18 category/geography shards, while the accepted-write
ceiling remains 1,000 leads/run.

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
 -> Master Registry dedupe
 -> Registry PendingDaily
 -> dated workbook append
 -> Registry Active
 -> dated Overview counters
```

## Schedule

GitHub Actions: hourly from 08:00 through 23:00 Asia/Karachi (03:00–18:00 UTC).

## Production credential

The Google service account needs access to:

- the configured lead folder / dated workbook
- the Master Registry

Google Sheets API and Google Drive API must remain enabled. The JSON key is
stored as GitHub secret `GOOGLE_SERVICE_ACCOUNT_JSON`.

## Current status

- User consent: **APPROVED**
- Google integration: **VERIFIED**
- Daily dated workbook routing: **ENABLED**
- Master Registry cross-day dedupe: **ENABLED**
- Overture Places source: **ENABLED**
- Country-balanced priority scheduling: **ENABLED**
- Taxonomy-first classification: **ENABLED**
- Public community Overpass production use: **DISABLED**
- Paid discovery APIs: **DISABLED**
