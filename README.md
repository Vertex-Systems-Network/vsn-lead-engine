# VSN Lead Engine

Zero-paid-API lead discovery engine for Vertex Systems Network.

## Safety / consent gate

Real lead collection is **OFF by default**. Scheduled runs will not collect or write leads until explicit user approval is given and `config/runtime.json -> runtime.enabled` is changed to `true`.

## Daily objective

- Countries: United States + Canada only
- 12 categories
- 1,000 accepted unique verified-phone leads/category/day
- 12,000/day total target
- Registry-first writes
- Optional enrichment never blocks a phone-verified lead
- FREE mode does not use paid discovery APIs

## Pipeline

```
Free public sources
 -> normalize
 -> validate phone
 -> registry dedupe
 -> registry PendingDaily
 -> daily-sheet append
 -> registry Active
 -> counters
```

Initial discovery source: OpenStreetMap/Overpass with rate limiting. The adapter interface is intentionally pluggable for additional compliant public sources.

## Schedule

GitHub Actions: hourly from 08:00 through 23:00 Asia/Karachi (03:00–18:00 UTC). While collection is disabled, scheduled runs exit safely.

## Production prerequisite

A Google service account must have access to the configured Drive folder and Master Registry. Add its JSON key as GitHub secret `GOOGLE_SERVICE_ACCOUNT_JSON`. Do not commit credentials.

## Local commands

```bash
python -m pip install -e ".[dev]"
python -m vsn_lead_engine.cli validate
pytest
python -m vsn_lead_engine.cli run --dry-run
```

## Current status

- Foundation: setup PR
- Lead collection: **NOT STARTED — awaiting user consent**
