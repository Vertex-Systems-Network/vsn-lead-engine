# GitHub Governance and Repository Rules

GitHub governance is part of **child-project initialization and control-plane enforcement**. The canonical template source stores desired policy only; it is not evidence that the source itself has child-project Rules applied.

Machine-readable blueprint: `config/github/ruleset-policy.json`.

## Source template boundary

For `Vertex-Systems-Network/ai-native-project-operating-system`:

- Rules policy is an inactive reusable child-project blueprint;
- missing child rules on the canonical source are not child-project governance drift;
- do not silently apply child merge/ruleset settings to the source;
- `blueprints/github/workflows/governance-audit.yml` stays inactive on the source;
- the canonical source may retain only the explicit guarded vendor/source workflow allowlist: continuous certification, immutable vendor handoff, guarded commercial production deploy, guarded commercial database migration, and guarded production readiness audit; these workflows are repository-guarded, source/vendor-only, least-privilege, and stripped from customer/vendor-template outputs;
- source branch protection/rulesets, review requirements, bypass actors and required-check enforcement are repository settings maintained and verified separately from child-project policy and from CI workflow presence.

## Child setup and consent

After bootstrap, capability-aware quality setup and observation of stable real check names, present:

- **Apply Recommended GitHub Rules**
- **Review GitHub Rules**

Repository-admin writes require this project-start user decision. A policy JSON is never proof of enforcement.

If the user approves and an authenticated admin-capable GitHub interface exists:

1. inspect current child repository settings, rulesets/branch protection, bypass actors and merge methods;
2. read `config/github/ruleset-policy.json` and protected paths from `config/github/path-ownership.json`;
3. verify actual installed/successful status-check contexts and platform capabilities;
4. calculate/apply the minimal approved changes;
5. protect default branch and control-plane coordination namespaces as supported;
6. enable governance auditing when appropriate;
7. re-read GitHub settings/rulesets and compare every material desired invariant;
8. mark setup complete only after verified evidence.

If administration writes are unavailable, provide exact manual settings and keep setup `pending_user_action` until re-read verification succeeds.

## Default branch baseline

For child `main`/default branch, intended baseline is:

- pull request required before merge;
- at least one approving review;
- stale approvals dismissed after new pushes;
- most recent reviewable push approved by someone other than its author where supported;
- conversations resolved;
- applicable observed required checks passing;
- branch up to date where required by chosen merge strategy;
- force pushes blocked;
- branch deletion blocked/restricted;
- linear history;
- **CODEOWNER review required for protected paths**;
- high-risk/security-critical Supervisor self-authored work independently reviewed;
- bypass permissions minimized and explicitly documented.

Protected control-plane paths include AI instructions/router/adapters, orchestration/coordination, protocol/security/consent/governance/quality/release policy, validators/schemas/scripts, workflows/blueprints and other paths listed by `config/github/path-ownership.json`.

## Coordination ref namespaces

`claims/**` and `supervisor/**` refs are distributed coordination infrastructure, not normal feature branches.

Where GitHub plan/ruleset capability supports it, restrict create/update/delete for these namespaces to the trusted orchestrator/Supervisor runtime identity. Normal Workers must not be able to manufacture or delete coordination authority.

Where GitHub cannot enforce namespace actor restrictions, the child runtime must provide an equivalent authenticated gateway, least-privilege token separation and audited mutation/recovery. Lack of platform enforcement is recorded as a residual control, not silently ignored.

## Required-check policy is capability-aware

Never hard-code a check as required merely because a blueprint exists.

Potential checks include:

- `AI Native Quality Gates / repository-integrity`;
- Dependency Review when supported/installed;
- CodeQL when supported/installed;
- stack-specific test/build/security/design/accessibility/migration checks after technology approval.

Before making a check required:

1. verify the workflow/feature is actually supported and enabled in that child;
2. observe the exact stable context name on a successful run;
3. ensure the check does not require unavailable billing/licensing/permissions;
4. then add it to the enforced ruleset.

If a platform security feature is unavailable, use an appropriate alternative where possible and record the unavailable control. Do not create a permanently red branch-protection configuration.

## Trusted CI and control-plane changes

Workflow/validator changes cannot be their own sole trust anchor. Protected-path changes require CODEOWNER/independent review. The repository-quality blueprint runs the proposed validator and, on PRs, the protected base revision's validator against the proposed tree where possible, plus control-plane conformance tests.

Any change that weakens governance/quality/security must be treated as a control-plane change and reviewed according to risk.

## Merge policy

For multi-agent child work, prefer squash merging into `main`:

- squash merge enabled;
- merge commits disabled;
- rebase merge disabled by default for the ANPOS model;
- auto-merge enabled when supported and desired;
- update-branch enabled when supported;
- delete merged feature branches when safe;
- merge queue recommended when available/practical for concurrent Workers.

Merge policy must not delete protected coordination refs or destroy evidence needed for stale-claim recovery.

## Identity and token separation

GitHub permissions should follow least privilege:

- Worker credentials: feature branch/review scope only as needed, no repository-admin or coordination-namespace authority by default;
- Supervisor/orchestrator: only permissions required for coordination/review/merge/governance operations;
- deployment identity: environment-scoped, short-lived/OIDC where supported;
- security scanners: minimal read/write permissions required for their outputs.

Never reuse a broad personal token as the universal Worker/Supervisor/deployment identity when a narrower mechanism exists.

## Drift monitoring

`blueprints/github/workflows/governance-audit.yml` is a child blueprint enabled after Rules setup. It reports observed drift but does not silently use `GITHUB_TOKEN` as a repository-administration credential.

A drift audit should compare the material desired policy, not merely check that *some* ruleset exists. Unsupported/unobservable settings must be reported as unknown rather than assumed compliant.

## Verification rule

Governance is `verified` only after authenticated re-read of the child repository demonstrates the applicable policy. Config files, screenshots, AI statements or PM status alone are insufficient evidence.
