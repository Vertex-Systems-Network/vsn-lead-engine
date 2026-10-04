# AI-Native Code Quality System

Code quality is a merge gate and planning concern for **child projects created from this template**. The canonical source stores policy and inactive blueprints; it does not represent child checks as already applied.

Machine policy: `config/quality/quality-policy.json`.

## Source template boundary

- `blueprints/github/` contains inactive reusable files.
- Source presence is not evidence a live check exists.
- Child workflows are activated only by child initialization/capability setup.

## Capability-aware child baseline — Requirements 57–58

Child bootstrap always installs the universally safe **AI Native Quality Gates** plus the non-privileged runtime/update blueprints and Dependabot seed configuration.

Before enabling GitHub-hosted security features such as CodeQL, Dependency Review or Scorecard, inspect the actual child repository visibility, plan/features, permissions and support. Use `scripts/install_quality_capabilities.py` only after capability is known. If a feature is unavailable, record it as unavailable/deferred and use an appropriate local/open alternative where useful rather than knowingly starting the project with red CI.

The AI must verify actual successful child check names before using them in GitHub Rules.

Installed workflows must have minimum explicit permissions for their configured behavior. For example, a workflow must not request PR commenting while lacking the required permission; disable nonessential writes instead of escalating privileges by default.

## Formal machine-state validation — Requirement 60

ANPOS uses JSON Schema Draft 2020-12 validation through the pinned dependency in `requirements-anpos.txt`.

- every `config/**/*.json` / routed machine config receives the base schema;
- security/coordination-critical state also receives specialized schemas;
- handwritten integrity checks supplement schemas rather than replace them.

## Stack-adaptive quality — Requirement 59

After `Approve Technology Stack`, automatically select mature ecosystem-standard tooling for the actual child project and configure CI before normal feature work scales.

At minimum where supported:

- deterministic formatting;
- linting;
- type/static analysis;
- unit tests;
- integration tests;
- build/package verification;
- dependency vulnerability audit;
- security scanning.

When relevant also add contract/API, E2E, accessibility, visual regression, performance/load, migration, container, IaC, license, coverage, SBOM and provenance/attestation checks.

Run `scripts/configure_dependabot.py` or equivalent after the actual stack/manifests exist so dependency updates cover the project's package ecosystems/directories, not only GitHub Actions.

## Trusted control-plane verification — Requirement 51

A PR must not be able to weaken its own validator unnoticed. The repository-quality blueprint:

1. runs the current validator;
2. on PRs, runs the **protected base revision's validator** against the proposed tree;
3. runs control-plane conformance tests;
4. reports control-plane file changes for CODEOWNER/independent review.

Protected-path GitHub Rules/CODEOWNERS remain necessary because a workflow file itself is code and cannot be its own sole trust anchor.

## Supply chain and release evidence — Requirements 62–63

- pin third-party GitHub Actions to full commit SHAs;
- use short-lived/OIDC deployment identity where supported;
- keep privileged credentials away from untrusted PR execution;
- enable secret scanning/push protection where supported;
- production artifacts should link SBOM, source commit, artifact digest and build provenance/attestation when supported.

See `PRODUCTION-ASSURANCE.md` and `config/release/release-policy.json`.

## Tool selection criteria

Compare ecosystem fit, maintenance/release health, false-positive profile, CI performance, autofix support, machine-readable/SARIF output, editor integration, monorepo support, security track record, license/cost and supported runtime compatibility.

Normal non-destructive quality tooling does not need another generic consent prompt. Paid services, secrets, repository-admin changes, destructive migrations or material commitments still require applicable access/consent.

## AI review layer

AI review services may complement deterministic gates when actually available. They never replace lint/tests/security gates, protected-base validation, or independent review for high-risk/control-plane changes.

## Definition of done

A module/work unit is not complete because code exists. Required supported checks must pass, behavior must have relevant tests, critical/high security findings must be resolved or handled under authorized risk policy, applicable design/accessibility/migration/release evidence must exist, documentation/state must agree with repository reality, and Supervisor integration acceptance must be recorded.
