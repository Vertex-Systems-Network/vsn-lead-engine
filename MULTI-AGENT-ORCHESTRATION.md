# Multi-Agent Orchestration and Control Plane

This protocol governs multi-agent execution after a child project has a validated plan and executable module graph.

## 1. Canonical systems

- GitHub/repository state is authoritative for code, branches, commits, PR/MR state, merges, tests, repository-backed memory, agent slots, alerts, merge-generation state, and release evidence.
- The selected project-management provider is the planning/progress collaboration mirror for phases, modules, assignments, blockers, review state, progress summaries, and Supervisor status.
- If the PM provider disagrees with GitHub about code, review, merge, or verified-completion reality, GitHub wins and the PM provider must be reconciled.

Use `PROJECT-MANAGEMENT.md` and `config/integrations/project-management.json`. Linear is one recommended adapter, not a hard dependency.

## 2. PM planning and synchronization

When a PM provider is selected and verified, mirror the approved Project → Phase/Milestone → Module → Work Unit plan using the provider adapter contract.

During active development the Supervisor reconciles repository ↔ PM provider:

- at startup/resume;
- at least once per hour only while a persistent Supervisor runtime actually exists;
- immediately after material events such as claim, reassignment, blocker, review submission, requested changes, merge, module completion, phase completion, release change, or plan revision.

If the provider or host is unavailable, record degraded state and catch up later. Never pretend a background sync occurred.

## 3. Development AI selection

Development-AI selection occurs during child initialization and can be revised later.

Use `config/ai/agent-catalog.json`.

Discover which development agents/tools are actually available or attachable in the current host and present only usable choices under **Choose Development AI**. Examples may include Codex/ChatGPT, Claude Code, GitHub Copilot, Gemini, Cursor, Windsurf, or other compatible agents.

Unavailable suggestions may be shown separately, never as active controls implying integration exists.

Allow one or more verified agent types when the host supports a pool. Record the selected pool and role assignments. A typical setup may use one selected capable agent as Supervisor and one or more selected capable agents as Workers.

## 4. Multi-agent operating model

There must be exactly one active **Supervisor** for a coordination epoch.

The Supervisor:

- owns whole-project coordination;
- maintains the queue and dependency graph;
- assigns/opens module slots;
- detects conflicting/shared writes;
- reviews Worker submissions;
- controls merge order;
- reconciles the selected PM provider;
- maintains README status;
- emits and closes repository-backed alerts;
- may also execute one bounded development module/work unit when coordination load permits.

Workers:

- work only on claimed eligible slots;
- use isolated branches;
- keep scope bounded to the assigned module/work unit;
- continuously reconcile with current main, merge generation, and open required-action alerts;
- submit PR/MR for Supervisor review.

## 5. Worker zero-question entry

A new Worker should need only the child repository URL plus a request to start/continue development.

The Worker must:

1. read `AGENTS.md`, `AUTO-AGENT.md`, `AI-NATIVE-EXECUTION.md`, and this file;
2. fetch/reconcile current `main`;
3. inspect `config/coordination/agent-work-queue.json`;
4. inspect `config/coordination/supervisor-state.json`;
5. inspect `config/coordination/agent-alerts.json`;
6. inspect current merge generation;
7. satisfy/acknowledge applicable required-action alerts before new substantive work;
8. claim the highest-priority dependency-satisfied free slot allowed for its role/capabilities using the atomic claim protocol;
9. mirror/update assignment in the selected PM provider when connected and permitted;
10. begin work without asking the user which module to choose unless repository evidence contains a genuine unresolved decision.

Repository-backed queue and alert state are the deterministic assignment/notification mechanisms. Direct messaging to external AI chats is optional.

## 6. Slot and branch isolation

Every executable slot has a stable ID, module ID, priority, dependencies, eligibility, deterministic claim reference/branch, status, claimant, base SHA, review reference, and PM reference when available.

Recommended work branch shape:

`agent/<slot-id>/<sanitized-module-name>`

