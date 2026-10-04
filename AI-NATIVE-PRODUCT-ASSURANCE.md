# ANPOS AI-Native Product Assurance — Requirements 83–88

These requirements extend the ANPOS child-project lifecycle beyond implementation correctness into AI-system evaluation, user validation, product evidence, controlled experimentation, progressive delivery, and engineering maintainability.

They are **capability-aware and project-type-aware**. A requirement activates only when relevant to the product being built. The canonical template source remains inert and stores reusable policy only.

## 83 — AI / LLM Evaluation and Model Assurance

When a child project contains AI/ML/LLM/RAG/agentic behavior, software tests alone are not sufficient.

The project must define an evaluation contract appropriate to the AI behavior, including where relevant:

- representative and adversarial evaluation datasets;
- golden/reference cases with provenance and versioning;
- prompt/system-instruction regression tests;
- model/provider/version comparison;
- structured-output/schema correctness;
- retrieval quality, grounding and citation correctness for RAG systems;
- hallucination/fabrication rate or equivalent factuality measure;
- tool-call selection, arguments and side-effect correctness for agents;
- multi-step task-completion evaluation;
- safety/policy/refusal behavior appropriate to the product;
- prompt-injection and untrusted-context resistance;
- latency, token, inference and external-tool cost budgets;
- reliability across retries/timeouts/provider degradation;
- privacy/data-boundary verification for evaluation data.

Evaluation thresholds must be tied to the exact model/prompt/retrieval/tool configuration under test. A model or prompt change that can materially affect behavior requires targeted re-evaluation.

Do not use a single aggregate score to hide critical failure classes. High-risk failures may block release even when average quality improves.

Machine policy: `config/ai/ai-evaluation-policy.json`.

## 84 — User Research, Problem Validation and UX Validation

For user-facing products, market research and design review do not substitute for validation with credible user evidence.

Before or during material product/design commitments, define where applicable:

- target users/personas or jobs-to-be-done;
- problem hypotheses and evidence strength;
- critical user journeys and success criteria;
- prototype/wireframe validation needs;
- usability test tasks and observable success/failure signals;
- accessibility-inclusive research needs;
- qualitative feedback provenance;
- design findings and required revisions;
- unresolved assumptions that must not silently become requirements.

For major UX surfaces, prefer a loop of:

`problem hypothesis → flow/prototype → user/usability evidence → findings → design revision → implementation → usability verification`

User research may be lightweight for low-risk/simple projects, but the AI must explicitly record when validation is skipped and why.

Machine policy: `config/product/product-validation.json`.

## 85 — Product Analytics and Outcome Evidence

A technically complete project is not automatically a successful product.

User-facing or business-critical child projects must define measurable product outcomes where useful, such as:

- activation;
- task completion;
- feature adoption;
- conversion;
- retention;
- churn;
- reliability/error impact;
- funnel completion;
- support/contact rate;
- latency experienced by users;
- satisfaction or other project-specific success signals.

Analytics design must specify:

- metric definitions and owners;
- event/data schema;
- privacy/data classification;
- collection purpose and retention;
- source-of-truth system;
- baseline and target when justified;
- segmentation limits to avoid misleading conclusions;
- instrumentation verification;
- interpretation caveats.

Never invent KPI success from code completion, deployment, synthetic traffic, or vanity metrics. Post-release evidence should feed the normal ANPOS planning/options/modules process.

Machine policy: `config/product/product-analytics.json`.

## 86 — Experimentation and Hypothesis Lifecycle

When uncertainty can be reduced safely through experimentation, ANPOS supports a bounded experiment lifecycle.

Every material experiment should record:

- hypothesis;
- target population or environment;
- intervention/variant;
- primary success metric;
- guardrail metrics;
- minimum observation/evidence rule appropriate to the decision;
- privacy/security/ethical constraints;
- rollout and rollback plan;
- start/end or stopping criteria;
- analysis result;
- decision: adopt / revise / reject / inconclusive.

A/B testing is optional, not mandatory. Experiments may be prototype tests, staged pilots, shadow comparisons, model evaluations, usability tests, or controlled production variants.

Do not run experiments that expose users to material undisclosed risk, weaken security/privacy controls, or bypass consent/legal requirements.

Machine policy: `config/product/experimentation-policy.json`.

