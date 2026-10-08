# Last Checkpoint

## Snapshot

- Vertex-Systems-Network/vsn-lead-engine; 2026-10-08 UTC / PKT.
- Protected feature main re-read: `bec879cb7b7ed925e64a623d2ce197c7c590eafa` / PR #184. This records the verified feature base before its own documentation merge; reconcile live main/issues/PRs before mutation replay.
- Owner selected Next.js + TypeScript; Django/DRF/PostgreSQL retain session, tenant, role, CSRF and mutation authority. Production CLI/R2/Google behavior is isolated.

## Current candidate

- Native Next sign-in with explicit CSRF bootstrap/generic failures/unchanged attempt caps and cancellation-error snapshot/review implemented. Local 146 pass/16 PostgreSQL skips (162 cases), nine transport tests, Next build/type/lint/format and HTTP flows pass; exact-head CI pending. No provider/payment activation or browser/deployment certification.

## Verified

- PR #184 merged at bec879cb7b7ed925e64a623d2ce197c7c590eafa; head 034cd99a40dbd3c2254e1a3a832e01f05f56501c passed required checks/Actions CodeQL, PostgreSQL 37755784470 (154 tests/migration/settings) and Next/HTTP 37755784437 (eight transport tests, escaped feedback/correction/replay/conflict/missing-context recovery and native sign-out).
- Native draft validation uses a five-minute actor/workspace/session-bound UUID handoff, maximum three entries, bounded allowlisted values/errors and the original signed draft nonce. Reads recheck role, expiry and nonce, are private/no-store and do not consume/extend the handoff. Correction and accepted replay create one draft; changed accepted content renders conflict. Missing context links to a new form/workspace.
- Invalid authority, oversized input, repeated scalars and unbounded errors retain Django validation fallback. Unknown fields/password/raw CSRF are omitted from handoff storage. Supported checkbox values/scalar text restore escaped; unknown choices require correction.
- Native Next sign-out confirms direct Django POST logout using a narrowly scoped authenticated masked-CSRF context. GET/logout missing CSRF/untrusted Origin denied; successful logout invalidates the session and feedback. No Next mutation proxy.
- PRs #180–#182 remain verified: native draft/cancel contexts/controls, bounded source configuration and saved-job state filtering/pagination. Earlier exact-head CI evidence is retained in CURRENT-STATE and review documents.
- PRs #175–#178 delivered internal terminal receipts/usage bypass guards, manual periods/rollover, bounded disabled daily draft occurrences/DST and fixed login/logout return. Unknown outcomes retain capacity until valid whole-job proof; no accepted results are minted. Unresolved reservations block rollover, late receipts account to original periods.
- Local SaaS 154 cases: 138 passed/16 PostgreSQL-only skipped. Final PostgreSQL CI all 154 passed; migrations/settings, Next lint/format/eight transport tests/build/type and real HTTP auth/CSRF/form/source/filter/recovery/sign-out flows pass. Root 376 passed, 1 skipped, 28 subtests; ANPOS/Ruff/drift pass.
- M5 85%, M6 70%, M7 65%, overall ~45% are engineering indicators. Work-unit counts unchanged: 9 complete, 5 in progress, 1 blocked, 2 deferred, 4 not started of 21.

## Not Verified

- Native login/cancellation-error screens and results/export store remain open. No provider consumer, configured receipt verifier, signed payment activation, scheduler timer/scanner or public automatic enqueue activation.
- No production Next deployment, provider exactly-once or visual/responsive/WCAG/customer certification. Browser runtime remains unavailable; HTTP checks do not replace browser assessment.
- Persistent distributed-agent identity remains unverified. No work after turn end is claimed. Latest retained production evidence remains 6,855/12,000 on 2026-10-04; no new quota observation.

## Known Risk

- Feedback read expiry is not physical erasure: existing server-side session retention/clearsessions cleanup applies. Production encryption/retention/cleanup review remains open. Concurrent session last-write may evict/lose feedback; missing context fails closed without affecting transactional idempotency.
- Unknown external outcomes retain capacity until valid proof; provider rights/evidence/replay contracts remain necessary. Evidence migrations refuse destructive rollback.
- Opt-in fixed trusted frontend origin is verified locally; production shared-origin TLS/proxy/cookie/CSRF acceptance remains open. No wildcard/request-selected trust.
- ESLint 9 is unsupported while plugin peers exclude 10; compatible maintained tooling remains a production gate.
- Manual accounting windows do not automatically reset or activate paid plans; disabled draft occurrence configs do not constitute a customer scheduler.

## Next Action

1. Continue native login and cancellation-error workflows under Django session/CSRF and abuse-control authority; signed billing events and phone-qualified results/export remain independent without provider/payment/scheduler activation.
2. Native anonymous login needs explicit CSRF bootstrap/cookie propagation, existing account/IP budgets and generic errors; never preserve passwords. Cancellation errors must show current state and require reviewed fresh confirmation, without automatic cancellation or stale-authority refresh.
3. Continue ready work within invocation budget. Checkpoints are recovery aids, not permission gates; no execution after turn end is claimed.
