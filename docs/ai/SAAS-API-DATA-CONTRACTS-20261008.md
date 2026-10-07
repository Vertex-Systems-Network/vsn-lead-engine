# SaaS API and data contracts

Design date: 2026-10-08 (Asia/Karachi)
Status: proposed M3 contract baseline; no SaaS runtime or external provider is enabled
Authority: merged MVP boundary in PR #140; system/threat-model baseline in PR #141; current repository technical-autonomy delegation

This document makes the M3 contracts testable while preserving the production pipeline. It is a design contract, not evidence of customer demand, source rights, legal clearance or production readiness.

## 1. Runtime and repository boundary

- Extend the current Python repository additively under a distinct `saas` application boundary. Keep the existing CLI, fixed production scheduler, Google Sheets output, R2 dedupe authority and P01-P70 workflows unchanged.
- SaaS routes, migrations, worker processes and dependencies must be opt-in and must not run from the existing production collection workflow.
- Local development and CI may use disposable test configuration. Production credentials, Google workbook data and the production R2 namespace must not be used by SaaS tests.
- Revisit a separate repository only if release cadence, dependency isolation, access control or deployment evidence shows the current repository boundary is unsafe. Record that change before moving code.
- No production SaaS deployment is part of M3 or the stack decision.

## 2. Resource and API contract

Use a versioned `/api/v1` namespace. Every workspace-owned route is scoped by a server-resolved workspace membership; a path or request field supplied by a client never proves authorization.

| Resource | Initial operations | Required invariant |
|---|---|---|
| Workspace and members | Read workspace; list members; invite/change role by authorized owner/admin | Membership is checked for each request; last owner cannot be removed or demoted |
| Search configurations | Create, read, update, archive | Countries, categories, status and fields are normalized and bounded before save |
| Source catalog | Read currently enabled source capabilities | Disabled or unreviewed source is not selectable |
| Jobs and schedules | Preview; submit manual job; list/detail; pause, resume, cancel, retry; create/update/pause schedule | Every mutation is permission, entitlement, source-policy and idempotency checked |
| Leads | List, filter, sort, detail | Tenant and source lineage are enforced before query, not after retrieval |
| Exports | Request, poll status, download | Export permission, source rights, field scope and limits are checked before generation |
| Usage | Read workspace usage and limits | Usage is server-derived and cannot be set by the client |

Request contract:

- JSON requests use explicit schemas and reject unknown or invalid enum values.
- State-changing job and export requests include an idempotency key scoped to workspace, operation and request body hash. A repeated key with the same body returns the original result; a different body returns a conflict.
- The API derives actor and workspace membership from the authenticated session/token. It records request ID, actor ID, workspace ID and authorization result in privacy-safe audit metadata.
- Use stable error classes: validation, unauthenticated, forbidden/not-found, conflict, rate-limited and unavailable. Cross-tenant resources return the same externally observable response as an absent resource.
- Paginate with opaque cursors; cap page size, filters, date range and export size. Set explicit timeouts and rate limits.
- Never put secrets, provider credentials, full lead payloads or signed export URLs in URLs or routine logs.

## 3. Tenant and role contract

- Workspace is the tenant boundary. Every tenant-owned table includes a non-null `workspace_id`; composite foreign keys/constraints prevent linking a row to another tenant.
- The service layer receives an authorized workspace context, not a bare client-selected identifier. Query helpers require that context and apply tenant scope before pagination, aggregation, cache lookup or export.
- Roles: `owner`, `admin`, `member`, `viewer`. Owner/admin manage workspace and membership. Member can create/manage jobs and read/export authorized leads. Viewer can read only. All roles are scoped to a verified membership; platform support access is separate, time-bounded where possible and audited.
- Test at least two workspaces with overlapping IDs and verify list/detail/update/delete/job/usage/export/cache paths cannot disclose across tenants. Include background-worker and stale-membership cases.

## 4. Data model and lineage

| Entity | Ownership and key constraints | Sensitive fields / lineage |
|---|---|---|
| User, Session | User identity is not duplicated into lead records; sessions are revocable and expire | Authenticator references stay outside logs |
| Workspace, Membership | Unique membership per (workspace, user); at least one owner | Role changes are audited |
| Search, Schedule | Workspace-owned; IANA timezone and normalized criteria | Schedule revision and next-run calculation are recorded |
| Job, JobAttempt | Workspace-owned; immutable request snapshot and stable idempotency key | Attempts append execution evidence; error details are redacted |
| Lead, LeadFieldProvenance | Workspace-owned; dedupe key is tenant- and source-policy-aware | Each field records source, source record ID, observed time, freshness, confidence and attribution/license metadata |
| SourcePolicy | Versioned capability and rights metadata; disabled until reviewed | Review evidence, permitted territory/fields, storage/export/retention and rate/cost limits |
| UsageReservation, UsageEvent | Workspace-owned; unique reservation/event keys and atomic accounting | No client-supplied balances |
| ExportJob, AuditEvent | Workspace-owned except separately governed operator audit | Export field manifest and actor; no raw credentials or unnecessary lead values |

A public business contact field can still contain personal data. Minimize collection and access; do not treat “publicly visible” as a general retention, export or legal permission. Qualified privacy/compliance review remains external.

