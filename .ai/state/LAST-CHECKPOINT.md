# Last Checkpoint

## Snapshot

- Vertex-Systems-Network/vsn-lead-engine; 2026-10-08 UTC / PKT.
- Protected feature main re-read: `c5c26d15f5cbb8e9865014c125f13489895755a4` / PR #186. Recorded feature base precedes this documentation merge; reconcile live main/issues/PRs before mutation replay.
- Owner selected Next.js + TypeScript; Django/DRF/PostgreSQL retain session, tenant, role, CSRF, abuse-control and mutation authority. Production CLI/R2/Google behavior is isolated.

## Verified

- PR #186 merged at c5c26d15f5cbb8e9865014c125f13489895755a4; head be357389f869b5b2cc667eff5280718d0e687789 passed required checks/Actions CodeQL, PostgreSQL 37766322082 (162 tests/migration/settings) and Next/HTTP 37766321955 (nine transport tests, native login bootstrap/failure/limit/rotation and cancellation-error review, plus earlier workflows).
- Native sign-in uses explicit Django browser cookie bootstrap with fixed Next return and one exact stateless masked-CSRF context. Only CSRF is forwarded for that anonymous context; all authenticated contexts retain validated session requirements. Password/username do not enter Next POST handlers, error URLs or feedback storage.
- Native login POST retains existing account/IP budgets and trusted connection-address policy. CSRF/Origin failures occur before budgets/auth. Generic failed/limited notices are presentation only; limit response is 303 plus Retry-After 900 without credential checks. Standalone login retains 200/429. Native success ignores supplied next and uses configured return with Django session/CSRF rotation.
- Cancellation errors return fixed invalid/changed/unavailable notices; native notice reads show the authorized current snapshot without confirmation issuance, auto-retry or cancellation. Explicit fresh review is required. Stale/started/terminal jobs remain protected; role/CSRF/foreign denial cannot become a recovery redirect.
- PR #184 remains verified: five-minute bounded draft feedback/correction/conflict/missing-context recovery and native sign-out. PRs #180–#182: native draft/cancel, bounded readonly source view and state-filter pagination. Earlier CI evidence is retained in CURRENT-STATE/review documents.
- PRs #175–#178: internal terminal receipts/usage bypass guards, manual periods/rollover, bounded disabled daily draft occurrences/DST and fixed session navigation. Unknown outcomes retain capacity until valid whole-job proof; unresolved reservations block rollover and late proofs account to original periods. Accepted leads/exports remain zero.
- Local SaaS 162 cases: 146 passed/16 PostgreSQL-only skipped. Final PostgreSQL CI all 162 passed; migrations/settings, Next lint/format/nine transport tests/build/type and real HTTP complete workflows pass. Root 376 passed, 1 skipped, 28 subtests; ANPOS/Ruff/drift pass.
- M5 85%, M6 70%, M7 70%, overall ~45% are engineering indicators. Work units unchanged: 9 complete, 5 in progress, 1 blocked, 2 deferred, 4 not started of 21.

## Not Verified

- Accepted-result/export store, billing-event reconciliation, recovery/signup and browser/customer acceptance remain open. No provider consumer, configured receipt verifier, payment activation, scheduler timer/scanner or automatic enqueue activation.
- No production Next deployment, provider exactly-once or visual/responsive/WCAG certification. No local browser binary available; HTTP checks do not replace browser assessment.
- Persistent distributed-agent identity remains unverified. No work after turn end claimed. Latest retained production evidence: 6,855/12,000 on 2026-10-04; no new quota observation.

## Known Risk

- Native separate-port HTTP flows require deployment shared-origin TLS/proxy/cookie/CSRF acceptance; unrelated domains do not share browser session/CSRF cookies automatically. Native login's generic PRG notice is not an authentication or quota grant.
- Existing draft feedback read expiry is not physical erasure: session retention/clearsessions cleanup applies. Concurrent session last-write can evict/lose feedback; missing context fails closed. Login/cancellation notices introduce no additional error store.
- Unknown external outcomes retain capacity until valid proof; provider rights/evidence/replay contracts remain necessary. Evidence migrations refuse destructive rollback.
- ESLint 9 is unsupported while plugin peers exclude 10; compatible maintained tooling remains a production gate. Manual windows and disabled schedule configs are not paid activation or a customer execution scheduler.

## Candidate in progress

Candidate result preflight implemented: separate empty-by-default signed evidence registry, current tenant/role/entitlement/source fingerprint checks, bounded US/CA phone/field lineage/retention validation and redacted immutable summary. No ingestion, dedupe, replay ledger, result/accounting writes or exports. Local/CI evidence pending on this branch. See docs/ai/SAAS-RESULT-EVIDENCE-REVIEW-20261008.md.

## Next Action

1. Continue bounded accepted-result and source-aware export contracts under trusted source evidence, phone qualification and exact R2 dedupe authority; billing-event reconciliation is independent. Keep provider/payment/scheduler consumers disabled.
2. Define accepted-result ingestion provenance/idempotency, rights/phone/export-field checks and denied-by-default routes before any live adapter. Do not duplicate or replace production R2 authority or count synthetic fixtures as accepted production leads.
3. Continue ready work within invocation budget. Checkpoints are recovery aids, not permission gates; no execution after turn end is claimed.
