# VSN Lead Engine

Zero-paid-API lead discovery engine for Vertex Systems Network.

## Consent / runtime status

Real lead collection has been **APPROVED** by the user and the runtime gate is enabled.

The scheduled runner enforces a credential preflight. If the GitHub secret `GOOGLE_SERVICE_ACCOUNT_JSON` is missing, the real run exits safely without collecting or writing leads.

## Daily objective

- Countries: United States + Canada only
- 12 categories
- 1,000 accepted unique phone-qualified leads/category/day
- 12,000/day total target
- Registry-first writes
- Optional enrichment never blocks a phone-qualified lead
- FREE mode does not use paid discovery APIs

## Permanent workbook model

Lead data is written into one user-owned permanent Google Sheet:

- `US + Canada Business Leads — Master`
- `Overview` tab
- 12 category tabs
- every lead row stores `Date Added`
- daily counts are filtered to the current Asia/Karachi date
- the service account never creates daily spreadsheet files

This avoids service-account storage ownership/quota restrictions while preserving automated daily tracking.

## Pipeline

```
Free public sources
 -> normalize
 -> validate phone
 -> registry dedupe
 -> registry PendingDaily (batch)
 -> permanent workbook category append (batch)
 -> registry Active (batch)
 -> current-date counters
```

Initial discovery source: OpenStreetMap/Overpass with rate limiting. The adapter interface is intentionally pluggable for additional compliant public sources.

## Schedule

GitHub Actions: hourly from 08:00 through 23:00 Asia/Karachi (03:00–18:00 UTC).

## Production credential

A Google service account must have Editor access to:

- the permanent lead workbook
- the Master Registry

Add its JSON key as GitHub secret `GOOGLE_SERVICE_ACCOUNT_JSON`. Do not commit credentials.

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
- Runtime gate: **ENABLED**
- Permanent workbook: **CONFIGURED**
- Paid discovery APIs: **DISABLED**
- Real scheduled writes: enabled after credential/access verification
