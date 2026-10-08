# Last Checkpoint

## Snapshot

- Vertex-Systems-Network/vsn-lead-engine; 2026-10-08 UTC / PKT.
- Exact protected payload-schema feature main `2c422919a607d116b687ca45994597b581773faa` after PR #220, before documentation-only checkpoint merge. Live open Issues/PRs reconciled before development; none open at feature checkpoint.
- Product 0.66.1 / ANPOS 1.4.0; Next frontend and isolated Django/DRF/PostgreSQL authority. Existing production CLI/R2/Google namespaces and phone-only US/Canada/taxonomy/quota invariants preserved.

## Verified

- PR #207 merged `8d555bf041b05690838b74b46406541abb68bd81`, head `d9be9ac1ef0303b70be62e4e8c1a9de592205cc0`. All five workflows passed, including PostgreSQL 37810735757 (290 tests, five billing races, migrations/settings) and Web 37810735885 (14 transport/build/type/actual HTTP). Disabled internal billing ledger, exact replay/contiguous revisions, grant deadlines and preservation of usage/periods/reservations. Past-effect settlement and safe cancellation retained. Migration 0017 refuses destructive evidence loss.
- PR #208 merged `7e93dc814e3bbf64ec95052a3a8f9df79c1c5450`, head `3d34dccd09e95b8fe0cc7b58b4e8c6b3a5cf8a62`. All five workflows passed, PostgreSQL 37811482736 (296 tests/migrations/settings), Web 37811482692 (14 tests/actual HTTP). Readonly redacted local billing diagnostics and active-user/admin gates, six new tests and preservation-first recovery runbook. No repairs/provisioning.
- PR #209 merged `176f8309a1d68c2feb650898d240bd2ed5aa89fc`, head `7c5adceb3fb150a89aaed3c8f556aea2552602f4`. All five workflows passed, PostgreSQL 37812348239 (306 tests/migrations/settings), Web 37812348326 (14 tests/build/type/actual HTTP). Pure bounded v3 manifest parser, ten DB-forbidden cases, separate empty-default authorities. No ORM/network/intake or replay side effects. ADR-SAAS-003 defines additive durable batch/final accounting/pagination direction; v2 single-source/25-row terminal acceptance/export retained.
- Root local regression: 382 passed, 1 skipped, 28 subtests. Ruff/format/ANPOS/README/audit/migration checks passed. Local SaaS 383 cases / 42 explicit PostgreSQL-only skips; protected PostgreSQL verifies those races separately.
- Earlier scope/filter/guarded CSV/expiry/receipt evidence remains in git history and linked review documents through PR #204. Counts unchanged: 9 complete, 5 in progress, 1 blocked, 2 deferred, 4 not started of 21. M5 85%, M6 75%, M7 86%, overall ~52% engineering indicators; partial slices do not certify full work units.

- PR #211 merged at 866efda12bf3250fc55ca3af66036987c11ea47e; head bc07f8d24eab993d125a3f17b8dbf8e2d63e4b65 passed all five CI workflows, PostgreSQL 37816152759 (319 tests/migrations/settings) and Web 37816152845 (14 transport/build/type/HTTP). Four inert v3 metadata tables, protected links/count/uniqueness and populated rollback guard; no enrollment/intake/settlement.

- PR #212 merged at 20e2362ec6000a72e679a8716d428795f1a9d077; head b0f19291687c8b532b81a2f2bdd85e8c29758e9a passed all five workflows, PostgreSQL 37816828169 (329 tests/migrations/settings) and Web 37816828126 (14 transport/build/type/HTTP). Ten DB-forbidden bounded source-final proof cases; no enrollment/intake/finality/settlement authority.

- PR #214 merged at 412c29286500d8db88491e13074baa77a7648eb5; head f68067283ab1ab16d437e8bd4093a182ab4cda01 passed all five workflows, PostgreSQL 37821424861 (338 tests/migrations/settings) and Web 37821424914 (14 transport/build/type/HTTP). Disabled quarantined admin v3 enrollment, default-v2 classification, legacy proof exclusion and preserved cancellation; no allocation/intake/dispatch.

