# ANPOS Production Assurance — Requirements 57–66

This protocol defines child-project production maturity. The canonical template source remains inert and stores reusable policy only.

## 57 — Capability-Aware Quality Bootstrap

Before enabling repository-hosted quality/security features, inspect the child repository visibility, plan/features, permissions, languages, package ecosystems, and available GitHub security capabilities. Install/enable only supported checks, record unsupported checks as `not_available`/`deferred`, and choose equivalent open/local tooling when useful. Never create a knowingly red baseline solely because a generic blueprint exists.

## 58 — Quality Workflow Contract Verification

Every installed workflow must be validated for required permissions, trigger safety, required feature/licensing assumptions, output/check names, and compatibility between related action components. A workflow option that writes PR comments/issues/SARIF must have the minimum explicit write permission required or that write behavior must be disabled.

## 59 — Stack-Adaptive Dependency Management

After the technology stack is approved, generate Dependabot/Renovate-equivalent configuration for every relevant package ecosystem, container/base image, infrastructure dependency, and GitHub Action used by the child project. Coordinate tightly-coupled dependency families rather than blindly merging independent updates.

## 60 — Formal Schema Enforcement

Machine state must be checked against real JSON Schema (Draft 2020-12 or later compatible validator), not only handwritten checks. Schemas define required fields, enums, transitions, provenance and security-critical invariants. Unknown properties are allowed only where intentionally declared as extension points.

## 61 — Release and Environment Protocol

Production-capable projects define environments such as local/dev/preview/staging/production as applicable. Each environment records deployment authority, secrets scope, data classification, required checks, approval gates, migration policy, smoke tests, rollback strategy, and observability.

Release readiness requires a release candidate tied to an immutable commit, successful required checks, migration preflight, security/QA acceptance, release notes, deployment plan, rollback plan, post-deploy verification, and recorded outcome.

## 62 — Secrets, Identity and Deployment Security

Use short-lived workload identity/OIDC where supported instead of long-lived cloud credentials. Enable secret scanning/push protection where available, prohibit secrets in repository/PM/AI memory, scope secrets by environment, define rotation/revocation, and prevent untrusted PR code from accessing privileged credentials.

## 63 — SBOM, Provenance and Attestation

Production release artifacts should include or reference an SBOM, source commit, dependency lock state, build workflow identity, provenance/attestation when platform support exists, artifact digest, and verification instructions. Release evidence is part of requirement traceability.

## 64 — PM Synchronization Conflict Engine

Repository/Git reality is authoritative for code, branches, PR/MR, merge, tests and release evidence. For fields the PM provider may legitimately own (for example human priority labels or business target dates), define explicit per-field authority. Synchronization uses provider cursors/revisions where available, idempotency keys, external-ID history and loop prevention. Conflicts are reconciled deterministically and never silently overwrite newer authoritative state.

## 65 — Typed Agent Handoff Envelope

Supervisor→Worker handoff must include: work/requirement IDs, role, required capabilities, allowed paths, denied paths, approved tools/network, base SHA, coordination epoch/fencing context, dependencies, acceptance criteria, required checks, lease/expiry, risk classification, secret/deployment restrictions, and expected output/review handoff.

## 66 — AI Provider Privacy and Data Boundary

Before attaching a development AI to a child project, record what repository/data scope it can access, whether external network/tools are enabled, data retention/training controls when known, geographic/enterprise constraints when relevant, secret access policy, and whether project policy permits the provider for the applicable data classification. Unknown privacy properties remain explicit unknowns; never fabricate assurances.
