# Continuous Improvement and Maintenance Protocol

This protocol governs requirements 31–32 for **child projects created from ANPOS**. The canonical source stores inactive workflow/config blueprints; it does not run project maintenance loops against itself.

## Template boundary

Source blueprints:

- `blueprints/github/workflows/technology-update-watch.yml`
- `blueprints/github/workflows/innovation-scout.yml`

Child bootstrap installs the applicable files into the child repository's active `.github/workflows/` paths. Technology Watch remains disabled until the child has an approved technology stack. Innovation Scout remains disabled until explicit owner opt-in.

## Core rule

Discovery and recommendation may be automated. Code changes that alter the approved technology stack, dependencies, modules, options, system behavior, data model, infrastructure, or user experience require an explicit consent record before implementation unless the change is an already-approved emergency/security remediation policy.

Every approved maintenance/change cycle follows:

**Detect → Research → Compare → Impact Analysis → Plan → Supervisor Alert → Owner Consent → Isolated Implementation → Tests/QA/Security Verification → Review → Merge → State/README/Selected-PM Sync**

GitHub remains canonical for code and consent/maintenance state. The selected project-management provider mirrors approved child-project work when connected.

---

## 31 — 24-hour Technology Update Watch

### Schedule

The source blueprint is `blueprints/github/workflows/technology-update-watch.yml`. After child bootstrap it becomes `.github/workflows/technology-update-watch.yml` in the child repository. It is enabled only after the child has an approved technology stack, then runs once every 24 hours and may also be dispatched manually.

The GitHub Action is a durable scheduler/trigger, not a substitute for an AI runtime. It creates or preserves a single open Supervisor audit request. When an active Supervisor runtime is available, the Supervisor processes that request.

### What the Supervisor audits

Build a current technology inventory from child-repository reality, including where relevant:

- frontend framework/runtime
- backend framework/runtime
- language/runtime versions
- direct dependencies
- package-manager lockfiles
- database and extensions
- cache/queue/search systems
- authentication/identity libraries
- build tooling
- testing tooling
- CI/CD actions
- container/base images
- infrastructure providers/modules
- monitoring/observability tooling
- SDKs/APIs/integrations
- security tooling

Then search current authoritative sources for meaningful updates. Prefer official release notes, security advisories, vendor documentation, package registries, language/framework release channels, and primary repositories.

Do not treat every newer version as an upgrade recommendation.

For each candidate update classify:

- current version/constraint
- candidate version
- release date when available
- update type: patch / minor / major / runtime / platform / security / deprecation
- security relevance
- breaking changes
- compatibility impact
- migration requirements
- data/schema impact
- deployment impact
- performance implications
- support/EOL implications
- ecosystem readiness
- rollback strategy
- recommended action: ignore / monitor / approve soon / urgent

### Update plan before code

When one or more changes are worth adopting, create a bounded update plan before editing code. The plan must define:

- exact technologies/packages to change
- reason for change
- expected benefits
- breaking-risk assessment
- affected modules
- migration steps
- required tests
- rollout/rollback plan
- sequencing/dependencies
- estimated scope classification

Create a consent request in `config/consent/consent-requests.json` and a Supervisor alert/reference.

### Owner notification email

The Supervisor must notify the configured child-project owner contact by email when a meaningful update requires consent.

The email should contain:

- concise list of detected updates
- why each matters
- risk/severity
- affected system areas
- recommended decision
- link/reference to the full plan
- consent request ID

Preferred interactive action when the current host/email integration supports an authenticated callback:

**Approve & Start Update**

Secondary action when supported:

**Review / Reject**

A one-click button must only be used when clicking it can securely record the authorized user's consent and trigger the approved workflow. Never render a fake button that cannot safely perform the action.

Fallback when authenticated email actions are unavailable:

- link to the canonical GitHub consent/review item, and/or
- require the exact command `APPROVE UPDATE <CONSENT-ID>` from an authorized owner in the connected AI session or approved review surface.

Owner email/contact resolution is defined by `config/notifications/project-owner.json`. Never guess or scrape a private email address.

### After consent

After consent becomes `approved`:

