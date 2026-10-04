# ANPOS AI-Native Governance Assurance — Requirements 89–96

These requirements extend ANPOS from product assurance into durable governance, accountability, compliance evidence, architectural continuity, AI configuration identity, lifecycle compatibility, operational resilience and unified risk control.

They are capability-aware and project-type-aware. The canonical source stores reusable policy only. Child projects activate only the controls justified by product impact, data sensitivity, AI behavior, contractual/regulatory exposure and operational risk.

## 89 — Responsible AI and Human Oversight

When AI materially affects users, decisions, access, safety, finances, employment, health, rights, reputation or other high-impact outcomes, the child project must define an oversight contract appropriate to the risk.

Where applicable, record:

- intended AI use and prohibited uses;
- affected user/population groups;
- known limitations and uncertainty;
- fairness/bias evaluation dimensions and evidence;
- explainability/traceability requirements;
- human-review or escalation thresholds;
- appeal/correction path when decisions materially affect a person;
- confidence/uncertainty handling;
- disclosure requirements when users should know AI is involved;
- emergency suspend/disable authority;
- monitoring for harmful drift or disproportionate failure;
- approved owner for residual responsible-AI risk.

ANPOS does not assume every project needs demographic fairness testing. The project must record why a dimension is applicable or not applicable.

A high-impact automated decision must not become irreversible solely because an AI produced it when project policy requires human review.

Machine policy: `config/ai/responsible-ai-policy.json`.

## 90 — Privacy, Regulatory and Compliance Evidence

Projects processing personal, sensitive, regulated or contractually restricted data must map relevant obligations into evidence-backed engineering controls.

Where applicable, record:

- jurisdiction and operating context;
- data categories and purposes;
- lawful/authorized processing basis where a qualified determination exists;
- consent requirements where applicable;
- data residency/localization constraints;
- controller/processor or equivalent roles when relevant;
- subprocessors/external providers;
- retention and deletion basis;
- data-subject/user-right workflows;
- cross-border transfer constraints;
- privacy/DPIA/PIA assessment requirement and status;
- regulatory/security standard mappings;
- required human/legal/compliance review;
- evidence references and review expiry.

ANPOS must not invent a legal conclusion. Unknown applicability remains explicit and may require qualified human review.

Machine policy: `config/compliance/compliance-profile.json`.

## 91 — Architecture Decision Records

Material architecture decisions must remain reconstructable after the original chat/session disappears.

Record, where material:

- decision ID and title;
- context/problem;
- considered alternatives;
- evidence and constraints;
- selected decision;
- trade-offs/consequences;
- security/privacy/data/operational/cost impact;
- reversibility;
- affected modules/contracts;
- approved/decided identity and date;
- status: proposed / accepted / rejected / superseded;
- supersedes/superseded-by relationship.

A later AI must not silently reverse an accepted material decision. It may propose a replacement ADR with impact analysis and normal consent when required.

Machine policy: `config/architecture/decision-records.json`.

## 92 — AI Asset and Configuration Registry

AI-system assurance must bind evaluation evidence to the exact behavior-producing configuration.

For AI/ML/LLM/RAG/agentic projects, track relevant identities such as:

- provider and model family/version;
- model configuration;
- system/developer prompt bundle identity/hash;
- prompt-template bundle identity/hash;
- tool/function schema identity/hash;
- retrieval/index snapshot;
- embedding model/version;
- reranker/version;
- safety/policy configuration;
- evaluation dataset/version;
- important external knowledge snapshot/version;
- last certified evaluation reference;
- deployment/environment binding.

Material configuration drift invalidates stale assurance evidence according to Requirement 83.

Do not store secrets or proprietary hidden provider internals that are unavailable; record explicit unknowns instead.

Machine policy: `config/ai/asset-registry.json`.

## 93 — Compatibility, Deprecation and End-of-Life Management

Production-capable projects must avoid surprise breakage from unsupported interfaces, dependencies or runtimes.

Where applicable define:

- supported API/SDK/schema/runtime versions;
- compatibility promises;
- deprecation announcement date;
- migration target/path;
- support window;
- planned removal/EOL date;
- affected consumers;
- notification/evidence requirement;
- exception process and expiry;
- rollback/compatibility strategy;
- upstream runtime/framework/vendor EOL dependencies.

A deprecated contract must not be removed before its approved compatibility/support conditions are satisfied unless an authorized emergency/security exception applies.

Machine policy: `config/contracts/deprecation-policy.json`.

## 94 — Operational Runbooks and Resilience Drills

Operational readiness requires executable recovery knowledge, not only SLO/RTO/RPO statements.

For production-critical capabilities define runbooks where relevant for:

- bad deployment/rollback;
- database or storage outage;
- authentication/identity outage;
- queue/backlog failure;
- dependency/provider outage;
- AI provider/model degradation;
- credential compromise;
- data corruption/restore;
- capacity/resource exhaustion;
- security containment;
- emergency feature/agent disable.

Critical runbooks should be tested through bounded drills, recovery exercises or safe failure injection appropriate to the environment. Record expected behavior, actual result, recovery time, data loss, findings and follow-up work.

Machine policy: `config/operations/runbooks-and-drills.json`.

## 95 — Tamper-Evident Audit Journal

Privileged AI/human/runtime actions should be reconstructable without storing secrets or full sensitive prompts.

Where applicable journal:

- verified actor/identity reference;
- role;
- action type;
- target/resource;
- tool/provider;
- base/source ref;
- result ref;
- consent/approval reference;
- sanitized input/output or artifact hashes;
- timestamp;
- result;
- risk class;
- previous-entry hash and current-entry hash.

The journal uses an append-oriented hash-chain contract or equivalent tamper-evident mechanism. It is evidence, not authorization by itself.

Secret values, credentials, sensitive full prompts and unrelated personal data must not be copied into the audit journal.

Machine policy: `config/audit/audit-journal.json`.

## 96 — Unified Risk and Exception Register

Material security, privacy, AI, product, operational, financial, compliance and architecture risks should be tracked under one lifecycle.

Each risk/exception should record where applicable:

- ID/category/title;
- description and evidence;
- likelihood and impact;
- owner;
- mitigation;
- residual risk;
- linked requirements/modules/incidents/findings;
- acceptance/exception status;
- authenticated consent reference where required;
- review/expiry date;
- current disposition.

Risk acceptance is not permanent by default. Expired acceptance must reopen the risk for review.

Machine policy: `config/risk/risk-register.json`.

## Lifecycle integration

Requirements 89–96 complement, not replace, Requirements 45–88.

- planning/system design: 89, 90, 91, 96;
- AI architecture/development: 89, 92, 96;
- API/data/platform evolution: 91, 93;
- release/operations: 90, 93, 94, 95, 96;
- incidents/continuous improvement: 94, 95, 96;
- high-impact AI release: 83 plus 89 plus 92.

All Requirements 83–96 are tracked in `config/assurance/assurance-state.json`.

## Evidence rule

A policy file is not completion evidence. Passing a requirement requires project-specific evidence bound to the relevant source/runtime/configuration identity. `not_applicable` requires a project-specific reason.
