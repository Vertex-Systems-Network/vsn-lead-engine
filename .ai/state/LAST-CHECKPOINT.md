# Last Checkpoint

## Snapshot

- Vertex-Systems-Network/vsn-lead-engine; 2026-10-10.
- Exact main SHA and latest merged PR are read from git (`git log -1 origin/main`), not copied here. At this checkpoint main was `7bfbe0525aa22f01fc6242747c1518dade22c691` (PR #240).
- Product 0.66.1 / ANPOS 1.4.0. Active agent role: `single_session_developer` (no verified distributed Supervisor).
- Full per-PR evidence for PR #207 through #238 (billing ledger and the v3 batch-evidence series) is retained in git history of this file and in `docs/ai/` review documents.

## Verified

- PR #240 merged: daily category-sheet appends skip unique keys already on the tab (retry cannot duplicate rows), Overpass QL city escaping fixed, `.env.example` corrected. Root regression 384 passed / 1 skipped locally; all required checks passed on the PR.
- SaaS foundation through PR #238: 436 PostgreSQL tests and 14 Web tests/HTTP passing. Tenant identity, drafts, cancellation, entitlements, usage reservations, accepted results, guarded CSV export and receipt history are implemented. The v3 batch-evidence modules (`apps/saas/core/batch_*.py`) are default-off and unreachable.
- Counts unchanged: 9 complete, 5 in progress, 1 blocked, 2 deferred, 4 not started of 21.

## Not Verified

- Jobs are now fulfilled by `manage.py run_jobs`, but only against the synthetic `local-fixture` source with the DEBUG-only local signer; there is no customer submit button, sign-up or real source yet.
- Latest retained production quota is 6,855 / 12,000 on 2026-10-04; no newer observation and no root cause recorded for the shortfall.
- Live payments, signup/recovery, browser/WCAG, privacy/source rights, deployment and launch remain open external or later gates.
- Distributed runtime/Supervisor identity unverified; no work after an invocation ends is claimed.

## Known Risk

- Roadmap drift: 19 of the 40 merges before PR #240 were default-off or no-effect evidence slices and 17 were state/docs reconciliation. CI now freezes `batch_*` modules and rejects chained non-code PRs (`scripts/verify_product_progress.py`).
- Independent review: the main ruleset requires 0 approvals; the only gate is CI. An AI reviewer workflow needs the owner to add an `ANTHROPIC_API_KEY` repository secret.
- Unknown effects retain reservations; no inferred cancellation/refund. Payload erasure cannot certify backup/downstream deletion.

## Next Action

Owner direction (2026-10-10): finish the SaaS platform first; do not work on the production collector quota.

1. Customer submit: a job-page button and Django form view that calls `enqueue_job` with the expected revision.
2. Sign-up page, automatic workspace and a starter entitlement (dev/staging), so a new customer can run a job without billing.
3. Job progress UI (queued → running → completed/failed) and a 25-lead-per-job explanation.
4. Real source adapter (collector Overture) and a non-DEBUG signer process to replace the dev-only local signer.
5. Fold README/state corrections into code PRs. Do not replay merged mutations.
