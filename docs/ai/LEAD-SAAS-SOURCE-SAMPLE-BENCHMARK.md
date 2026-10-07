# SaaS Source Sample Benchmark Protocol

**Status:** protocol prepared; no source sample has been acquired or benchmarked.  
**Snapshot:** 2026-10-06 PKT  
**Parent:** `docs/ai/LEAD-SAAS-SOURCE-FEASIBILITY.md`  
**Purpose:** turn source feasibility claims into a reproducible, rights-aware measurement plan. This does not select a provider or approve collection.

## Preconditions (hard stops)

Do not query, download, scrape, or retain source records until all applicable items are true:

1. Owner has selected a test country, niche, record type (business/place vs named person), required fields, and intended customer-visible use.
2. The exact source, endpoint/dataset release, plan, applicable terms, storage/retention/export rights, attribution and permitted territory are documented in the source eligibility register.
3. A qualified review has cleared the proposed collection and use where rights/privacy interpretation is needed.
4. A no-production test workspace, credentials, rate limits, deletion path, and spend cap are configured. No production customer or personal contact data is used.
5. The test uses provider-authorized access. Do not use public community endpoints as a benchmark service without operator authorization; do not infer upstream permission from a reseller's product or price.

If a gate is unresolved, mark the source **not testable** and record the exact missing evidence. Do not replace it with scraping or an unapproved free tier.

## Freeze the benchmark brief before collection

Record these fields and have the owner approve the brief before results are seen:

- Test ID and date window; decision owner; test operator.
- Target user segment (hypothesis), country/region, one niche/taxonomy, business/place or person search.
- Search intent, exact query/filter, geographic boundary and inclusion/exclusion rules.
- Required fields and minimum acceptable freshness; definition of a unique entity and duplicate rule.
- Sources eligible under written terms; endpoint/dataset version and field mask.
- Sample procedure and target size. Use the same brief and boundary for each source; do not tune queries after seeing one source's results.
- Maximum calls, records, operator time and cash cost; source-specific caps.
- Predeclared decision thresholds for field completeness, rights-eligible yield, duplicate rate and total cost per usable record. Leave thresholds blank until the owner sets them; never invent a pass from observed results.

## Sampling procedure

1. Choose one bounded country/niche brief only after gates pass. For batch data, record release ID, extraction timestamp, geographic polygon/query rules and snapshot method. For APIs, record endpoint, API version, request fields, pagination and timestamp.
2. Run the same brief independently for each eligible source within the approved window. Save request/response metadata and source identifiers permitted by its terms. Never retain disallowed attributes just to compare them.
3. Where the source allows repeated queries, run three repeats on separate days or documented refreshes to estimate volatility. If not allowed or feasible, report one observation and mark stability unknown.
4. Normalize only into a temporary comparison schema; preserve raw-to-normalized field mapping and source/license provenance. Use a keyed hash for comparison if retaining source IDs is not permitted.
5. Deduplicate both within source and across sources using a documented entity rule (e.g., normalized domain, then phone, then name+address). Record uncertain matches separately; do not silently merge.
6. Manually review a predeclared random sample for entity match and field plausibility. Record reviewer decisions without collecting extra personal data. Reviewer agreement can be measured only if two reviewers independently inspect the same permitted sample.
7. Delete source data and credentials at the end of the approved retention window; retain only the metrics/metadata that the terms allow.

## Metric definitions

Use explicit denominators and report missing/unknown separately:

| Metric | Calculation |
|---|---|
| Raw returned | Number of rows returned before normalization/deduplication |
| Unique entities | Distinct entities after the frozen matching rule |
| Required-field completeness | Unique entities with every required field / unique entities |
| Per-field completeness | Unique entities with a non-empty usable value for that field / unique entities |
| Rights-eligible usable entities | Unique entities meeting required fields and confirmed rights for intended customer display/export |
| Eligible yield | Rights-eligible usable entities / raw returned; also report / unique entities |
| Duplicate rate | (raw returned − unique entities) / raw returned |
| Freshness observed | Counts by verifiable age band; if retrieval/update date is absent, mark unknown (do not infer from API response date) |
| Match plausibility | Manually reviewed records judged to match the frozen business/place brief / reviewed records |
| Unit cash cost | Provider charges + attributable compute/egress/storage for the run; state excluded shared costs |
| Operator time | Setup, cleaning, review and support minutes measured separately |
| Cost per eligible usable entity | Unit cash cost / rights-eligible usable entities; if denominator is zero, report N/A |
| Source stability | Change in eligible unique entities/required-field completeness across repeats; only where repeats are allowed |

Report sample size, query limitations, missing denominators and terms version next to every metric. Never present vendor-wide advertised coverage as measured coverage.

## Results table (one row per source × brief × run)

| Test ID | Source / exact product | Terms/version gate | Market/niche brief ID | Run timestamp | Raw | Unique | Required complete | Rights-eligible usable | Eligible yield | Duplicate rate | Freshness unknown % | Cash cost | Operator min | Cost/usable | Exceptions / deletion date |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| pending | not selected | unresolved | not selected | not run | — | — | — | — | — | — | — | — | — | — | No collection authorized/performed |

## Decision rule and interpretation

- First disqualify a source that fails rights, security, or permitted-use gates, regardless of yield or price.
- Among eligible sources, compare only against thresholds frozen before collection. Preserve results that fail.
- A source with a high raw count but low required-field completeness or rights-eligible yield is not a successful lead source.
- Report one segment/market result as a bounded sample, not a global coverage guarantee.
- Sample yield and cost can inform MVP economics; they cannot establish customer demand, willingness to pay, or usability. Those require separate user research.
- Do not choose a provider solely because its free tier or retail per-record price appears low.

## Blank run log

```text
Test ID / owner / operator:
Owner-approved brief and threshold record:
Source and exact terms/version:
Written use/storage/export rights evidence:
Qualified review reference (if applicable):
Market / niche / boundary:
Query / endpoint / fields / dataset release:
Run date/time and repeat number:
Raw rows / unique entities:
Required field definitions and completeness:
Rights-eligible usable count:
Freshness evidence / unknowns:
Duplicate and match rules:
Cash cost, shared-cost exclusions:
Operator minutes:
Exceptions, rate limits, partial failures:
Deletion completed / date / allowed retained metrics:
Decision and rationale:
```

No provider is approved by this protocol. The first valid run remains blocked until the owner selects a concrete segment/market brief and source-specific rights gates are cleared.
