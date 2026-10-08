# Native Next workflows: delivered boundary and next frontier

PRs #180–#192 deliver native account/job/source/filter/correction workflows, candidate/event validation, dual-attested internal accepted storage/accounting and bounded current-rights results reads. Django remains session, tenant/role/CSRF and transactional authority; Next.js is the frontend. One complete single-source batch is limited to 25. Signer registries stay empty; no real R2 signer/consumer/source is activated.

PRs #194–#196 now verify guarded CSV preparation/accounting, explicit bounded source-expiry payload erasure with preserved dedupe tombstones, and native Next export preview/confirmation. Current rights/field grants, membership/CSRF, caps, replay/conflict and expiry remain authoritative. Same confirmation does not recharge; preview creates no CSV/counter. Viewer export action omitted. All 241 PostgreSQL cases and 11-test Next/HTTP CI pass; browser/customer acceptance remains open.

## Next bounded implementation

1. Add bounded current-batch result filters/selection and native presentation; specify visible/withheld/filtered counts without treating requested limits as achieved output. Preserve tenant/rights/expiry checks and maximum 25 records. Avoid personal contact values or full payloads in URLs/logs.
2. Bind export previews to explicit filtered selection without widening field/source/row authority. Recheck current roles/grants/deadlines and preserve once-only prepared-file accounting.
3. Review audit/fingerprint retention and backup/WAL/replica/downstream erasure before production. Existing command erases active row payloads only; it does not certify every copy erased or permit reaccepting duplicates.
4. Real isolated R2 signer onboarding must prove canonical qualification/fingerprint mapping, committed objects, independent keys and crash reconciliation. Preserve production CLI/R2/Google namespaces and zero-new-spend behavior; fixtures are not provider rights.
5. Multi-source/multi-batch intake and larger pagination require versioned contracts/concurrency tests. Signed billing-event reconciliation is independent safe work.

Recovery/signup, browser/keyboard/WCAG/customer, shared-origin TLS/proxy/cookies, provider rights and deployment/launch acceptance remain open.
