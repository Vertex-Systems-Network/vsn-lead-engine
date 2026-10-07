# SaaS system and threat-model baseline

Decision baseline: 2026-10-07 (Asia/Karachi)
Repository: Vertex-Systems-Network/vsn-lead-engine
Status: design baseline; stack-neutral and not a production implementation

This document advances M3 without selecting a framework, database, queue, cloud, payment provider, or source adapter. The existing daily production collector remains outside this SaaS boundary.

## System context

Actors:

- Visitor: reads public product/source/cost explanations.
- Workspace user: configures searches, runs or schedules jobs, reviews leads and exports within entitlement.
- Workspace administrator: manages members, workspace policy and approved source configuration.
- Platform operator: handles incidents, abuse, adapter policy and audited support actions.
- External provider: returns discovery/enrichment data under its own policy and limits.
- Scheduler/worker: executes authorized jobs with bounded concurrency and idempotency.

Trust boundaries:

1. Browser/client to versioned SaaS API.
2. API to tenant-scoped application services.
3. Application services to system-of-record and job/usage transactions.
4. Worker to source adapters and object/export storage.
5. Operator control plane to tenant data, with least privilege and tamper-evident audit.
6. AI assistant to approved read-only context and explicitly confirmed actions.

No client, worker or AI component may receive another tenant's data or raw provider credentials.

## Tenant and authorization invariants

- Every workspace-owned record carries a workspace/tenant identity.
- Authorization is checked server-side at every read, write, export, job, credential-reference and AI-context boundary.
- Membership role is not sufficient by itself; workspace identity and resource ownership must also match.
- Cross-tenant identifiers must not be enumerable or distinguishable through error responses.
- Background jobs carry an immutable workspace context and re-check entitlement/policy before dispatch and before provider calls.
- Exports, caches, logs, metrics and AI retrieval are tenant-scoped by construction.
- Operator access is explicit, time-bounded where supported, least-privileged and audited.
- Provider secrets are references to a protected secret boundary; they are never sent to clients, logs, AI memory or ordinary application records.

## Core data-flow contracts

1. User submits a search configuration with country/region, status, category, fields, source mode and schedule.
2. API validates schema, tenant membership, source policy, entitlement and estimated usage.
3. API creates an idempotent job intent; duplicate request keys return the original intent.
4. Scheduler claims the job with a lease and immutable workspace context.
5. Worker revalidates policy, entitlement, budget and cancellation before each provider operation.
6. Adapter returns normalized leads plus source/provenance/freshness metadata and usage evidence.
7. Pipeline applies phone-qualified acceptance, exact dedupe and retention/deletion policy.
8. Results are stored or exported only when the source policy allows that operation.
9. User sees queued/running/partial/completed/failed/paused/cancelled state and evidence-backed counts.
10. Audit records security-relevant decisions without raw credentials or unnecessary personal data.

## Job lifecycle and failure semantics

Allowed transitions:

`draft -> queued -> running -> {partial, completed, failed, paused, cancelled}`

- A terminal job is immutable except for append-only evidence/audit metadata.
- Lease expiry permits bounded recovery; it does not permit concurrent duplicate execution.
- Retry requires a stable idempotency key, bounded attempts, classified error and backoff.
- Pause prevents new provider work; cancellation is checked before every externally consequential operation.
- Partial results are explicit and never represented as successful full completion.
- Timezone and DST resolution are stored with the schedule/run decision; ambiguous or skipped local times use an explicit documented policy.
- Usage reservations are reconciled idempotently with actual accepted work and released on safe pre-dispatch failure.
- Circuit breakers stop repeated provider failures, budget overruns, policy violations and suspicious abuse.

## Threat model and controls

| Threat | Control |
|---|---|
| Horizontal tenant data access | Server-side workspace authorization on every path; cross-tenant tests for API, jobs, exports, caches and AI context |
| ID enumeration | Non-sequential public identifiers; uniform not-found/denied responses; rate limiting |
| Credential leakage | Secret-manager boundary; references only in app data; redacted logs; no client/AI exposure |
| Duplicate or replayed jobs | Idempotency key, durable job lease, compare-and-set transitions and bounded recovery |
| Provider abuse/cost explosion | Source allowlist, field/cost preview, per-tenant hard caps, circuit breakers and kill switch |
| Prompt injection through lead/source text | Treat source text as untrusted data; no tool authority from retrieved content; output validation and confirmation |
| Export/retention violation | Provider-specific policy attached to result lineage; export/delete guards and audit evidence |
| Operator misuse | Least privilege, explicit reason, audit trail, separation of read and mutation paths |
| Sensitive data in telemetry | Data classification, field minimization, redaction and retention policy |
| Availability failure | Queue backpressure, bounded retries, recovery runbook, partial-state visibility and rollback-safe migrations |

## Required design acceptance evidence

Before stack-specific implementation:

- reviewed API/resource contracts and versioning;
- reviewed threat model and tenant-isolation test plan;
- documented data classification, retention/deletion and backup behavior;
- documented schedule/DST/idempotency/overlap policy;
- documented source-policy adapter contract and cost/rights gate;
- documented repository boundary and migration/rollback plan;
- technology alternatives and explicit owner stack approval.

This baseline is not proof that legal, privacy, provider-rights, billing or production gates have passed.