- PR #216 merged at 469c4ec883f0533f42291e9c717b39ec82a4a1d8; head 508878f54f85fe32f23b1719f48c5f5771a8fa6e passed all five workflows, PostgreSQL 37823442614 (350 tests/migrations/settings) and Web 37823442485 (14 transport/build/type/HTTP). Disabled server-owned UUID/ordinal allocation, original caps, exact identity replay and unknown-effect preservation; no reachable v3 start/intake.

- PR #217 merged at 81423210ec1500a5e2006d8985d7f8da4f19265f; head ca1cd8ec52706de4cba9ad37745cfff5ee1795c1 passed all five workflows, PostgreSQL 37824016673 (358 tests/migrations/settings) and Web 37824016597 (14 transport/build/type/HTTP). Pure batch-bound candidate proof and shared eligibility, eight DB-forbidden cases; no durable candidate/acceptance.

- PR #218 merged at 15814cf0bf0c52f58c4b1d1e31cc208bc3445199; head f9d0173c03fac4a757a605dfed3e30f38c98cb3e passed all five workflows, PostgreSQL 37824615261 (366 tests/migrations/settings) and Web 37824615227 (14 transport/build/type/HTTP). Disabled durable redacted candidate ledger, exact replay/reference conflicts and unknown-effect preservation; no accepted payload/finality/dispatch.

## Not Verified

- V3 durable metadata schema and pure terminal proof are verified; transactional batch intake/finality/accounting and multi-source/multi-batch pagination/native UI remain unimplemented. v3 signature/schema success does not prove signer qualification, committed R2 objects, payment truth or rights.
- Live source/qualification/isolated R2 signer/client, billing/provider/webhook/consumer/scheduler and Next deployment remain disabled. Keys empty; synthetic proofs/rights are fixtures only.
- Real payment sandbox/account mapping, signup/recovery, browser/responsive/WCAG/customer, qualified privacy/source rights, log redaction/retention/encryption/backups/TLS/proxy and launch remain open.
- Latest retained production quota remains 6,855 / 12,000 on 2026-10-04. No new production quota observation. Distributed runtime/Supervisor identity unverified; no work after invocation ends claimed.

## Known Risk

- Unknown effects retain reservations. No inferred cancellation/refund; downgrade/expiry cannot rewrite past accounting. Trusted future provisioning/revocation must use matching workspace/user locks and independently authenticated runtime context. Local command arguments are context selectors, not remote authentication.
- Payload erasure cannot certify WAL/replica/backup/download/downstream deletion; fingerprints and actor/job/event references are pseudonymous. Retention/backup/legal review remains before-production evidence.
- Bindings/events/deadlines block destructive migration reversal. Provider truth, key lifecycle/independence, precise batch finality and crash reconciliation require separate proof. No old revision/body may be replayed as a repair.
- CSV charge is preparation, not delivered download; no retained CSV exists. Actual signer keys/cost/rights and ESLint compatibility/browser/release evidence remain external or later development gates.

## Next Action

1. Add isolated v3 accepted-payload schema with evidence-preserving rollback, then gated atomic acceptance and exact terminal/unknown-effect accounting; preserve original reservations. Internal write-ahead entry and signed 25-row pagination follow. Ordinary v3 dispatch remains quarantined.
2. Then add stable-watermark signed 25-row page services and native selected-page CSV, preserving current rights/expiry/no-referrer/once-only preparation semantics.
3. Keep README/machine/checkpoint evidence synchronized after protected merges; checkpoints are recovery aids, not permission gates. Continue safe frontier within the next invocation's host budget. Do not replay merged mutations.

## Protected payload schema checkpoint

PR #220 merged at 2c422919a607d116b687ca45994597b581773faa; head 57c54ce52681d63603f87151785f4f818cf68be0 passed all five workflows, PostgreSQL 37826291597 (375 tests/migrations/settings) and Web 37826291595 (14 transport/build/type/HTTP). Exclusive v3 payload links, bounded positions, shared fingerprints/erasure, protected populated rollback and legacy visibility withholding verified; no v3 intake/finality/dispatch.

