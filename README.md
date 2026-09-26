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
coverage, public contact completeness, query execution and dedupe.

## Primary free source

Production discovery now uses **Overture Maps Places**, queried directly from
its public GeoParquet release with DuckDB. The dataset exposes place names,
categories, phones, websites, emails, socials and addresses when available.

The engine resolves the current Overture release from the official STAC
catalog instead of hardcoding a release.

See [DATA_SOURCES.md](DATA_SOURCES.md) for licensing/compliance notes.

## Anti-stall shard scheduler

Discovery no longer derives geography from accepted lead count.

Every workflow run gets an independent cursor (GitHub run number in Actions).
The cursor rotates:

1. tied pending categories;
2. metro geographies;
3. up to 12 category/geography shard attempts per run.

A zero-result query therefore cannot pin future runs to the same
`AI & Automation / Phoenix` shard indefinitely.

## Permanent workbook model

Lead data is written into one user-owned permanent Google Sheet:

- `US + Canada Business Leads — Master`
- `Overview` tab
- 12 category tabs
- every lead row stores `Date Added`
- daily counts use the current `Asia/Karachi` date
- the service account does not create daily spreadsheet files

Overview also tracks shard attempts, zero-result shards and source errors.

## Pipeline

```
Overture Places
 -> rotating category/geography shard
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
- Independent shard rotation: **ENABLED**
- Public community Overpass production use: **DISABLED**
- Paid discovery APIs: **DISABLED**
