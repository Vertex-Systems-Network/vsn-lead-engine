# Explicit source-deadline payload erasure and dedupe tombstones

`expire_result_payloads` is an operator-invoked development command taking explicit workspace and current active actor UUIDs plus a limit from 1 to 100. The transactional service rechecks current owner/admin membership under the existing workspace lock. Members/viewers/foreign/revoked actors cannot erase data. No HTTP cleanup endpoint or automated scheduler is added. Expiry uses server time and stored source-derived delete_at; callers cannot provide a cutoff or delete unexpired rows. Inactive entitlements or disabled source policies do not prevent necessary expiry cleanup.

Select due unerased records by indexed workspace/deadline/UUID under row locks, at most the requested bound. Atomically clear fields, field lineage, source record reference, category, purpose and retention label; stamp erasure time and actor. Multiple null source references avoid same-batch uniqueness collisions. Keep minimal row identity, tenant/job/acceptance links, country, observation/deadline timestamps and accepted fingerprint tokens as tombstones. Historical accepted counts, receipts and usage are unchanged; erasure is not a refund or permission to collect a duplicate again. Existing acceptance replay does not rewrite erased rows. Reads explicitly withhold erased rows; export/replay cannot regenerate removed data.

Database constraints require complete cleared tombstones or intact live identity; simple attempts to attach payloads to an erased state fail. Trusted database administration can still alter state and is outside these application controls. Workspace locking serializes cleanup with acceptance, reads, export and membership changes. Repeated cleanup is a no-op with original erasure timestamps preserved; `more_due` tells an operator whether another explicit bounded invocation is needed. Command output contains counts only, never IDs/values/references/tokens.

Migration 0015 is additive and reverses while no erasure exists. After any payload erasure, reversal refuses because source references/data cannot be reconstructed; use a reviewed roll-forward preservation plan. Runtime erasure is intentionally irreversible for those active payload fields. This change is implemented and exercised only against disposable synthetic databases; no production erasure is performed.

Tests cover due/future/idempotent/bounded cleanup, multiple references, role/revocation/tenant isolation, disabled policies/inactive entitlements, rollback, retained duplicate rejection, database tombstone consistency, command output and rollback guard. PostgreSQL tests cover duplicate expiry and simultaneous due-result export/cleanup. Actual Django/Next HTTP verification erases a synthetic expired result, observes empty payload, preserved fingerprints and withheld Next display. Exact-head CI is the merge gate.

This removes active row payloads only. PostgreSQL historical pages/WAL/replicas, backups, caches outside this isolated application, audit-key retention, permanent pseudonymous fingerprints, client-downloaded CSVs and downstream copies are not certified erased. Qualified retention/privacy/backup review remains required before production. No live source/signer/R2 registry, scheduler, paid service or production deployment is activated. Next export preview/confirmation is the next user-facing slice.

## Verified merge evidence

PR #195 merged at 92657c5c8bbdb27115e95f5642f841e8a1c975c3; head dc84dce770bf14580e9d2691880510fc6615ba14 passed required checks/Actions CodeQL, PostgreSQL 37780165591 (235 tests/expiry races/migrations/settings) and Next/HTTP 37780165669 (10 transport tests/build/type and payload erasure/tombstone flow).

## Subsequent verified frontier

PRs #194–#196 deliver guarded CSV preparation, bounded active payload erasure/tombstones and native Next preview/confirmation. Historical remaining-work statements in this review are superseded for those slices. Result filters/selection, wider pagination, real signer/source and browser/customer/backup/production acceptance remain open.
