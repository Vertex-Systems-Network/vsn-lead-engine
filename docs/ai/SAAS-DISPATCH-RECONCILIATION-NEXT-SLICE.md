# Next safe dispatch/reconciliation slice

Prepared from merged internal outbox, lease, expiry and usage code; implementation plan only. No dispatch service, adapter, worker, schedule or external runtime is certified by this document.

## Existing boundary

`core.attempts` claims and checks fixed pre-dispatch leases only. `JobAttempt` accepts leased/expired/cancelled and `core.recovery` cleans overdue queued intents. Pending cancellation can release unused reservations. These paths cannot safely infer that a network call never happened after a worker crashed.

The next unit is an internal write-ahead dispatch ledger with synthetic tests and no outbound caller. Keep source policy defaults disabled. Do not expose an enqueue/run button while provider collection remains unavailable.

## State and identity requirements

A dispatch operation must bind immutable workspace/job/source/operation identity, normalized request hash and approved policy snapshot to one persisted provider idempotency key. The key is stable across transport retry and worker lease replacement; deriving it from the current lease token or retry number would permit duplicate external work.

Persist states separating prepared, send-started, outcome-unknown, confirmed-success and confirmed-no-effect. A send-started row committed before network I/O means work may have happened even if no response was recorded. A terminal receipt needs verifiable provider operation identity and bounded actual accounting, not a client-supplied success flag. Lease and delivery identities have separate purposes: the lease fences internal ownership; the provider key deduplicates external effects.

Additive schema should use unique operation/provider-key constraints and explicit status constraints, preserve existing rows as pre-dispatch legacy records, and test forward/back/forward only against disposable databases. Rollback of a real database with send-started records requires an operational plan that retains reconciliation evidence.

## Transaction and recovery rules

1. Hold the existing workspace lock, lock job/outbox/reservation/attempt in the established order, and recheck current membership/role, lease deadline/revision, source fingerprint, entitlement/caps and intent expiry.
2. Atomically bind the operation/key, persist send-start intent and transition job/outbox out of pre-dispatch eligibility. Cancellation racing this transition must serialize: either cancellation releases genuinely pending capacity or dispatch-start wins and cancellation refuses. Predispatch cleanup must skip all started/unknown records.
3. Release database locks before any eventual network call. A transaction cannot make database plus provider I/O atomic. Recheck authorization immediately before the outbound boundary; if authorization changes, suppress new sending and retain uncertain prior work for reconciliation. Revocation cannot undo a provider action already sent.
4. Record provider response under current fencing and operation identity. A stale worker response cannot settle usage, overwrite a newer receipt or release an uncertain reservation. It may supply bounded evidence to a reconciliation path rather than being silently discarded as proof of no effect.
5. A crash/timeout after send-start is outcome-unknown. Do not automatically retry with a new key, release capacity, refund settled use or let ordinary expiry erase the evidence. Reconcile with the provider's authoritative status/idempotency behavior or retain a redacted operator-review state.
6. Confirmed no-effect may release unused capacity idempotently; confirmed success settles actual bounded use once. Ambiguous outcome preserves reservation until an authorized reconciliation determines actual effect. Current `settle_usage` is not sufficient evidence on its own.

## Adapter activation prerequisites

Synthetic ledger tests are independent zero-new-spend work. Actual adapter activation additionally requires reviewed collection/storage/display/export/cost/territory/field rights, verified provider-specific idempotency retention/replay semantics and a status-query or equivalent reconciliation path. Unsupported provider idempotency or status behavior must remain disabled or require a separately bounded operator-controlled procedure; do not promise exactly-once network execution from database leases alone.

No credentials, provider response bodies, contact records or signed download URLs belong in the ledger's audit messages. Persist only required redacted operation/error/accounting metadata and protected references; define retention and deletion behavior before customer use.

## Acceptance tests before activation

- Real PostgreSQL concurrent dispatch-start versus cancellation/expiry, duplicate dispatch-start and stale-token attempts.
- Failure injection before/after write-ahead commit; rollback leaves no partial job/outbox/reservation transition.
- Same operation always has the same immutable provider key; changed payload/policy identity conflicts.
- Lease expiry and source/role/entitlement changes suppress new sending without claiming prior work had no effect.
- Late/stale responses cannot double-settle, overwrite receipts or refund uncertain/settled usage.
- Repeated success/no-effect reconciliation is idempotent; cross-tenant receipt/operation IDs are denied.
- Recovery excludes started/unknown records from pre-dispatch cancellation/expiry and retains required evidence.
- App liveness and all user routes still report provider dispatch unavailable; no outbound code or background consumer is introduced by the internal ledger unit.

Next unit should implement and verify the ledger before enabling an adapter. Browser/accessibility/customer task validation, billing period/events, durable scheduling, actual result storage/export and external rights/privacy/deployment/launch gates remain separate work.
