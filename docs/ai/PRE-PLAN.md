# AI-Native Pre-Plan — Lead Engine SaaS Direction

Planning snapshot: 2026-10-05 PKT  
Repository baseline: `ba7a8bcc224f429d5ab85d8cff076a3c9eccffa2`  
Blueprint: ANPOS 1.4.0 child project  
State: discovery/pre-plan; no new SaaS implementation or stack approval.

## 1. Product Objective
Evolve VSN's lead-generation capability into a multi-tenant subscription product that helps a user define a target market, discover and manage business leads through permitted sources, schedule repeatable jobs, filter/export results, and understand source/usage costs. Provide coherent web, desktop, and mobile experiences over shared account, job, and data contracts. Product success is improved time-to-first-useful-lead and reliable, transparent, compliant job execution—not a guaranteed lead count.

## 2. Scope

### In scope
- User/account/workspace model, authentication, roles, subscription entitlements, usage limits and lifecycle.
- Search configuration: countries/regions, supported business status, niches/categories, fields and filters.
- Free, paid, BYOK and custom-source options as separately governed adapters, only after licensing/cost review.
- Manual and scheduled collection, per-user timezone, DST, durable jobs, retries, idempotency, pause/cancel, notifications and history.
- Lead normalization, provenance, confidence/validation, deduplication, filtering, exports and retention/deletion.
- Admin control plane for tenants, plans/entitlements, adapters/credentials references, budgets, jobs, abuse controls, incidents and audit.
- AI assistance with bounded tools, user-visible provider/model/cost, evaluation, output provenance and explicit approval before paid actions.
- Responsive web product, marketing/landing site, then desktop and mobile clients using versioned shared APIs.

### Out of scope for this planning milestone
- Replacing or interrupting the existing daily production lead pipeline.
- Guaranteeing any quota, provider coverage, email/phone accuracy, or source uptime.
- Collecting from sources whose terms/rights do not permit the intended use; bypassing access controls or anti-bot protections.
- Final vendor, architecture, stack, cloud, payment gateway, price, store listing, or legal conclusion.
- Sending marketing outreach on behalf of users; this needs separate consent, deliverability, and jurisdiction review.
- Autonomous AI spending, provider-key disclosure, or unrestricted scraping/code execution.

## 3. Current Repository Reality
- Existing ANPOS 1.4.0 child; current production operations phase remains active.
- Current implementation is a Python lead engine oriented to US + Canada, Overture free discovery, phone-required accepted records, R2 packed fingerprint dedupe and dated Google Sheets.
- Latest persisted snapshot before this planning request recorded 6,855/12,000 for 2026-10-04 and shortfall 5,145; this is historical evidence only, not today's status. Re-read live runtime/workbook before operational claims.
- P01–P70 and production controls are historical/current baseline and are not reset.
- SaaS foundation (auth/tenancy/billing/user schedules/client apps) is not implemented in the audited repository tree. The detailed read-only component/reuse/gap map is in `docs/ai/LEAD-SAAS-CURRENT-ENGINE-AUDIT.md`.
- Repository write plan is documentation/planning only. New product implementation must wait for research, system design, technology consent, and repo-boundary decision.

## 4. Primary Actors and Workflows
1. Visitor reviews product/source/cost explanations, creates an account, and selects a plan.
2. User creates workspace, selects supported countries/regions, status, niche and fields, selects an eligible source mode, sees estimated limits/cost, then saves or runs a search.
3. User configures a daily schedule in an explicit timezone; system shows next run, handles DST, prevents overlapping duplicates, reports queued/running/partial/completed/failed/paused states, and permits edit/pause/cancel.
4. User filters/sorts/searches leads, inspects source/provenance and data freshness, exports within entitlement, and requests deletion.
5. Admin safely configures provider adapters and limits, monitors job queues/costs/failures/abuse, changes entitlements through audited workflows, and responds to data/security requests.
6. AI helper translates plain-language intent into a reviewable search configuration, explains filters/source coverage, and summarizes selected records. User confirms before execution, paid usage, or externally consequential action.

## 5. Validated Requirements vs Assumptions
Validated from current user instruction: multi-client product, subscriptions/login, country/status/category selection, user-time daily jobs, free/paid/custom source choices, admin integrations, AI assistance, broad filtering, feature-rich visual landing site.
Assumptions: organizations/seats, Windows-first desktop, Android+iOS app, user-selectable source fields and custom fields, BYOK, email/phone policy, exact schedule semantics, in-product payment by platform. These remain unresolved.
Market-driven candidates: source/field provenance, cost preview, run history, retry/pause controls, data export, retention/deletion controls, audit, accessibility, per-tenant rate limits, clear partial-result status.

