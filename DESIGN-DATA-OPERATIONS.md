# ANPOS Design, Data and Operations Assurance — Requirements 67–74

These requirements apply to child projects when relevant to their product/platform. The template source stores policy only.

## 67 — Design Version and Approval Lock

When an external design is used, persist provider/file/node identifiers, immutable version/revision/snapshot reference when available, captured timestamp, design-system/token version, audit result, and explicit approval status. Development must not silently mix revisions. Material design changes after approval trigger impact analysis and update affected work units.

## 68 — Visual Regression and Design Traceability

Trace important UI requirements through design surfaces/components to implementation and verification. For visual products, record responsive target states and use screenshot/visual-regression evidence where tooling permits. Pixel-level matching is required only when the product requirement says so; otherwise verify hierarchy, spacing/tokens, states, interactions and accessibility against the approved design contract.

## 69 — Accessibility Baseline

For web products, default to WCAG 2.2 AA unless a stronger/project-specific standard is approved. Native apps use equivalent platform accessibility guidance. Define keyboard/focus behavior, semantics/labels, contrast, zoom/reflow, reduced motion, error identification, touch targets and screen-reader expectations as applicable. Accessibility acceptance is testable, not decorative documentation.

## 70 — Data Classification and Privacy Lifecycle

Every project defines data classes (for example Public/Internal/Confidential/Restricted/Secret plus PII/financial/health/regulatory tags as applicable), permitted storage/transit/logging/AI usage, retention/deletion, backup treatment, masking/redaction, non-production rules, export/subject-right handling when applicable, and breach/incident sensitivity. Production data must not be copied to lower environments without an approved protected process.

## 71 — Threat Model and Security Verification Artifact

Maintain a project threat model with assets, actors, trust boundaries, entry points, abuse cases, controls, residual risks and verification references. Link security requirements/findings to tests/evidence. Use OWASP ASVS or another appropriate standard as a verification baseline where applicable, tailored to the actual product rather than blindly requiring irrelevant controls.

## 72 — API / Database Contract Migration Safety

Breaking API/schema/data changes require compatibility and migration planning. Prefer expand→migrate/backfill→verify→contract for live systems. Define consumer compatibility, dual-read/write when justified, migration idempotency, large-data/runtime impact, rollback/roll-forward, backup/restore prerequisites and irreversible-step approval. No destructive migration is considered safe because it works on an empty development database.

## 73 — Observability, SLO, Incident and Disaster Recovery

Production-capable projects define relevant service indicators/objectives, alert severity/routing, logging/metrics/tracing standards, privacy-safe telemetry, incident roles, mitigation/hotfix flow, post-incident review, backup/restore tests, and RTO/RPO expectations where business impact warrants them. Operational readiness is part of release readiness.

## 74 — Budget, Rate, Retry and Recursion Guardrails

Agentic automation defines limits for maximum parallel agents, delegation depth, retry count/backoff, tool-call loops, token/model budget, CI minutes, external API rate limits, cloud/infra spend and destructive-operation frequency where applicable. Use circuit breakers for repeated failures. An autonomous agent must stop/escalate rather than consume unbounded resources or recursively delegate forever.
