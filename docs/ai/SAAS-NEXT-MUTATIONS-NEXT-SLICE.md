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

## Next ready receipt-recovery slice

Expose bounded readonly tenant/job export-receipt metadata from the existing redacted ledger, with explicit current role/creator scope. Show preparation accounting/expiry and explain that no retained CSV copy or confirmed download exists. GET must not prepare/replay CSV, refund, reserve or charge usage. Avoid contact fields, digests, signing/source references and mutable provider activation. Signed billing-event reconciliation remains a separate M5 frontier.

Receipt history is implemented as a candidate with current creator/role scope and signed bounded navigation; verify protected-head CI before marking delivered. See SAAS-EXPORT-RECEIPT-HISTORY-REVIEW-20261008.md. Next independent plan frontier is provider-neutral signed billing-event validation/reconciliation design with verifier defaults disabled, preserving existing reservations/windows and no live payment activation.