## 6. Market and Comparable-System Findings
- Apollo's public product materials combine prospecting, contact data/credits, sequences, analytics and AI. Lesson: users may compare against a broader workflow; differentiation must be explicit. This plan does not include outbound campaigns in MVP.
- Clay publicly promotes multi-provider enrichment and waterfalling. Lesson: provider ordering, field-level provenance, confidence, and spend preview can be differentiators.
- Hunter publicly provides email discovery/verification, API and credit-based plans. Lesson: focused, measurable adapters can be integrated without promising uniform fields from all providers.
- Google Places policy restricts storage/caching of content except defined exceptions such as Place IDs; this demonstrates why each provider needs its own policy and storage contract.
- Google Maps Platform bills by service/SKU and usage; a single generic “paid” setting is insufficient.
- Source feasibility matrix records Overture's mixed source licenses and optional fields, OSM ODbL and shared Overpass limits, Google Places storage and SKU cost constraints, Apollo resale-contract uncertainty, Hunter's email-focused credits/API limits, and Clay's credit/action comparator. No provider is approved or selected; see `docs/ai/LEAD-SAAS-SOURCE-FEASIBILITY.md` and EVID-000011–000016.
- Apple in-app subscriptions and Microsoft Store commerce have platform-specific rules. Cross-platform entitlement sync and storefront-specific checkout must be designed after distribution decision.
Evidence URLs, dates, evidence class and limitations are in `config/research/evidence-registry.json`. Findings are initial desk research, not legal advice, independently verified user findings, or current full-price comparison.

### Positioning hypothesis
“Transparent, source-aware lead discovery and scheduled workflows that let smaller teams choose free, provider-funded, or bring-your-own data services with visible limits and control.” Validate this against user interviews and actual permitted provider coverage/cost before adopting as public positioning.

## 7. Recommended MVP and Simplifications
Recommended first release: responsive web app; one market (US + Canada is incumbent scope, not proven SaaS priority); a small number of source adapters cleared for data rights; manual run + daily scheduling; workspace isolation; plan/usage enforcement; lead provenance, dedupe, filter/export; basic admin; job health; no outbound sending. AI initially assists configuration/explanation with human confirmation, not autonomous enrichment spending.
Keep desktop/mobile clients after the shared API and web workflows are stable. Build landing-site information architecture/content during product design; polish/animation follows the approved design system. Treat “every filter/any custom provider” as extensibility goals, not MVP commitments.

## 8. Constraints, Risks and Dependencies
- Data-provider terms, country-specific privacy/marketing rules, licensing, storage, resale and attribution are source-specific; qualified review required.
- Multi-tenant authorization defects can expose customer leads/keys; tenant isolation is a P0 architecture/test gate.
- Paid-provider spend and AI costs can exceed subscription revenue; per-tenant hard budgets, estimates and circuit breakers required.
- Free-source yield varies; never promise targets or silently use a paid fallback.
- Schedules must survive DST, retries, app deploys, duplicate events and worker outages.
- Credentials must be encrypted and scoped; never expose provider keys to clients, logs, AI memory, or other tenants.
- Provider-specific retention/deletion restrictions must propagate to user exports, derived data and backups.
- App store billing and desktop code signing/release may add external costs and account gates.
- Existing daily operations consume shared repository/maintainer capacity and must not regress.
- Depend on vendor APIs/terms, payment availability for Pakistan-based VSN, source coverage, GitHub/Cloudflare/Google controls, design/user research and qualified compliance review.

## 9. Technology Decisions
No stack approved.
Candidate architecture for evaluation: shared versioned API, relational system of record with tenant-scoped authorization, durable queue/scheduler, object storage only for suitable artifacts, provider adapter interfaces, web-first frontend, desktop/mobile clients later. Compare options for current team skills, cost at idle/scale, free-tier limits, queue durability, database isolation, secrets/OIDC, observability, vendor lock-in, deployment and migration burden.
`Approve Technology Stack` remains a required ANPOS gate after system design. No paid infrastructure/API should be enabled without cost and account authorization.

## 10. Proposed Options and Modules
Canonical option IDs are in `config/ai/options-bank.json`; module IDs, boundaries, dependencies and acceptance gates are in `config/ai/modules-bank.json`.
Core proposed modules: product discovery; identity/workspaces/tenant security; plans/entitlements/usage; source catalog/adapters; search configuration; durable scheduling/job orchestration; lead pipeline/provenance/dedupe/storage; filtering/export; admin operations/audit; AI assistant/evaluation; web UX; desktop client; mobile client; marketing site; production assurance.
Legacy production runtime, ANPOS governance, My Drive autonomy and assurance modules remain tracked independently.