A slot is claimable only when dependencies are satisfied and no valid active claim exists.

Shared coordination files are normally Supervisor-owned. Workers should avoid shared-state writes except through explicitly allowed claim/heartbeat/submission/alert-acknowledgement fields.

## 7. Worker completion and review handoff

When a Worker has completed its bounded scope and all required checks pass, it must:

- synchronize against required current main according to merge-generation and alert rules;
- push its branch;
- open/update the PR/MR;
- update queue and PM review state when permitted;
- send the exact completion state:

**ALL DONE SUBMITTED FOR REVIEW AND MERGE**

The work is not merged merely because this message exists.

## 8. Supervisor review and merge

The Supervisor independently inspects the PR/MR, changed files, tests, architecture fit, security/quality impact, shared-state conflicts, and current main.

If defects exist, request targeted changes or make bounded corrective changes where authorized and safe, then rerun relevant verification.

Merge only when acceptance gates pass and merge order is safe.

When the Supervisor authored the submitted change itself, its authorship is not independent approval. Require an independent eligible reviewer/agent where available. High-risk/security-critical self-authored changes require an independent human or separate authorized reviewer before merge.

After merge, update the connected PM provider only from verified repository reality.

## 9. Merge-generation alert and acknowledgement protocol

Every successful merge to `main` must:

1. increment `merge_generation` in `config/coordination/supervisor-state.json`;
2. append a merge event to `config/coordination/merge-events.json`;
3. append a required-action alert to `config/coordination/agent-alerts.json` for affected active Workers;
4. mirror the reconcile requirement in the selected PM provider when useful.

Before a Worker starts/resumes substantive implementation, before a substantial continuation, and before final submission, it compares its acknowledged generation to the current generation and inspects applicable open alerts.

If main advanced, the Worker fetches/integrates current main, resolves conflicts, reruns impacted tests, acknowledges the new generation with evidence, then continues.

The Supervisor closes an alert only after intended recipients acknowledge it, their slots end/cancel, or the alert is superseded.

## 10. Optional Figma/design intake

Before detailed UI/UX execution, offer:

- text/URL box: **Figma / Existing Design Link**
- primary action: `Add Figma Design`
- secondary action: `Skip Design Link`

If an accessible design is supplied, audit it against validated requirements, flows, architecture, responsive/accessibility needs, and the approved design system. If no design exists or the user skips, create the UI/UX professionally from validated requirements.

Record design source/audit state in `config/design/design-intake.json`.

## 11. README live development dashboard

The child project's main-branch README is the human-readable control surface.

It should include where relevant:

- overall project progress;
- selected PM provider + sync state;
- selected Supervisor/Worker AI pool;
- phases/modules/work units;
- description/owner/status/progress;
- blockers/dependencies;
- start/target dates;
- PR/MR/review state;
- merge generation;
- open required-action alert count;
- last repository-visible update;
- last PM-provider sync.

Refresh after repository-visible state transitions and supported heartbeat intervals. Do not create literal one-second Git commits.

## 12. Failure and degraded modes

- If the selected PM provider is unavailable/quota-limited, use repository state and provider documents/status surfaces where possible; do not block development unnecessarily.
- If no PM provider is selected, repository-backed planning is sufficient.
- If direct cross-agent messaging is unavailable, queue state + agent alerts + merge generation + optional PM mirror are the communication layer.
- If only one development AI is available, it may act in separated Supervisor/Worker passes while preserving role and review safeguards.
- If Figma cannot be accessed, design from requirements unless an export is genuinely needed.

## 13. Provider switching

If the owner switches PM providers, reconcile GitHub first, connect/verify the replacement, rebuild active plan/task/review state from repository truth, verify counts/mappings, then disable old sync. Never migrate by trusting stale PM state over GitHub.

## 14. Completion discipline

Supervisor coordination is not complete until queue state, GitHub merge reality, alert acknowledgements, selected PM mirror when connected, project memory, and README dashboard agree.