Next ready frontier: Implement paired candidate/acceptance proof-to-payload mapping with exact record-set and conditional domain-token checks, then gated atomic accepted-batch reconciliation and original aggregate caps. Reconcile every allocated identity and unknown effect before terminal whole-job settlement; internal write-ahead entry and signed 25-row pages follow. Keep v3 dispatch quarantined.

## Paired payload proof review

Pure paired v3 candidate/acceptance payload mapping under review: exact signed record sets, candidate digest/ref binding, independent isolated dedupe key, issuance order, current phone/territory/taxonomy/rights checks and website-dependent domain fingerprints. Immutable in-memory rows suppress sensitive repr; no durable intake, job mutation or usage settlement. Eight DB-forbidden adversarial cases; exact-head CI pending.

Next ready frontier: Implement disabled atomic v3 accepted-batch intake using paired current proofs, durable candidate identity, exact replay/reference collision checks, shared tenant fingerprints and summed original lead/source-call/outbox-call caps. Preserve the full reservation and unknown effects until every allocated identity is reconciled and exact source-final/whole-job accounting passes; then internal write-ahead entry and signed 25-row pages.

Paired-proof local verification: 383 SaaS cases / 42 explicit PostgreSQL-only skips; eight new DB-forbidden proof mapping cases passed. Ruff/format pass; pending exact-head CI remains the merge gate.

## Disabled atomic batch intake — development review

The paired-proof PR #222 merged after all five exact-head workflows passed on the branch updated with CI path scoping. The next isolated service under review writes a v3 acceptance, 1–25 payload rows and shared tenant fingerprints in one transaction after rechecking current actor/source/entitlement, the recorded exact candidate event and original lead/call caps across all batches. Exact replay returns the existing acceptance; changed bytes, source/key revocation, duplicate fingerprints, expiry and ambiguous effects fail closed. No HTTP route, ordinary dispatch, terminal settlement or usage release is enabled. `SAAS_BATCH_ACCEPTANCE_ENABLED` defaults false; external signer/R2 truth remains unverified. CI for this intake slice is pending.

## Source-final evidence — development review

PR #224 merged after 389 PostgreSQL tests, 14 Web tests and all five workflows passed. The next default-off service under review records one redacted signed source-final set only after all server-owned allocated batch identities have accepted evidence, bounded payload counts and exact trusted hashes. Unknown effects cannot create new finality; an exact existing final may replay under current rights. Empty source sets, whole-job settlement, quota release, dispatch and pagination remain unavailable. CI for source-final evidence is pending.

## Whole-job aggregate guard — development review

PR #225 merged after 394 PostgreSQL tests, 14 Web tests and all five workflows passed. A pure bounded guard under review compares the exact original source set, started operation status, nonempty accepted batch totals, committed calls and original reservation caps before proposing one job and actual leads/calls. No database write, usage settlement, no-effect proof or dispatch is enabled. CI for this guard is pending.

## Atomic positive-result settlement — development review

PR #226 merged after 402 PostgreSQL tests, 14 Web tests and all five workflows passed. A separately default-off transactional service under review re-verifies signed source-final proofs for every original source under workspace/actor/job/reservation locks, checks current entitlement/period and aggregate original caps, then settles actual positive-result usage and job/attempt/operation states together. Unknown/no-effect paths, settled-state replay, ordinary dispatch and live signer/provider trust remain disabled. CI for this slice is pending.

## Verified atomic positive-result settlement checkpoint

PR #227 merged at 930cc4d37f71303905954ca9a3e619c71ad4a66a; exact head c6cfbd2 passed all five workflows, 406 PostgreSQL tests and 14 Web tests/HTTP. Disabled internal positive-result settlement validates every original source final under current rights and locks, then updates usage/job/attempt/outbox/operation in one transaction; injected late failure rolls back. Current key registries are empty, ordinary v3 start/dispatch is quarantined. Unknown/no-effect resolution, settled-state replay, source-qualified real R2 signer/rights, internal write-ahead entry and signed 25-row pagination remain open.
