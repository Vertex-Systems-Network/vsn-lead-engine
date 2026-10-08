# Native Next workflows: delivered boundary and next frontier

PRs #180–#192 deliver native account/job/source/filter/correction workflows, candidate/event validation, dual-attested internal accepted storage/accounting and bounded current-rights results reads. Django remains session, tenant/role/CSRF and transactional authority; Next.js is the frontend. One complete single-source batch is limited to 25. Signer registries stay empty; no real R2 signer/consumer/source is activated.

PRs #194–#196 now verify guarded CSV preparation/accounting, explicit bounded source-expiry payload erasure with preserved dedupe tombstones, and native Next export preview/confirmation. Current rights/field grants, membership/CSRF, caps, replay/conflict and expiry remain authoritative. Same confirmation does not recharge; preview creates no CSV/counter. Viewer export action omitted. All 241 PostgreSQL cases and 11-test Next/HTTP CI pass; browser/customer acceptance remains open.

## Next bounded implementation

1. Country filters and explicit native row/field selection are verified and merged through PR #198; 247 PostgreSQL tests and 12-test Next/HTTP CI pass. PR #200 verifies saved category/source filters and exact combined export scope; 253 PostgreSQL tests and 13-test Next/HTTP CI pass. See SAAS-RESULT-METADATA-FILTER-REVIEW-20261008.md. Keep displayed/filtered/withheld counts distinct and preserve the single-batch 25-row ceiling.
2. Current signed previews bind filtered row scope and require an explicit subset. Maintain common field grants, conservative deadlines, current role/rights checks and once-only prepared-file accounting. See SAAS-RESULT-FILTER-SELECTION-REVIEW-20261008.md; browser/customer acceptance remains open.
3. Review audit/fingerprint retention and backup/WAL/replica/downstream erasure before production. Existing command erases active row payloads only; it does not certify every copy erased or permit reaccepting duplicates.
4. Real isolated R2 signer onboarding must prove canonical qualification/fingerprint mapping, committed objects, independent keys and crash reconciliation. Preserve production CLI/R2/Google namespaces and zero-new-spend behavior; fixtures are not provider rights.
5. Multi-source/multi-batch intake and larger pagination require versioned contracts/concurrency tests. Signed billing-event reconciliation is independent safe work.

Recovery/signup, browser/keyboard/WCAG/customer, shared-origin TLS/proxy/cookies, provider rights and deployment/launch acceptance remain open.

## Delivered receipt history and next foundation frontier

PR #202 verifies readonly redacted settled receipts, 25-row signed pages, current owner/admin job or member-own scope and retained no-charge metadata after payload erasure. No CSV delivery proof or stored download exists. All 259 PostgreSQL cases and 14-test Next/HTTP CI pass; see SAAS-EXPORT-RECEIPT-HISTORY-REVIEW-20261008.md. Production logging/privacy and browser/customer acceptance remain open.

Implement provider-neutral signed billing-event validation/reconciliation under WU-SAAS-FOUNDATION, with verifier registries disabled by default, preserving reservations/windows and no live payment activation. Real signer/live consumers and production gates remain unavailable.

PR #204 verifies the pure normalized billing-evidence validator with ten DB-forbidden adversarial tests and no storage/write/endpoint activation; all 269 PostgreSQL cases and 14-test Next/HTTP CI pass. The next implementation is disabled durable bindings/redacted ledger, exact replay/contiguous revisions and comprehensive entitlement-expiry guards before any billing write path. See SAAS-BILLING-EVIDENCE-REVIEW-20261008.md.

## Current frontier after verified PRs #207–#209

The previously planned pure billing parser and transactional binding/ledger/deadline slice are delivered through PR #207, with readonly diagnostics/active-admin recovery boundaries through PR #208. Both remain internal and default disabled; no provider/payment activation is established. PR #209 adds a separate pure v3 batch-proof validator and ADR-SAAS-003. All five exact-head workflows passed; latest PostgreSQL 37812348239 verifies 306 cases/migrations/settings, Web 37812348326 verifies 14 transport/build/type/HTTP cases. Full browser/customer/provider/privacy/deployment acceptance remains open.

Next implement separately gated durable v3 batch identity/ledger and trusted terminal manifests with additive preservation-safe migrations, then atomic partial-batch/final accounting and stable-watermark signed 25-row pagination. Preserve delivered v2 single-source/one-batch settlement and export contracts. A valid proof-shaped manifest has no durable replay/ordering/qualification authority. Unknown effects retain full reservations. Follow ADR-SAAS-003 and the latest compact checkpoint; do not replay the old billing frontier described above.
