# Bounded country filters and native selected-row CSV review

The user story is Results → country GET filter → scoped export preview → record/field checkboxes → native Django CSRF POST → selected CSV and once-only receipt. Next remains the frontend; Django owns current tenant/role/source/retention/entitlement/usage authority. The complete single-source accepted batch remains at most 25; no new ingestion, provider, billing or persistence boundary is added.

## Contract and review

Results and export-form GET accept exactly one optional country parameter: US, CA or empty (All). Unknown, repeated or unsupported query values fail closed. Filtering runs after every current-rights, fingerprint, payload, lineage and expiry check. `withheld_count` counts unavailable recorded rows; `filtered_count` counts otherwise available rows excluded by country. Displayed + filtered + withheld stays bounded by 25. Country filters contain no contact/search values and never authorize a row. Next validates the bounded enum, response echo/counts/countries and exact transport paths; ordinary result reads still forward only session, export-form reads require session and CSRF cookies. Filtered export links and preview back links retain the country. No pagination beyond this batch is claimed.

The preview returns only authorized row UUID, escaped business name and country for selection; no phone, private source reference, signer/dedupe token or full lead payload is added to preview. Signed scope includes exactly the currently visible filtered IDs, common permitted fields, actor/workspace/job, deadline and UUID request key. POST requires 1–25 unique canonical result UUIDs and 1–6 unique allowed fields, all subsets of that signature scope. No selected IDs or signed token appear in query URLs. Empty, duplicate, outside-scope, malformed and oversized selections reject before CSV/accounting. Choosing a narrower subset does not widen common field rights or extend the preview's conservative earliest deadline.

Private confirmation salt advances from v1 to v2 to require explicit row selection. Previous all-row forms fail closed with Review a new preview; there is no silent fallback to exporting all records. The JSON export API remains unchanged. Coordinated backend/Next rollback requires a new preview; this development-only surface is not deployed to customers. No database migration is needed.

The shared atomic preparation service rechecks current membership, source/export field grants/fingerprint, selected-row availability/deadline, entitlement/window and caps (including reservations). One unit means one prepared file, regardless of selected row count. Identical accepted token/rows/fields replay without another charge; changing accepted rows or fields on that key conflicts. Unselected-row erasure cannot add authority or invalidate a still-current selected subset before the conservative token deadline. Selected-row erasure/rights revocation still denies export. Signed previews and CSV copies are never persisted; unchanged pseudonymous receipt ledger/retention limits apply.

## Verification evidence

Local backend: 247 cases, 221 passed and 26 PostgreSQL-only skips; root regression 376 passed/1 skipped/28 subtests. Ruff and ANPOS pass. Next lint/format, 12 transport tests, build/type pass; actual HTTP smoke passes across filtered/empty results, selected-row confirmation and retained auth/erasure flows and exact-head PostgreSQL/Web CI evidence reconciled after merge. Backend tests cover genuine dual-attested two-row acceptance → subset-only CSV → identical replay → changed-selection conflict, unselected expiry/erasure, empty/duplicate/foreign/oversized IDs, prior v1 rejection, filter-versus-withheld counts, empty scope and readonly preview. Existing transactional export/expiry/acceptance PostgreSQL race tests remain authoritative through the shared service. No new lock ordering or writes are introduced.

Actual HTTP smoke follows native country filter and filtered link → Next preview and escaped selectable names → direct CSRF CSV/receipt → empty-selection denial/replay/conflict, with existing viewer/revocation/expiry/erasure/auth flows. React review: server components, one bounded fetch per page, no request-shared mutable state, stable UUID keys, persistent select label and checkbox fieldset/legend, plain escaped text, no client effects or write proxy. Browser/visual/responsive/keyboard/WCAG/customer acceptance is unverified; HTTP is not browser evidence.

## Remaining boundary

Category/source/full-text filters, broader multi-batch pagination, real isolated R2 signer/source-rights intake, customer billing/scheduler, production deployment and legal/backup/audit retention acceptance remain open. Synthetic fixture grants prove application contracts only. Production US/CA phone-only qualification, exact production R2 cross-day dedupe, Google delivery and daily target are unchanged.

## Verified protected merge

PR #198 merged at 7dd9f10b4c28b1bacea1488aee5874685f600e3a; head 141cbac20f05b9edc3f63a4374fbc3612766140c passed all required checks/Actions CodeQL, PostgreSQL 37784930553 (all 247 tests, concurrency, migrations/settings) and Web 37784930581 (12 transport tests, build/type and HTTP country-filter/selected-row CSV/empty denial/replay/conflict/erasure/auth flows).
