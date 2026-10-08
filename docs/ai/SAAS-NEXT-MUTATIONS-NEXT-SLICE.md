# Native Next workflows: delivered boundary and next frontier

PRs #180–#192 deliver native account/job/source/filter/correction workflows, candidate/event validation, dual-attested internal accepted storage/accounting and bounded current-rights results reads. Django remains session, tenant/role/CSRF and transactional authority; Next.js is the frontend. One complete single-source batch is limited to 25. Signer registries stay empty; no real R2 signer/consumer/source is activated.

PRs #194–#196 now verify guarded CSV preparation/accounting, explicit bounded source-expiry payload erasure with preserved dedupe tombstones, and native Next export preview/confirmation. Current rights/field grants, membership/CSRF, caps, replay/conflict and expiry remain authoritative. Same confirmation does not recharge; preview creates no CSV/counter. Viewer export action omitted. All 241 PostgreSQL cases and 11-test Next/HTTP CI pass; browser/customer acceptance remains open.

## Next bounded implementation

1. Country filters and explicit native row/field selection are verified and merged through PR #198; 247 PostgreSQL tests and 12-test Next/HTTP CI pass. Richer category/source filters require their own bounded metadata contract. Keep displayed/filtered/withheld counts distinct and preserve the single-batch 25-row ceiling.
2. Current signed previews bind filtered row scope and require an explicit subset. Maintain common field grants, conservative deadlines, current role/rights checks and once-only prepared-file accounting. See SAAS-RESULT-FILTER-SELECTION-REVIEW-20261008.md; browser/customer acceptance remains open.
3. Review audit/fingerprint retention and backup/WAL/replica/downstream erasure before production. Existing command erases active row payloads only; it does not certify every copy erased or permit reaccepting duplicates.
4. Real isolated R2 signer onboarding must prove canonical qualification/fingerprint mapping, committed objects, independent keys and crash reconciliation. Preserve production CLI/R2/Google namespaces and zero-new-spend behavior; fixtures are not provider rights.
5. Multi-source/multi-batch intake and larger pagination require versioned contracts/concurrency tests. Signed billing-event reconciliation is independent safe work.

Recovery/signup, browser/keyboard/WCAG/customer, shared-origin TLS/proxy/cookies, provider rights and deployment/launch acceptance remain open.