## 11. Phase / Milestone Strategy
- P0 Discovery and validation: current implementation boundary, user/job research, competitors, source/legal/cost evidence, launch market and MVP.
- P1 System design: actors, API/module boundaries, tenant threat model, data flows, lifecycle/retention, scheduling semantics, UX flows and success measures.
- P2 Technology selection and explicit owner consent; decide same vs dedicated implementation repository.
- P3 SaaS foundation: auth/workspaces/RBAC, tenant isolation, entitlements and usage meter.
- P4 Collection platform: provider policy registry, first permitted adapters, durable schedule/queue, normalization/provenance/dedupe.
- P5 User workflows: search setup, job controls/history, lead management/filter/export, notifications.
- P6 Admin and AI: adapter controls, audit/abuse/cost admin, evaluated AI assistant with bounded actions.
- P7 Web/marketing release: responsive product, accessibility, landing feature sections and analytics.
- P8 Desktop then mobile clients, only after stable API and billing/distribution decisions.
- P9 staged launch: threat/security/privacy review, load/failure tests, SLO/runbooks/backups/restore, migration/rollback, progressive rollout and production evidence.
Detailed work units, status, dependencies and gates are in `config/ai/execution-plan.json`. Existing daily quota work remains concurrent.

## 12. Critical Path
Research provider legality/coverage/cost + target users → select MVP and product boundary → system/data/threat design → approve stack + budget → tenant identity/entitlement foundation → source/scheduler/lead pipeline → web workflow acceptance → security/privacy/load/restore evidence → staged launch. Client apps depend on stable API and platform billing/distribution decisions.

## 13. QA Strategy
- Contract/schema tests for provider adapters, field provenance, plan limits, jobs and API versioning.
- Tenant isolation tests (horizontal and vertical access, exports, queues, caches, AI context, credentials).
- Scheduler tests for timezone/DST, duplicate event delivery, overlap policy, retries/backoff, pause/cancel and missed runs.
- Source-policy tests: no adapter activates without allowlisted use/storage/attribution/cost metadata and kill switch.
- Pipeline accuracy/coverage evaluations with labeled/synthetic fixtures; duplicate, stale, missing and conflicting fields.
- Cost/usage limits, race conditions, rate limiting, abuse, queue fairness and failure injection.
- Accessibility WCAG 2.2 AA, responsive/mobile layouts, keyboard/focus, reduced motion and screen-reader checks.
- AI evaluation by task, hallucination/source attribution, prompt injection, tenant boundary, unsafe action and spend caps.
- Browser E2E, desktop packaging/signature verification, mobile store sandbox tests only when those clients are in scope.
- Staging parity, migration/rollback, backup restore, incident drills and post-deploy verification.

## 14. Security, Privacy and Responsible AI
Threat-model tenant boundary, authentication/session theft, provider-secret compromise, webhook forgery/replay, job abuse/DoS, scraping-policy violations, export leakage, prompt injection and admin privilege misuse. Apply least privilege, tenant-scoped authorization at every query/job/export, encrypted provider credentials, scoped OAuth where possible, signed/idempotent webhook handling, secret-free telemetry, rate/cost budgets, audit, retention/deletion, access review and incident response. AI sees only authorized minimal context, treats external lead text as untrusted, cites provider provenance, supports human review/correction, and cannot execute paid/provider actions without explicit user confirmation. No legal applicability is marked passed without qualified review.

## 15. Deployment / Operations
Isolate dev/staging/prod credentials and data. Use managed durable queue/scheduler and DB only after cost/plan approval; do not base customer schedules on ephemeral GitHub Actions cron. Define queue SLO/latency, success and partial-result metrics, per-provider health/circuit breakers, cost alarms, tenant quotas, support/runbooks, backups and restore targets, migrations expand→migrate→verify→contract, signed desktop release and store review. Roll out behind tenant/feature controls; maintain stop/rollback path.

## 16. Unresolved Human Decisions
1. Product boundary: evolve this repository/runtime or create a separate SaaS application repository before code work.
2. Launch market/countries/niches and first user segment.
3. Provider model: platform-funded, BYOK, or both; first source providers.
4. MVP field policy and phone/email requirements.
5. Subscription plans, trial, quotas, overage behavior, payment provider and billing currency.
6. Windows/macOS/Linux desktop and Android/iOS storefront scope/order.
7. Hosting/API/AI budget ceiling and acceptable ongoing monthly spend.
8. User research contacts and success targets.
These decisions do not block documentation/research. Technology approval and external paid/production changes remain gated.

## 17. Execution Readiness
- [x] User overview captured and normalized without converting assumptions to facts.
- [x] Existing repo/production boundary reconciled from current repository state.
- [x] Initial official-source/competitor desk research recorded with provenance.
- [x] Phased candidate plan, proposed options/modules, work units and risks prepared.
- [ ] User/job validation and deeper competitor/source-policy research.
- [ ] Product boundary, launch market, source model, billing, platform and budget decisions.
- [ ] System/data/threat/UX design and architecture records.
- [ ] Technology alternatives evaluated and owner approval recorded.
- [ ] Implementation acceptance criteria refined with approved MVP.
- [ ] SaaS implementation started.
