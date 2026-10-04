# Start Here

This document defines the mandatory path from a repository created from ANPOS to project research, planning, and engineering execution.

## State A — Repository link received

Inspect:

- the actual current Git repository identity;
- `config/protocol/instance.json`;
- `AGENTS.md`;
- `.ai/manifest.json`;
- `PROJECT-INITIALIZATION.md`.

Canonical source repository:

`Vertex-Systems-Network/ai-native-project-operating-system`

### If this is the canonical source

The source is an inert template/protocol repository. Do not attach a live PM provider, select a live project-specific AI pool, apply child GitHub Rules, activate child code-quality/runtime workflows, or start application development against it.

The development target must be a **new child repository created/copied from this template**.

### If this is a child repository

If the child inherited `instance_status: template_source`, treat it as uninitialized and bootstrap it. If it is already `active_project`, resume from the first incomplete setup/lifecycle state.

If project intake is not complete, offer the single primary action:

**Start Development**

Preferred UI when supported:

- Primary button/action: `Start Development`

Fallback:

- Ask the user to reply: `Start Development`

## State B — Start Development activated

### B1. Bootstrap the child repository

Run the safe child-instance bootstrap from `scripts/bootstrap_instance.py` or equivalent repository writes.

The bootstrap must:

- create child instance identity;
- clear inherited runtime claims/leases/alerts/consents/merge state;
- regenerate valid child CODEOWNERS;
- reset PM/provider selection to unresolved;
- reset development-AI selection to unresolved;
- install the universal child Code Quality/runtime workflow blueprints into active child `.github/` paths;
- leave GitHub Rules unapplied until the user is asked.

### B2. Choose Project Management System

Load `PROJECT-MANAGEMENT.md` and `config/integrations/project-management.json`.

Discover project-management providers actually connectable/attachable in the current host and present:

**Choose Project Management System**

Candidate options may include:

- **Linear — Recommended**
- GitHub Projects
- Jira / Atlassian
- ClickUp
- GitLab Issues / Boards
- Azure DevOps Boards
- Plane
- Asana
- monday.com
- Notion
- Other compatible provider
- **Skip Project Management**

Only make an option actively selectable when a real connector/MCP/OAuth/API/git-native setup path exists. Unavailable products may be shown separately as recommendations.

If the user skips, continue with repository-backed planning and allow PM connection later.

### B3. Connect/map the selected PM provider

Use the provider's secure connected-app/OAuth/MCP/authentication path. Never ask for an ordinary password, raw private token, or session cookie in normal chat.

After connection:

1. discover available workspace/organization/project choices;
2. select/attach the intended project, or create one when needed and authorized;
3. persist selected provider + mapping only in the child repository;
4. enable sync only after mapping is verified;
5. mirror planning/progress automatically according to `PROJECT-MANAGEMENT.md`.

GitHub/repository state remains canonical for code, branches, PR/MR, merge, test, and release reality.

If Linear is selected, use `config/integrations/linear-sync.json` as the Linear-specific adapter state.

### B4. Choose Development AI

Discover development agents/tools actually usable in the current host and present:

**Choose Development AI**

Candidate examples may include:

- Codex / ChatGPT
- Claude Code
- GitHub Copilot
- Gemini
- Cursor
- Windsurf
- Other verified compatible agent

Only actually attachable/invokable agents are active selection choices. Allow one or more agents where supported and record the selection in `config/ai/agent-catalog.json`.

When useful, let the selected pool define roles such as one Supervisor plus multiple Workers. Do not claim an agent is attached merely because it is known by name.

### B5. Verify/apply the Code Quality baseline

The child bootstrap installs the universal baseline from `blueprints/github/`.

Verify the child files/workflows exist and are valid. Do not say a GitHub check is active/passing until the child repository has produced evidence.

After technology approval later in the lifecycle, automatically add mature stack-specific formatter/linter/static-or-type-analysis/test/build/dependency/security tooling appropriate to the actual stack.

### B6. Ask about GitHub Rules

After the child baseline is installed enough to determine real check names, present:

- Primary action: `Apply Recommended GitHub Rules`
- Secondary action: `Review GitHub Rules`

If the user approves and the AI has authenticated repository-admin write capability, apply `config/github/ruleset-policy.json`, then re-read GitHub and verify enforcement.

If the AI cannot apply rules itself, provide the exact required manual settings, mark `pending_user_action`, and verify after the user performs them.

Do not apply this child-project Rules flow to the canonical template source.

### B7. Collect project intake

Present one large free-form intake field when supported, labeled:

**Idea / Thoughts / Plan / Research / Search / Assumptions**

Prompt:

> Add everything you currently have about the project in one place. This can be a raw idea, incomplete thoughts, an existing plan, research, links, search notes, assumptions, desired features, constraints, references, competitors, technical preferences, or uncertainties. It does not need to be organized.

Fallback:

> Paste your Idea / Thoughts / Plan / Research / Search / Assumptions in one message. It can be completely unstructured.

Do not force the user through multiple required project-description fields.

## State C — Intake received

Persist/update normalized project intake in `PROJECT-IDEA.md` when child repository write access is available.

Then execute the following sequence before implementation.

### 1. Understand

Extract and distinguish:

- explicit requirements
- facts
- assumptions
- preferences
- constraints
- open questions
- risks
- references
- existing decisions

Never silently promote an assumption into a fact or requirement.

### 2. Search the internet for possibilities

When web/search capability is available, proactively investigate:

