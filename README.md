# VSN Lead Engine

Zero-paid-API lead discovery engine for Vertex Systems Network.

## Consent / runtime status

Real lead collection has been **APPROVED** by the user and the runtime gate is enabled.

The scheduled runner still enforces a credential preflight. If the GitHub secret `GOOGLE_SERVICE_ACCOUNT_JSON` is missing, the real run exits safely without collecting or writing leads. As soon as the credential is configured, the next scheduled run can start automatically.

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

GitHub Actions: hourly from 08:00 through 23:00 Asia/Karachi (03:00–18:00 UTC).

## Production credential

A Google service account must have access to the configured Drive folder and Master Registry. Add its JSON key as GitHub secret `GOOGLE_SERVICE_ACCOUNT_JSON`. Do not commit credentials.

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
- Paid discovery APIs: **DISABLED**
- Real scheduled writes: start automatically after Google credential preflight succeeds