## 87 — Progressive Delivery and Feature Safety

Production-capable projects should use the least risky release strategy appropriate to their architecture and impact.

Where useful, define:

- feature flags with ownership and cleanup dates;
- environment promotion rules;
- preview/staging verification;
- canary or percentage rollout;
- blue/green or parallel deployment;
- shadow/read-only comparison;
- automatic rollback/stop thresholds;
- health/SLO/error guardrails;
- migration compatibility during mixed-version rollout;
- kill-switch/emergency-disable behavior;
- rollback and roll-forward evidence.

Feature flags must not become permanent hidden configuration debt. Security/authz controls must not rely on a client-side feature flag as their authorization boundary.

A project may choose a simpler deployment when risk is low, but should explicitly record the selected rollout mode.

Machine policy: `config/release/progressive-delivery.json`.

## 88 — AI-Generated Engineering Quality and Maintainability Review

Passing tests is necessary but does not prove that AI-generated or rapidly generated code is maintainable.

Before major module completion or release, perform a bounded engineering-quality review covering relevant areas:

- correctness and acceptance-criteria coverage;
- architecture/module-boundary conformance;
- unnecessary complexity or premature distribution;
- duplication and inconsistent abstractions;
- dead/stale/temporary code;
- dependency quality and unnecessary packages;
- API/contract consistency;
- data ownership and migration discipline;
- error handling and observability consistency;
- security and privacy design adherence;
- performance/resource implications;
- test quality, determinism and meaningful failure coverage;
- documentation and persistent-state consistency;
- technical debt introduced or intentionally accepted.

The review must produce actionable findings with severity, evidence, affected paths/modules and disposition. It must not reward superficial metrics such as line-count reduction or arbitrary complexity scores without project context.

Critical correctness/security/data-integrity defects block completion. Material maintainability debt must be fixed, explicitly deferred with rationale, or tracked as planned work.

Machine policy: `config/quality/engineering-review-policy.json`.

## Lifecycle integration

These requirements do not replace `START-HERE.md`, `DEVELOPMENT-LIFECYCLE.md`, `CODE-QUALITY.md`, `PRODUCTION-ASSURANCE.md` or `DESIGN-DATA-OPERATIONS.md`. They add conditional assurance gates:

- planning/design: Requirements 84–86;
- AI architecture/development: Requirement 83;
- development/SQA: Requirement 88;
- release: Requirements 83, 85, 87, 88 as applicable;
- post-release continuous improvement: Requirements 85–86.

## Project-type activation examples

### Static/content site
Usually relevant: 84, 88; 85 if business outcomes are measured.  
Usually not required: 83; 87 may be minimal.

### Conventional SaaS
Usually relevant: 84, 85, 86, 87, 88.  
83 activates only if product behavior uses AI/ML/LLMs.

### AI / agentic SaaS
Usually relevant: all Requirements 83–88.

### Internal tooling
Activate only the controls justified by user impact, operational risk, data sensitivity and AI behavior.

## Evidence rule

A blueprint/configuration is not completion evidence. Mark a requirement satisfied only when the child project has project-specific artifacts, tests, metrics, research/evaluation results, or verified provider/runtime evidence appropriate to that requirement.


## Persistent assurance state and evidence

Requirements 83–88 are tracked inside the unified Requirements 83–96 `config/assurance/assurance-state.json`. A requirement may be `pending_detection`, `applicable`, `optional`, or `not_applicable`; completion states are separately tracked and require evidence.

Research and market evidence that materially informs requirements, options, modules, architecture, design or product decisions is recorded in `config/research/evidence-registry.json` with provenance, validation state and explicit fact/inference classification.

Specialized JSON Schemas under `schemas/` validate the unified assurance state, research registry and Requirements 83–96 policy surfaces.

## Runtime executor contract

`config/assurance/runtime-executors.json` defines provider-neutral executor inputs/outputs for AI evaluation, product/UX validation, analytics, experiments, progressive delivery and engineering review. A provider/tool is not considered integrated merely because its product name is known; it must satisfy the required capability and evidence contract.

## Protocol release preparation

ANPOS 1.4.0 is the active protocol baseline for Requirements 83–96. `config/protocol/next-release.json` now resets to an unplanned future-release state; future protocol changes must create a new explicit release plan.
