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

This specifically prevents errors such as `retirement_home` matching the
Cars keyword `tire`, or a dermatology business entering Salon only because
its name contains `Beauty`.

## Country-balanced priority scheduler

Discovery does not derive geography from accepted lead count.

Every workflow run gets an independent cursor (GitHub run number in Actions).
The scheduler now combines three controls:

1. **Country balancing:** US and Canada metros are interleaved. The country with
   fewer usable leads today is scheduled first, so Canada cannot remain stuck
   behind a long US-only geography list.
2. **Progress weighting:** categories below 25% of target receive 3× shard
   weight, categories from 25-50% receive 2×, and categories above 50% receive
   normal weight.
3. **Rotation:** metro order changes with the run cursor so an empty shard does
   not repeat forever.

A run can try up to 18 category/geography shards, while the accepted-write
ceiling remains 1,000 leads/run.

## Permanent workbook model

Lead data is written into one user-owned permanent Google Sheet:

- `US + Canada Business Leads — Master`
- `Overview` tab
- 12 category tabs
- every lead row stores `Date Added`
- daily counts use the current `Asia/Karachi` date
- the service account does not create daily spreadsheet files

Overview tracks shard attempts, zero-result shards, source errors, and live
United States / Canada usable-lead totals.

## Pipeline

```
Overture Places
 -> rotating category/geography shard
 -> taxonomy-first classification
 -> normalize phone
 -> Master Registry dedupe
 -> Registry PendingDaily (batch)
 -> permanent workbook category append (batch)
 -> Registry Active (batch)
 -> current-date counters
```

Optional self-hosted/approved Overpass can be enabled separately, but public
community Overpass instances are not the scheduled production default.

## Schedule

GitHub Actions: hourly from 08:00 through 23:00 Asia/Karachi (03:00–18:00 UTC).

## Production credential

A Google service account must have Editor access to:

- the permanent lead workbook
- the Master Registry

Its JSON key is stored as GitHub secret `GOOGLE_SERVICE_ACCOUNT_JSON`.
Credentials must never be committed.

## Local commands

```bash
python -m pip install -e ".[dev]"
python -m vsn_lead_engine.cli validate
pytest
python -m vsn_lead_engine.cli run --dry-run
```

## Current status

- Foundation: merged
- User consent: **APPROVED**
- Google integration: **VERIFIED**
- Permanent workbook: **CONFIGURED**
- Overture Places source: **ENABLED**
- Country-balanced priority scheduling: **ENABLED**
- Taxonomy-first classification: **ENABLED**
- Public community Overpass production use: **DISABLED**
- Paid discovery APIs: **DISABLED**
