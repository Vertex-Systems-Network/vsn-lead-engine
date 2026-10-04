# AI-Native Execution and Project Memory Protocol

This document defines how the AI must own, remember, plan, decompose, and continuously execute the project after the discovery and planning lifecycle has established a validated direction.

## Principle: treat the project as an active engineering responsibility

The AI must behave as if it is responsible for bringing the repository from its current verified state to the approved product outcome.

This does **not** mean ignoring human authority. Product, legal, business, risk-acceptance, and explicit consent decisions remain human-controlled where required. It means the AI must not act like a stateless code generator waiting to be told every next step.

The AI must continuously know, as far as repository evidence permits:

- what the project is trying to become
- what has already been completed
- what is partially completed
- what remains to be built
- what needs to be updated
- what should be removed or deprecated
- what is blocked
- what is invalid or stale
- what was intentionally deferred
- what dependencies exist
- where development should resume
- what the next highest-value valid work item is

## Repository-backed memory bank

Chat history and model memory are never sufficient as the project source of truth. The repository must carry a persistent memory bank that another compatible AI can read and continue from.

The required machine-readable core is:

- `config/ai/project-state.json`
- `config/ai/options-bank.json`
- `config/ai/modules-bank.json`
- `config/ai/execution-plan.json`

The required human-readable planning artifact is:

- `docs/ai/PRE-PLAN.md`

Additional decision records, research, architecture documents, work logs, QA reports, or security reports may be created as the project grows.

### Memory-bank truth hierarchy

When resuming or starting work, reconcile evidence in this order:

1. explicit current user instruction
2. actual repository state and current code
3. current Git branch/commit history and merge state when available
4. approved architecture and technology decisions
5. verified tests/build/deployment evidence
6. `config/ai/project-state.json`
7. `config/ai/execution-plan.json`
8. `config/ai/modules-bank.json`
9. `config/ai/options-bank.json`
10. older planning notes or conversation context

If a memory-bank entry disagrees with verified repository reality, repository reality wins and the memory bank must be repaired.

Never continue blindly from stale state.

## Mandatory resume/reconciliation pass

Before choosing development work, inspect enough repository evidence to answer:

- What exists now?
- What changed since the last recorded AI state?
- Which modules are complete, active, blocked, deprecated, or not started?
- Which tests and quality gates currently pass or fail?
- Are there unfinished migrations, TODOs, temporary implementations, dead code, stale documents, or abandoned paths?
- Is the recorded next task still valid?
- Does anything now need update, replacement, cleanup, or deletion?

Then update the memory bank before or alongside new execution work.

## Pre-plan before implementation

Before large-scale implementation, create and maintain `docs/ai/PRE-PLAN.md`.

The pre-plan is an engineering decomposition document, not a marketing summary. It should capture:

- validated product objective
- scope and non-scope
- primary actors and workflows
- current repository reality
- major system capabilities
- known constraints
- key risks
- dependencies
- technology decisions and their approval state
- proposed major modules
- sequencing constraints
- milestones/phases
- acceptance strategy
- QA/security expectations
- deployment implications
- unresolved decisions

The pre-plan should be revised when material evidence changes. Do not preserve a plan merely because it was written earlier.

## Options Bank

Maintain `config/ai/options-bank.json` as a reusable catalog of capabilities/options that may be attached to one or more modules.

An option is a discrete product or engineering capability such as:

- social login
- email/password authentication
- MFA
- role-based access control
- file upload
- search
- notifications
- audit logging
- offline support
- localization
- subscriptions
- exports
- analytics
- API access
- webhooks
- backup/restore behavior

Each option should have a stable ID and may contain:

- name
- category
- description
- status
- requirement source
- priority
- dependencies
- conflicts
- technical implications
- UX implications
- data implications
- security implications
- QA implications
- selected/rejected/deferred state
- rationale

Do not duplicate the same capability independently inside many modules when it can be referenced by a shared option ID.

## Modules Bank

Maintain `config/ai/modules-bank.json` as the canonical module catalog.

Each module should represent a coherent, testable area of responsibility, for example:

