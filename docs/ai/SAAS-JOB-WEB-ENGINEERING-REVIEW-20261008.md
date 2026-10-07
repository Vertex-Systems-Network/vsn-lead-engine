# Job visibility and draft form engineering review

Date: 2026-10-08 PKT. Scope: additive isolated `apps/saas` session UI. This review records the implementation assessment; it is not an independent reviewer, source-rights, deployed security or WCAG certification.

## Delivered behavior

- Job history/detail use the existing job entity as a saved normalized search. No second search entity or divergent search validation contract is introduced.
- Read snapshots filter by workspace, lock the workspace and re-resolve membership. Detail looks up both workspace and job. All roles may read; writes remain owner/admin/member only.
- Newest-first continuation uses immutable `created_at` plus UUID ordering, selects 26 rows and displays 25. Signed continuation binds workspace and expires in one day. New inserts appear before an existing cursor; a cursor does not freeze the database.
- The form is session-authenticated and CSRF-protected. A signed one-day actor/workspace-bound random idempotency key keeps repeat submissions on one draft. Request validation reuses `SearchSerializer`; `create_draft` retains transactional membership/role rechecks and replay/payload-conflict enforcement.
- A successful POST returns 303 to a tenant-safe job detail. Invalid inputs preserve prior values and token; mismatched replay returns 409. Form errors are escaped, linked to focusable field groups and summarized in an alert. Viewer controls are hidden and server rejection remains authoritative.
- Phone qualification, US/Canada scope and existing result/category/source bounds remain enforced. Source selections and categories are preferences, never activated capabilities or rights evidence. Draft saves neither reserve usage nor queue an outbox.

## Review findings and trade-offs

Existing API pagination is unchanged for compatibility; the session history has a separate chronological signed continuation. Queries are bounded, detail is one tenant-scoped object, and no count query or provider call runs. Existing workspace/creation index supports the chronological filter; migration/extra index is not justified by unmeasured production volume.

The UI is deliberately a development surface reflecting existing persisted facts: scope/status/count/revision/UTC times. It avoids invented start/finish/attempt/failure metadata, retry/cancel/download controls and billing checkout. It renders no request hash, fencing token, provider credentials or raw error object. Server escaping and Django form rendering protect client-supplied categories/source text; no source text is used as an external URL or marked safe.

History tables use captions/header scopes and keyboard-focusable overflow regions. Draft form labels, fieldset semantics and field errors use Django field groups, and controls have visible focus rules. Browser, responsive layout and assistive-technology behavior still need actual execution. Browser fixtures/harness were prepared locally, but Chromium was absent and the attempted browser download returned invalid/truncated archives. This blocker does not justify claiming visual/WCAG acceptance or disabling tests.

The first history CI exposed an omitted `Known Risk` checkpoint heading after documentation rewrite. The checkpoint was repaired; the existing test/validator contract was preserved. Root suite must be rerun after the final documentation/state change, not only before it.

## Validation and remaining gates

- History local SaaS: 58 passed, 8 explicit PostgreSQL-only skips. Draft-form local SaaS: 65 passed, 8 explicit PostgreSQL-only skips.
- Root suite: 376 passed, 1 skipped, 28 subtests passed after checkpoint repair. Ruff lint/format and migration drift checks pass locally.
- Route tests cover foreign/revoked/viewer scope, mutation denial, escaped text, pagination ties/inserts, invalid/expired/cross-workspace cursors, signed form actor/workspace/expiry/tamper checks, field bounds, normalized phone-only drafts, duplicate replay, changed-payload conflict, CSRF and transactional access revocation.
- Real PostgreSQL regression/concurrency/migration/security-setting gates remain required on each published final head. No production collector, R2/Google delivery, billing, provider consumer, cleanup schedule or public deployment is activated.
- Next independent frontier: current-policy source availability preview, guarded draft controls where contracts permit, explicit dispatch-start/provider-idempotency/uncertain-outcome reconciliation and full browser/customer task validation. Provider rights, paid activation, qualified privacy review and launch acceptance remain external gates.


## Pending cancellation follow-up

A separate review page requires explicit POST confirmation signed for actor/workspace/job/revision and expiring after ten minutes, plus normal CSRF. Role-aware controls are backed by transactional membership/state/revision authorization. Existing cancellation keeps request history, refunds no settled usage, releases pre-dispatch reservations and invalidates active leases. Draft and queued states only are supported; running/partial/completed/failed/paused states cannot be cancelled. A stale confirmation conflicts; a duplicate already-applied confirmation safely replays. Form errors expose a review path instead of an immediately reusable failed confirmation button. Synthetic tests cover queued release/lease invalidation, draft replay, stale/running/finished state preservation, expired/tampered/foreign actor/job tokens, tenant/viewer/revoked access, role downgrade during transactional cancellation, CSRF and method rejection. Local SaaS is 72 pass with 8 PostgreSQL-only skips; no new schema or external execution is added. Real PostgreSQL checks remain merge gates.