## 5. Source policy and lead acceptance

A source adapter is unavailable until its versioned policy has evidence for intended purpose, territory, fields, attribution, display, storage, onward export, retention/deletion, rate limits, failure behavior and cost. API key possession is not rights evidence.

The policy contract must expose supported countries/categories/fields, storage and export flags, maximum rates, estimated cost, attribution requirements, freshness behavior and a kill switch. Unknown rights or policy metadata fail closed. BYOK does not override source terms.

Preserve phone-qualified accepted-lead requirements and exact deduplication semantics from the existing engine. SaaS dedupe keys and indexes are tenant-scoped; do not expose the production R2 ledger as the SaaS database. If multiple sources contribute fields, retain field-level lineage and reject combinations that violate any source policy.

## 6. Job, retry and schedule contract

Job states follow the current domain contract: `draft -> queued -> running -> partial/completed/failed/paused/cancelled`.

- State changes use compare-and-set against the stored revision. Only `completed` and `cancelled` are permanently closed. A `partial` job may resume and a `failed` job may be explicitly retried; each execution is a new append-only attempt with a bounded retry count and the same parent job/idempotency context.
- A worker claims a lease for one attempt. Lease expiry permits recovery only after the previous lease is invalidated; duplicate workers cannot dispatch the same attempt.
- Recheck membership, source policy, entitlement, budget and cancellation immediately before external work. Reserve usage atomically before enqueue; settle actual use idempotently and release reservations on pre-dispatch failure.
- Partial output is labeled partial. Never report a requested result limit as an achieved count.
- Persist the schedule's IANA zone, requested local date/time, resolved UTC instant, UTC offset, DST resolution and schedule revision. For a nonexistent spring-forward time, execute at the next valid local instant that day. For an ambiguous fall-back time, execute once at the earlier UTC instant. Derive a unique occurrence key from schedule ID, schedule revision and requested local date/time.
- Pause blocks new attempts. Cancellation is checked before every externally consequential action. A cancelled job is not resumed; a user creates a new job.
- Retry only classified transient failures with bounded exponential backoff and jitter. Policy, entitlement, authorization and validation errors fail closed without automatic retry.

## 7. Usage, billing and cost safety

No payment gateway, price, subscription billing or charge is enabled by this design.

- Entitlement is an internal capability contract; an inactive or unknown entitlement blocks dispatch.
- Enforce job, accepted-lead, provider-call, export and AI budgets with atomic reservations so concurrent requests cannot exceed limits.
- The preview shows requested scope, eligible sources, unavailable fields, estimated usage/cost and hard cap before dispatch. Unknown cost means no paid work.
- Billing-provider state can be integrated later through a signed, idempotent adapter; it must not be client-authoritative.
- New recurring paid infrastructure, API, AI or other spend needs separate authorization. Free access does not imply zero compute/storage/egress cost.

## 8. Retention, deletion, export and backup

- Attach a retention policy version to each source-derived record and export. Enforce source-specific deletion/retention terms at field level where needed.
- Provide workspace deletion and per-record deletion as auditable jobs. Delete active copies and caches; propagate tombstones to derived exports and downstream stores where permitted. Backup expiry must be documented, bounded and tested before production.
- Retention duration, legal basis, subject-right handling and backup timelines remain unset until qualified privacy/compliance review and source terms establish them; do not invent a universal duration.
- Exports contain only authorized fields and sources, are generated asynchronously with size/time limits, and use short-lived download access. Downloads are audited without storing the URL token.
- No email outreach or marketing send action is in the MVP contract.

## 9. Migration and recovery

- Keep SaaS migrations in a dedicated namespace and never apply them from production lead-collection jobs.
- Use expand -> migrate/backfill -> verify -> contract for any live schema change. Backfills are idempotent, checkpointed and tenant-safe.
- Before a schema or data migration, verify a restorable backup or reproducible rollback path. Destructive cleanup waits until post-migration verification and recovery window pass.
- SaaS failure must not block or mutate the established daily collector. Disable the SaaS entry point with a feature/config gate and preserve existing production workflows.

## 10. UX and accessibility acceptance

1. Visitor can distinguish live capability from planned or unvalidated claims.
2. User can see source eligibility, supported fields, estimated limits/cost and uncertainty before saving or running a job.
3. Schedule setup previews the next local and UTC run with timezone and DST interpretation.
4. Job history distinguishes queued, running, partial, completed, failed, paused and cancelled; error messages identify safe recovery actions without exposing secrets.
5. Lead tables expose source, field provenance and freshness; filters, pagination and export remain tenant-scoped.
6. Forms and tables support keyboard use, visible focus, labels, error summaries, zoom/reflow, contrast and reduced motion. Target WCAG 2.2 AA.

## 11. M3 verification gates

M3 is ready to close when the API/resource model, tenant threat tests, source policy, job/DST semantics, data classification and retention design, migration/recovery boundary and primary UX flows are reviewed against this contract. Technology alternatives and cost/operability trade-offs then move to the next architecture decision. Runtime auth, persistence, provider activation, billing and production deployment remain separate implementation/release gates.
