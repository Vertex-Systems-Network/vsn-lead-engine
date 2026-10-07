# Project Idea

## Intake Status
`RECEIVED — NORMALIZED — RESEARCH IN PROGRESS`

## Raw User Input
> I want a system with web, desktop, and app versions. Users subscribe, log in, select countries, business status and niche/category, and configure daily lead collection at a chosen time. The system should collect leads from free services, while the admin side can integrate paid services too. Users should be able to choose free or paid options, add custom options, use AI help, and filter data with every useful option. The product also needs a landing page explaining every feature with images, strong visuals, and animations. This was a rough description and should be organized into a proper step-by-step plan using the AI-Native blueprint already in this repository.

## Normalized Understanding

### Explicit product requirements
- Deliver a subscription product usable through web, desktop, and mobile applications.
- Let users create accounts, sign in, and access features according to an active subscription/entitlement.
- Let users configure country/region, business status, niche/category, filters, and scheduled collection time.
- Run repeatable daily lead jobs at the user's configured local time, with job status/history and controls.
- Support free-source and paid-source choices, plus custom integrations/options where technically and contractually valid.
- Provide administrative controls for integrations, users, subscriptions/entitlements, jobs, limits, and usage.
- Provide AI assistance for configuring searches and working with lead data.
- Provide useful lead filtering and export/data handling.
- Build a public landing site with feature imagery, explanations, polished visuals, and motion.

### Repository facts
- Target repository: `Vertex-Systems-Network/vsn-lead-engine`.
- It is an active ANPOS 1.4.0 child project with a production US/Canada lead pipeline.
- Existing product invariants include Overture as the primary free discovery source, phone-qualified accepted leads, exact cross-day R2 deduplication, dated Google Sheets output, and a 12,000/day target that is explicitly not guaranteed.
- Current operational work is daily quota monitoring/recovery. It must continue independently and must not be declared complete by this product plan.
- Existing historical P01–P70 engineering work must not be replayed.
- This intake does not approve a technology stack, provider, paid plan, pricing, external integration, or production launch.

### Assumptions requiring validation
- “App” means Android and iOS mobile apps; “desktop” means at least Windows. macOS/Linux support is undecided.
- Users may be individuals and organizations/teams; roles and seat model need validation.
- “Business status” means a configurable status/type filter (for example active, closed, opening soon) only where a source can support it reliably.
- Users expect scheduled jobs to be durable across deploys, time-zone/DST changes, retries, and missed executions.
- Users may bring provider credentials (BYOK) or consume platform-managed provider credits; the preference and commercial implications are undecided.
- “Custom option” means extensible filters/source adapters/custom fields where permitted, not arbitrary executable code or a guarantee that any website can be scraped.
- AI can assist with setup, query translation, classification, summaries, and filters; it must not silently spend paid credits, bypass source rules, or make unsupported claims about lead accuracy.
- The current repository is the requested planning target. Whether the eventual SaaS implementation remains in this production runtime repository or moves to a dedicated application repository is unresolved and must be decided before application code changes.

### Constraints and guardrails
- Existing production lead collection, R2 dedupe authority, current free-source mode, secrets, and quotas remain untouched during planning.
- Publicly reachable data is not automatically licensed for collection, resale, long-term storage, or cross-customer redistribution.
- Each source adapter needs an evidence-backed use/storage/retention/attribution/cost/rate-limit policy before activation.
- No login-wall, paywall, CAPTCHA, rate-limit, robots, or access-control bypass.
- Tenant isolation, least privilege, consent, source-level spend caps, per-user quotas, auditability, retention/deletion, and safe retries are release-critical.
- Do not promise that free sources can meet a chosen volume or coverage target.
- Web defaults to WCAG 2.2 AA under the adopted ANPOS policy; cross-platform UX requires platform-specific review.

### Competitor and market notes (initial; not exhaustive)
- Apollo publicly presents prospecting, contact-data credits, sequences, analytics, and AI assistance as an integrated outbound product. This validates users' expectation for more than raw lead collection, but does not prove its private implementation details.
- Clay publicly describes enrichment from many providers and waterfall selection; this suggests source transparency, field-level provenance, and cost-aware provider ordering are useful product expectations.
- Hunter publicly offers email discovery, verification, API access, and credit-based plans; it shows a focused provider can be one adapter rather than the whole product.
- These public descriptions are vendor claims. Independent user research, detailed competitor workflow review, current pricing comparison, and geographic/source coverage verification remain planned.

### Open questions
- Initial countries, launch language(s), and first niches/categories.
- MVP required fields and whether phone is mandatory for every user or varies by workflow.
- Subscription tiers, quotas, trial, seats, overages, refunds, and billing currency.
- First permitted free and paid providers; platform-funded credits versus BYOK versus both.
- Target app stores and whether mobile purchase/entitlement must use store billing.
- Desktop target operating systems and signing/distribution route.
- Product/repository boundary and hosting budget.
- User research participants, core jobs-to-be-done, and measurable MVP success criteria.

### Research status
`INITIAL RESEARCH RECORDED — DEEP SOURCE/COMPETITOR VALIDATION PENDING`

Primary references are recorded in `config/research/evidence-registry.json`. Source legal terms, provider prices, app-store rules, user needs, and competitor behavior must be rechecked before implementation and launch.

### Planning status
`DISCOVERY AND PRE-PLAN DRAFTED — TECHNOLOGY/PRODUCT DECISIONS PENDING`
