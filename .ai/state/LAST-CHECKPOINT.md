# Last Checkpoint

## Snapshot

- Repository Vertex-Systems-Network/vsn-lead-engine; 2026-10-08 PKT / 2026-10-07 UTC.
- Protected main re-read: `4d2c6ab86b01c6335de81d2d437ed8d2fe3d7b01` / PR #181. Current branch `codex/next-job-state-filter`; inspect live main/issues/PRs before future mutation replay.
- Owner selected Next.js + TypeScript. Django/DRF/PostgreSQL remain session, tenant, role and mutation authority; isolated SaaS work preserves production CLI/R2/Google behavior.

## Current candidate

- Native saved-job state filter/cursor continuity and private bounded validated query implemented; local 129 pass/16 PostgreSQL skips (145 cases), eight transport tests, Next build/type/lint/format and HTTP filtered/empty/Next/First page flow pass; final-head CI pending. No mutation/provider or full browser/customer acceptance.

## Verified

- PR #181 merged at 4d2c6ab86b01c6335de81d2d437ed8d2fe3d7b01; head 66152035d4f4da7f75d8c656fe3eae0224590076 passed required checks/Actions CodeQL, PostgreSQL 37703955016 (141 tests/migration/settings), and Next/HTTP 37703954934 (bounded native source/XSS/viewer/tenant and earlier form/auth flows).
- PR #180 merged at 6c6460c095778b27235272bd6f5ea608900614e1; head 3c24b14fd0e263cc4fa24fd15ed2279752738961 passed all required checks/Actions CodeQL, PostgreSQL 37703540378 (138 tests/migration/settings) and Next/HTTP 37703540308 (native draft/replay/role/tenant/queued cancellation/CSRF/auth flows).
- PR #178 merged at 90f90a6952932d7ef8a43d5d6bcaa6decb964139; head 71af41df128f1a2f54d19a6132d859ac0b492187 passed validate 37702109328, repository-integrity 37702109032, Actions CodeQL 37702109054, PostgreSQL 37702109091 (130 tests/migration/security gates), and Next/HTTP 37702108894 (real CSRF login-return/logout and old-session denial).
- PR #177 merged at b73d0de7ec1e5659c1573d4fc814973be765adbd; head 177b826286449ef6983af40cd1631d5658bec568 passed required checks/Actions CodeQL, PostgreSQL 37701609841 (124 tests including duplicate/revocation schedule races and migration/security gates), and Next/HTTP 37701609870.
- PR #176 merged at 52653cfbd7d3ccffee0cf1685afcc99be9877183; head d3707b30d5284fb94cd39e80c9b4474a6aa749be passed required checks/Actions CodeQL, PostgreSQL 37701109983 (114 tests including period races/migration/security gates), and Next/HTTP 37701109984.
- PR #175 receipts merged at d29cffd520c5eca4152f76633035aab540f5f18b; head 1a1e321ecdf7e93d6597653c20e1d7070eb5ffca passed PostgreSQL 37700238737 (104 tests), Web 37700238777 and all required checks. Exact proof replay/conflict, source event identity, bounded call budgets and concurrent terminal reconciliation are covered.
- Internal dispatch write-ahead/unknown state keeps uncertain reservations; terminal proof reconciles whole-job usage only after all operations resolve. Accepted leads/exports remain zero. Generic usage APIs cannot release/settle attached job reservations.
- Explicit manual period windows retain legacy counters and late receipt accounting; unresolved reservations block rollover. Closed totals archive once, expired periods stop new work, old receipt/key replay cannot reset or charge a new window. Next/Django show explicit dates without automatic reset claims.
- Next workspace/jobs/detail/usage uses bounded server-only session GET transport, fixed origin/path checks and no shared cache/redirects. Real disposable Django/Next HTTP rendering checks pass; Django draft/cancel forms remain in use.
- Local SaaS suite: 130 cases, 114 passed/16 PostgreSQL-only skipped; final PostgreSQL CI runs all 130 without skips. Next password/CSRF cookie/return/confirmation/logout and old-session denial verified by HTTP CI. Root 376 passed, 1 skipped, 28 subtests, ANPOS and local lint/drift/settings pass. M5 85%, M6 70%, M7 65% candidate, overall ~45% are engineering indicators only. Work-unit counts: 9 complete, 5 in progress, 1 blocked, 2 deferred, 4 not started of 21.

## Not Verified

- No schedule timer/scanner, public activation endpoint, automatic enqueue or live source consumer is enabled. Synthetic fixtures do not prove provider compatibility or rights.
- No configured terminal proof verifier, signed billing-event/payment activation, accepted-lead/results/export store or production Next deployment. Provider exactly-once is not certified.
- Browser executable unavailable; HTTP checks do not certify visual/responsive/WCAG/customer acceptance. Rights/privacy/customer/deployment/launch review remains open.
- No persistent distributed-agent runtime identity or work after turn end claimed. Production quota retained at 6,855/12,000 on 2026-10-04; no new production observation.

## Known Risk

- Unknown external outcomes retain capacity until valid terminal evidence arrives; provider adapters need reviewed proof contracts and replay semantics. Evidence/history migrations refuse destructive rollback.
- Fixed session return/logout is tested over localhost HTTP, with opt-in trusted origin. Native Next account/error flows and production shared-origin TLS/cookie/CSRF acceptance remain open; native draft/cancel/screens are verified.
- ESLint 9 is upstream unsupported while current plugin peers exclude 10; compatible maintained tooling remains a production gate.
- Manual windows do not automatically reset or activate paid plans. Schedules are disabled configurations and draft decisions, not a working customer execution scheduler; timezone data and activation/overlap/retention need deployment review.

## Next Action

1. Verify/merge saved-job filter candidate, then continue native validation/error and account flows under Django authority.
2. Continue account forms, signed billing-event and accepted-lead/results contracts where independent, without activating payments/providers. Native browser/proxy acceptance remains explicit.
3. Continue ready work within invocation budget; checkpoints are recovery aids, not permission gates. No execution after turn end is claimed.