- existing solutions and competitors
- comparable products
- relevant workflows/user expectations
- current technologies/implementation approaches
- APIs/platforms/libraries/standards/integrations
- technical/operational/regulatory/security/privacy/accessibility constraints
- pricing/business-model patterns where relevant
- known failure modes/common mistakes
- opportunities not mentioned by the user

The purpose is discovery, not confirmation of the user's assumptions.

### 3. Research the strongest possibilities

Deepen the most relevant findings. Prefer current, primary, authoritative, or technically credible sources. Compare alternatives and trade-offs; do not base important decisions on one snippet/source.

### 4. Reason independently

The AI should:

- test assumptions against evidence
- identify missing pieces
- identify contradictions
- identify hidden dependencies
- consider simpler/stronger alternatives
- identify feasibility/scope risks
- separate must-haves from optional ideas
- mark unresolved uncertainty explicitly

### 5. Compare with the current market

Compare the normalized concept against relevant direct/indirect competitors, category leaders, newer products, and open-source substitutes.

Examine where relevant:

- common features and user journeys
- positioning/differentiation
- pricing/monetization
- onboarding/activation
- integrations/ecosystem expectations
- platform coverage
- trust/privacy/security/compliance/accessibility expectations
- operational models
- recurring complaints/weaknesses/gaps

Identify where the user's idea is stronger, weaker, undifferentiated, missing important capabilities, or carrying unnecessary complexity.

### 6. Deeply audit comparable systems

For the most relevant systems, analyze what can responsibly be established about:

- scope/target users/jobs-to-be-done
- feature architecture/information architecture
- major user flows/onboarding
- roles/permissions/collaboration
- automation/integrations
- pricing/business model
- platform/deployment/API ecosystem where observable
- data handling/privacy/security/compliance/trust signals
- credible performance/reliability/operational characteristics
- recurring user complaints/limitations/failure patterns
- strengths worth learning from
- weaknesses worth avoiding
- reusable product/architecture decisions

Clearly distinguish verified evidence, reasonable inference, and unknown/private implementation details.

### 7. Synthesize findings and plan

Only after discovery/research/reasoning/market comparison/audits should the AI create the project plan.

The plan must be grounded in:

- user intent
- normalized intake
- repository reality
- external evidence
- market comparison
- lessons from comparable systems
- technical feasibility
- risks/constraints
- discovered opportunities/gaps

Explicitly revise, add, remove, simplify, or reprioritize proposed capabilities when evidence justifies it.

At minimum distinguish:

- validated requirements
- assumptions still requiring validation
- recommended additions
- recommended removals/simplifications
- competitive/market-driven requirements
- differentiators
- risks
- unresolved decisions
- phased implementation priorities

After the plan is created or materially revised, sync it to the selected PM provider when one is connected.

## State D — Post-planning engineering lifecycle

After Stage 7, continue using `DEVELOPMENT-LIFECYCLE.md`.

Required sequence:

8. **System Design**
9. **Technology Selection + Consent** — present `Approve Technology Stack`; use `Review Alternatives` where useful.
10. **Development Architecture Design**
11. **Data Flow Design**
12. **Professional UI/UX Design**
13. **Development + DevOps**
14. **SQA**
15. **Security Engineering + Authorized Adversarial Assessment**

Then apply the capability-aware assurance requirements from `AI-NATIVE-PRODUCT-ASSURANCE.md`:

16. **AI / LLM Evaluation + Model Assurance** — required when the product contains AI/ML/LLM/RAG/agentic behavior.
17. **User / Problem / UX Validation** — required when user-facing assumptions or material UX decisions need evidence.
18. **Engineering Quality + Maintainability Review** — required before major module completion/release.
19. **Progressive Delivery + Production Verification** — required when release risk justifies staged rollout/feature controls.
20. **Product Analytics / KPI Evidence + Experiment Feedback Loop** — required when product outcomes are measurable/material; experimentation remains optional and bounded.

These are project-type-aware gates, not mandatory bureaucracy. Mark a gate `not_applicable` only with a project-specific reason and evidence.

Also apply the cross-cutting governance requirements from `AI-NATIVE-GOVERNANCE-ASSURANCE.md` when relevant:

- **89 Responsible AI + Human Oversight**
- **90 Privacy / Regulatory / Compliance Evidence**
- **91 Architecture Decision Records**
- **92 AI Asset + Configuration Registry**
- **93 Compatibility / Deprecation / EOL Management**
- **94 Operational Runbooks + Resilience Drills**
- **95 Tamper-Evident Audit Journal**
- **96 Unified Risk + Exception Register**

These are assurance/governance controls across the lifecycle, not eight additional sequential development stages.

After technology approval, the AI also completes the stack-specific Code Quality installation defined by `CODE-QUALITY.md` and verifies resulting child-project check names before final GitHub Rules enforcement/adjustment.

Security requirements influence every lifecycle stage; Stage 15 is the dedicated final hardening/adversarial verification pass.

Do not skip the technology-consent gate unless the user has already explicitly approved a concrete stack for the child project.


### Blueprint closure and extension boundary

The ANPOS 1.4.0 canonical blueprint is closed at Requirements 1–96. Read `config/protocol/blueprint-completion.json` when auditing completeness. It proves reusable blueprint coverage only; child implementation/pass claims still require project-specific evidence.

For repository-level acceptance, use `config/testing/reference-e2e-matrix.json` and execute only the scenario applicable to the real repository state. A reference scenario marked `reference_only` is not runtime certification evidence.

Do not append REQ-97+ or introduce a core-semantic extension ad hoc. Future normative requirements and extensions must follow `config/protocol/extension-contract.json`, including explicit release planning, compatibility, migration, schema evolution and deprecation.
