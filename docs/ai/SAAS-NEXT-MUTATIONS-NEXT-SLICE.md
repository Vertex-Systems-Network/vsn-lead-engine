# Native Next workflows: delivered boundary and ready results frontier

PRs #180–#184 delivered native draft/cancel controls, source configuration, state-filter pagination, draft correction/conflict/missing-feedback recovery and sign-out. PR #186 now delivers native sign-in with explicit browser CSRF bootstrap and generic attempt-limit/credential notices, plus cancellation-error current-state review. Django remains authentication, tenant/role/CSRF, abuse-control and transactional mutation authority.

## Verified account and mutation controls

- Browser cookie bootstrap returns only to configured Next sign-in. The exact anonymous context forwards CSRF only and returns a masked token; authenticated paths retain validated session requirements. Credentials post directly to the protected Django login handler. Native success ignores supplied next destinations; generic notices contain no account/password data and grant no authority.
- Login account/IP budgets and trusted connection-address policy are unchanged. Native limited responses use 303 plus Retry-After, without credential checks; standalone handlers retain existing behavior. Session/CSRF rotation and logout invalidation are tested.
- Cancellation notice mode reads the authorized current snapshot, shows status/revision and links to explicit review. It issues no confirmation and performs no retry/cancellation. Stale or expired authority cannot become fresh through error rendering.
- Exact-head PostgreSQL, migrations/settings, Next build/type/lint/format/transport and real HTTP bootstrap, credential/Origin/limit, mutation/replay, source/filter and cancellation-recovery workflows pass. Browser/deployment acceptance remains separate.

## Candidate result contract boundary

The internal candidate preflight now implements the initial signed provenance/phone/scope/field-lineage/retention validation contract; exact-head verification is pending. It returns redacted comparison metadata only. No event ledger, result store, R2 dedupe authority, nonzero accounting, export or route is enabled. See `SAAS-RESULT-EVIDENCE-REVIEW-20261008.md`.

## Next bounded implementation: accepted results and source-aware export

1. Reconcile the existing API/data and UX contracts with `src/vsn_lead_engine/saas/contracts.py`, `source_policy.py`, current job/source/usage/receipt services and model ownership before adding result storage. Preserve production CLI/Google delivery/exact R2 dedupe authority; use isolated tenant-scoped SaaS storage/keys and synthetic test namespaces, never the production R2 namespace or workbook data.
2. Define trusted ingestion provenance, event identity, tenant/job/source bindings, stable replay/conflict behavior, phone qualification, US/CA scope, field lineage, retention version and permitted purpose. Browser payloads and a requested result limit cannot establish accepted leads. Current terminal receipts/accounting carry zero accepted leads: a reviewed versioned evidence/accounting change is required before accepting nonzero results; do not reinterpret existing receipts.
3. Keep new ingestion/export routes unavailable until their contracts and authority checks exist. Enforce source display/storage/export/field rights, live policy version/kill switch, current actor membership/role and atomic lead/export budgets. Reuse source-aware policy logic; unknown metadata fails closed. Synthetic rights fixtures remain tests only.
4. Add bounded tenant-scoped read views/pagination before enabling export. Export specification/idempotency, allowed fields, no formula injection, no sensitive URLs/logs, revocation/retention and audit evidence must be reviewed together. Full lead payloads are data, not operational logs or control-plane memory.
5. Verify forged/unsigned evidence, conflicting replay, foreign tenant/source/job, missing phone, unsupported territory/fields, rights changes, stale membership and concurrent caps with disposable PostgreSQL. No live adapter, source, scheduler, payment or release activation follows from contract tests.

Signed billing-event reconciliation remains independent safe work. Recovery/signup, local browser visual/keyboard/WCAG/customer assessment, shared-origin TLS/proxy/cookies and retention/encryption/cleanup acceptance remain open. Engineering implementation progress is not deployment or collection certification.
