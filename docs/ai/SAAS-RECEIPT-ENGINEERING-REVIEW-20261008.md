# Internal receipt reconciliation review

Scope: M6 continuation after PR #169. No sender, worker, public receipt endpoint, configured verifier or provider data is enabled.

- Fixed: generic usage primitives previously could release/settle a job reservation without dispatch evidence. Job-attached usage now requires pending cancellation/expiry or the internal reconciliation service; existing non-job usage semantics remain.
- Exact-byte bounded HMAC proof is checked against trusted server settings, scoped to saved immutable operation/provider/request/policy identifiers and a stable source event reference. Unknown fields, duplicate keys, unconfigured verifier, bad signatures and implausible timestamps fail closed. This contract has no verified external provider implementation.
- Workspace locking serializes current admin-role checks, receipt insertion, operation outcomes, whole-job completion and usage finalization. Duplicate identical receipts replay; changed receipts and reused source-event references conflict. Cross-workspace insert collisions have a savepoint and return conflict, preserving reservations.
- Partial signed outcomes retain all capacity. No-effect is not inferred from expiry or a stale worker. Accepted leads and exports are always zero in this slice; phone qualification, exact dedupe, result storage and real provider metering semantics remain required before sender activation.
- Saved source call limits bind accounting to preflight policy; existing rows default to zero and cannot finalize without reviewed backfill. Receipt/cap evidence prevents destructive reverse migration; live deployments require backup/expand/roll-forward planning.
- Synthetic tests cover success/no-effect/replay, malformed/signature/identity/role/tenant rejection, budget bounds, partial outcomes, rollback and PostgreSQL duplicate/conflicting receipt races. Local SQLite is regression evidence only; final-head PostgreSQL/Next/root/ANPOS CI is required before merge.

Remaining: provider key lifecycle/rotation/status-query compatibility, verified accepted results, retention/operational reconciliation, durable scheduling, billing periods/events, browser/customer/release acceptance. No independent external security certification is claimed.