- authentication
- users
- organizations/workspaces
- projects
- billing
- notifications
- reporting
- admin
- integrations

Each module should include, where applicable:

- stable module ID
- name
- objective
- scope
- boundaries
- dependencies
- attached option IDs from the Options Bank
- data/entities owned or touched
- APIs/contracts exposed or consumed
- UI surfaces
- security responsibilities
- acceptance criteria
- tests/quality gates
- implementation status
- completion evidence
- update/delete/deprecation notes

### Module-option attachment rule

A module references reusable options through stable option IDs. Example conceptually:

`AUTH` -> `OPT-EMAIL-LOGIN`, `OPT-GOOGLE-OAUTH`, `OPT-MFA`, `OPT-RBAC`

This lets the AI understand both the module and the exact capabilities configured for it without duplicating definitions.

## Phase -> module -> work-unit decomposition

Do not execute a project as a few giant phases.

Translate the approved roadmap into a dependency-aware hierarchy:

`Project -> Phase/Milestone -> Module -> Work Unit -> Acceptance/Verification`

A phase is an outcome boundary, not a giant coding task.

A module is a cohesive product/engineering responsibility.

A work unit is the smallest useful independently executable and verifiable slice.

Prefer work units that are:

- small enough to understand quickly
- independently testable where practical
- dependency-explicit
- reversible or low-blast-radius where possible
- reviewable in isolation
- capable of reaching a clear done state
- valuable enough to advance the module

Do not split work into meaningless micro-tasks that create coordination overhead without reducing risk.

## Execution Plan

Maintain `config/ai/execution-plan.json` as the active dependency-aware work graph.

It should track at minimum:

- phases/milestones
- modules assigned to each phase
- work units for each module
- dependencies
- priority
- status
- blockers
- acceptance criteria
- required tests/checks
- completion evidence when finished

Useful statuses include:

- `not_started`
- `ready`
- `in_progress`
- `blocked`
- `needs_update`
- `needs_removal`
- `verification_required`
- `complete`
- `deferred`
- `deprecated`

## Project State

Maintain `config/ai/project-state.json` as the compact answer to: **where are we now and where should work resume?**

It should expose at minimum:

- lifecycle stage
- current phase
- current module
- current work unit
- last verified completion
- next valid work unit
- counts of total/complete/in-progress/blocked/deferred work
- outstanding updates
- outstanding removals/deprecations
- unresolved decisions
- known critical defects
- QA/security readiness
- last reconciled repository reference when available

Do not fake precision. If progress percentages cannot be credibly calculated, use work-unit counts and status summaries instead.

## Autonomous next-work selection

When the user has authorized AI-native development and no human decision blocks progress, the AI should determine the next valid work item rather than asking the user which module to work on.

Choose work using evidence such as:

1. blocking dependencies and critical path
2. safety/security/correctness blockers
3. approved phase priority
4. module dependencies
5. user-visible value
6. risk reduction
7. ability to complete and verify a small slice quickly

Never choose a task solely because it is easy.

## Update and delete discipline

The AI must recognize that development includes more than adding code.

If repository evidence shows obsolete, duplicate, unsafe, contradictory, or superseded artifacts, classify them appropriately as:

- update required
- migration required
- removal required
- deprecation required
- documentation sync required

Deletion must be evidence-based. Do not remove working behavior merely because a new approach is preferred. Check dependencies, public contracts, data migration impact, tests, and rollback implications first.

## Continuous synchronization

After meaningful work, synchronize the relevant artifacts:

- implementation
- tests
- documentation
- module status
- options status when changed
- execution-plan status
- project state
- decisions/rationale

A completed work unit with stale planning/state metadata is not fully complete.

## Definition of AI-native execution

AI-native development in this repository means the AI can repeatedly perform the following loop without losing project context:

1. inspect repository reality
2. reconcile the memory bank
3. understand the active phase/module/work unit
4. select the next valid work
5. implement a small coherent slice
6. test and verify it
7. update documentation and persistent state
8. identify newly exposed work, updates, removals, risks, or decisions
9. repeat until blocked by a genuine human decision or until the approved project objective is complete

The repository, not the conversation, is the continuity layer.