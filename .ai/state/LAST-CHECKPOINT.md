# Last Checkpoint

## Snapshot

- Vertex-Systems-Network/vsn-lead-engine; 2026-10-08 UTC / PKT.
- Protected feature main read: `0a81b3e24f45edfa72b5101c8241891030a88f1c` / PR #189. This recorded feature base precedes the checkpoint documentation merge; reconcile exact live main/issues/PRs before replay.
- Next.js/TypeScript frontend; Django/DRF/PostgreSQL retain auth, tenant/role/CSRF and transactional authority. Production CLI/R2/Google behavior remains isolated.

## Verified

- PR #189 merged at 0a81b3e24f45edfa72b5101c8241891030a88f1c; head fb58dd787290a81813f3c85a412f897782b5ffd7 passed required checks/Actions CodeQL, PostgreSQL 37770588647 (all 182 tests, including three candidate-event races, migrations/settings) and Next/HTTP 37770588715 (nine transport tests/build/type and native workflows).
- PR #188 head a942efbacd299ee2460eb560da00d899b7f58f3f / merge 1baf1d80fa6aafca5420cf21a640ce7e7a9e7146: required/Actions CodeQL, PostgreSQL 37770063209 (172 cases), Next/HTTP 37770063198 passed.
- Internal signed candidate preflight binds current tenant/job/operation/source/provider key/request hash/policy fingerprint. Separate verifier registry empty by default; exact-byte schema, bounds, phone/USCA/saved scope, field lineage, purpose, explicit display/storage/retention and current kill switch fail closed.
- Frozen review exposes only event ref/digest/count/deadline. Redacted one-event-per-operation ledger records no payload/signature/source record references. Same bytes replay without refreshing timestamps; changed bytes/event and global source-event rebind conflict. Every replay rechecks current role/rights/expiry. Three PostgreSQL races pass; failed writes roll back. Additive migration supports empty reversal and refuses populated evidence loss.
- PR #186 native login/bootstrap/attempt limits/rotation and cancellation-error review remain verified. PRs #180–#184 native Next draft/cancel/source/filter/validation/sign-out remain verified. No fresh cancel authority is minted by an error page; direct browser credentials go to Django.
- PRs #175–#178 zero-lead terminal receipt reconciliation, manual periods, disabled daily occurrences and session navigation remain verified. Unknown effects retain reserved capacity; current terminal receipts still settle zero leads/exports.
- PostgreSQL all 182 cases/migrations/settings pass. Local 163 passed/19 PostgreSQL-only skips. Next lint/format/nine transport tests/build/type and real HTTP pass. Root 376 passed/1 skipped/28 subtests; Ruff/ANPOS/drift pass. Actions CodeQL is Actions-only.
- M5 85%, M6 70%, M7 70%, overall ~45% are engineering indicators. Work units unchanged: 9 complete, 5 in progress, 1 blocked, 2 deferred, 4 not started of 21. README and traceability reflect verified slices rather than whole-work-unit completion.

## Not Verified

- No accepted-result store, nonzero accounting, R2 uniqueness grant, result/export endpoint or live adapter follows from candidate evidence. Receipt and candidate verifier registries remain unconfigured. Payment/provider/scheduler consumers remain disabled.
- Billing events, recovery/signup, browser/responsive/WCAG/customer acceptance, shared-origin TLS/proxy/cookies, retention/encryption/physical cleanup/backup acceptance and production Next deployment remain open. No usable local browser binary was available; HTTP is not browser certification.
- Persistent distributed-agent identity remains unverified. No work after turn end claimed. Latest retained production evidence: 6,855/12,000 on 2026-10-04; no new quota observation.

## Known Risk

- Phone syntax/provenance signatures are not reachability, territory accuracy, provider rights or exact cross-day dedupe proof. Candidate count cannot settle leads or be shown as accepted results.
- Candidate freshness deadline does not physically erase redacted audit metadata. DATA-006 records the before-production retention/cleanup/backup gate; opaque event references must exclude personal data. One event/operation does not support multi-batch intake without a versioned extension.
- Current authority is rechecked on candidate replay; closed/expired/revoked/drifted operations fail closed even when evidence was previously recorded. Evidence migrations protect history rather than silently deleting it.
- Existing draft feedback read expiry is not physical session erasure; cleanup/encryption acceptance remains open. Unknown provider effects retain capacity until valid terminal evidence. ESLint 9/plugin compatibility EOL remains a production gate.

## Accepted-result candidate

PR #191 merged at 1d11e078a9a784f964c4743fc7b523b0f05307ed; head d7cabfae2fa53cf5daba19f0432bdb11b022b03b passed required checks/Actions CodeQL, PostgreSQL 37774522114 (all 202 tests, three acceptance races, migrations/settings) and Next/HTTP 37774522030 (nine transport tests/build/type and native flows). See ADR-SAAS-005 / SAAS-ACCEPTED-RESULTS-REVIEW-20261008.

Current-rights bounded tenant/job result API and native Next view implemented: source/fingerprint/field lineage/retention checks, escaped source/field/deadline display and empty/withheld states. Six read tests; local SaaS 208 cases (186 passed/22 PostgreSQL skips); final Web/HTTP and exact-head CI pending.

## Next Action

1. Continue reviewed versioned nonzero accepted-result/accounting and trusted dedupe contracts; then bounded tenant result reads and source-aware export. Keep production R2 namespaces/workbooks isolated and live consumers disabled.
2. Preserve atomic lead/export caps, source field/export rights, revocation/retention/tombstones, safe CSV and privacy-safe audits. Existing candidate validation/replay must not be reimplemented as completed acceptance.
3. Billing-event reconciliation is independent safe work; external source/legal/customer/provider/deployment evidence remains separate. Continue ready frontier within invocation budget; checkpoints are recovery aids, not permission gates.