1. Supervisor converts the update plan into one or more bounded maintenance slots.
2. Worker/Supervisor uses an isolated branch.
3. Reconcile current main and merge generation first.
4. Apply only the approved update scope.
5. Execute migration steps safely.
6. Run required static/unit/integration/E2E/regression/build/deployment/security checks.
7. Test compatibility and rollback where relevant.
8. Update architecture/docs/version inventory.
9. Submit through normal review/merge governance.
10. Update project memory, child README/runtime state, selected PM provider when connected, and maintenance state.

An approved dependency update is not complete merely because installation succeeds.

### Urgent security updates

A critical security update may be flagged `urgent`, but this protocol does not silently bypass owner authority. If an explicit emergency-remediation policy has previously been approved for the child project, follow it. Otherwise obtain expedited consent and clearly communicate exposure/risk.

---

## 32 — Optional 25-hour Market / Options / Modules Innovation Scout

### Activation consent

This loop is optional and disabled by default in both the source blueprint and newly bootstrapped child until owner approval.

Before activation, offer:

- `Enable 25-Hour Innovation Scout`
- `Keep Innovation Scout Off`

If native controls are unavailable, require the exact fallback:

`ENABLE 25-HOUR INNOVATION SCOUT`

Record the decision in the child project's `config/maintenance/innovation-scout.json`.

### Schedule semantics

The source blueprint is `blueprints/github/workflows/innovation-scout.yml`. Child bootstrap installs it as `.github/workflows/innovation-scout.yml`, but it remains inactive while `enabled` is false.

GitHub cron cannot express a true repeating 25-hour interval directly. Therefore, once explicitly enabled in a child project, the workflow runs an hourly lightweight due-check and creates a scout request only when at least 25 hours have elapsed since the last scout request and no prior scout request remains open.

This preserves the requested ~25-hour cadence without one-hour research runs or noisy repository commits.

### Scout research

When due and enabled, the Supervisor/Research AI searches the market and current technical ecosystem for useful additions such as:

- new product capabilities
- new reusable options
- new modules
- better workflows
- new integrations/APIs
- automation opportunities
- security/privacy improvements
- accessibility improvements
- performance/reliability improvements
- developer-experience improvements
- deployment/operations improvements
- newly mature technologies
- competitor/category changes
- recurring user pain points

Research must compare evidence and avoid novelty bias. A new technology or competitor feature is not automatically valuable.

### Suggestion bank

Candidate discoveries go to the Options Bank / Modules Bank as `proposed` or to an attached research artifact. They must not silently become approved scope.

For each suggestion record:

- problem/opportunity
- evidence/source summary
- affected user/system area
- proposed option/module/system
- expected value
- complexity
- dependencies
- risks
- alternatives
- market/competitive relevance
- recommendation

### User consent before building

Before creating implementation slots, present a concise set of worthwhile proposals and ask what the owner wants to add.

Preferred actions when supported:

- `Approve Selected Suggestions`
- `Review Suggestions`
- `No Changes This Cycle`
- `Disable Innovation Scout`

Do not force the user to accept all suggestions as a bundle.

Every accepted proposal receives its own consent/decision record or an explicitly scoped grouped consent record. Only approved items are promoted into the execution plan/modules bank as active development scope.

After approval, use the normal architecture/data-flow/UI/UX/security/QA and multi-agent development lifecycle appropriate to the change.

---

## Scheduled workflow limitations

GitHub Actions can schedule and create durable child-repository audit requests, but a generic template cannot assume a continuously running AI agent, connected email account, authenticated one-click email callback, connected PM provider, or access to proprietary tools.

Therefore:

- source files are inactive blueprints;
- child bootstrap installs project workflows;
- scheduled child Actions create durable due/audit requests;
- an available Supervisor AI performs the actual current research and planning;
- email is sent only through an authorized connected provider/runtime;
- PM synchronization happens only when a provider is selected/verified;
- consent is recorded only through a verifiable authorized action;
- if the Supervisor was offline, it processes overdue requests at next startup/resume;
- never claim an email, research run, PM sync, consent click, or code update occurred when the required runtime/integration was unavailable.

## Completion and reconciliation

After either maintenance loop produces an approved child-project change and it is merged:

- increment normal merge generation
- alert active Workers to reconcile main
- update technology/options/modules inventory
- close the maintenance/scout request
- update `config/consent/consent-requests.json`
- refresh child project status/README
- sync the selected PM provider when connected
- record test/security evidence

The two loops continuously improve child projects without turning automated discovery into uncontrolled scope or dependency churn.
