# SaaS MVP Decision Brief

Snapshot: 2026-10-05 PKT  
ANPOS work unit: WU-SAAS-MVP-DECISIONS  
Status: **proposed recommendations only — no owner decisions accepted**  
Prerequisites: WU-SAAS-USER-MARKET-RESEARCH remains active; source qualification and cost evidence remain conditional.

This brief turns current evidence and the user's stated product direction into concrete options for review. Recommendations are reversible planning guidance, not approved implementation scope, vendor choice, price, legal assessment or technology consent.

## Proposed decision table

| Decision area | Proposed starting point | Why this is the current recommendation | Still required before acceptance |
|---|---|---|---|
| Product boundary | Create a dedicated SaaS application repository before application code; retain vsn-lead-engine as the operating production pipeline/reference until any extraction has parity evidence | The current repo is a production CLI/workflow with daily operations and has no SaaS tenant/API/client foundation. This reduces accidental coupling with daily operations. | Owner confirms repository direction; map whether existing ingestion logic may be called as a service or extracted later; define migration/ownership evidence. |
| Release sequence | Responsive web MVP first; design shared API contracts so desktop/mobile can follow | Web is the quickest surface to validate workflows; desktop/mobile were explicitly requested but OS/storefront and billing decisions are open. | User interviews confirm web-first delivery is acceptable; choose OS/storefront order later. |
| First market | Use current US/Canada engine coverage only as a benchmark for small-sample validation, not as an approved commercial launch market | It is the only evidenced incumbent geography in this repo. Existing coverage does not prove demand or sufficient rights-eligible yield. | Interview target users; choose country/niche order; run measured source sample and qualified review. |
| Discovery vs contacts | MVP hypothesis: business/place discovery with contact fields only where source-supported and allowed; treat named-person prospecting and email verification as separate optional jobs | Apollo and Hunter workflows emphasize people/contact discovery and outreach, while existing engine is place/business discovery. Combining those jobs would obscure rights, coverage and cost. | Interviews decide whether users need business records, named people, verified email, phone, or staged enrichment. |
| Free / paid / BYOK | Free eligible source as default; paid provider disabled unless admin enables it, user opts in per search/run and confirms estimated spend plus a hard cap; BYOK is a separate mode and never overrides provider terms | Avoids silent spend and handles provider/tenant budgets; public research has no qualified provider agreement or VSN wholesale economics. | Select source model, payment model, opt-in semantics, budgets and provider terms after legal/market review. |
| First data input | Permit schema-validated CSV import as the first custom-data path; later support only named, allowlisted/documented connectors; no arbitrary scraper or user executable adapter | Supports a custom option without unbounded SSRF, policy, schema and support exposure. | User demand and connector targets; file retention/deletion rules; security review. |
| Source candidate | Qualify Overture as a batch-source pilot candidate only; preserve per-record upstream source/license provenance and reject/quarantine records without eligible policy metadata | It is the strongest currently documented open batch candidate, but it has mixed source licensing and optional fields. It is not selected or approved. | License-aware prototype, country/niche yield test, storage/display/export rights review and written/qualified sign-off. |
| Jobs and schedules | Manual preview/run first, then daily user-timezone schedule with explicit next-run preview, pause/edit, idempotency and cost/source cap | Directly matches the stated daily schedule requirement and makes control observable before unattended execution. | Interview frequency and missed-run tolerance; durable scheduler design and costed hosting decision. |
| AI | Bounded assistant may draft a search/filter configuration and explain source coverage; user reviews before a job is saved or run; no autonomous paid source usage | Useful assistance while keeping spend and external actions under user control. | Decide acceptable AI tasks/model/data, budget, retention, eval set and explicit confirmation UX. |
| Plans / price / payment | Defer price, quotas and gateway; validate willingness-to-pay and unit economics using interviews and source-cost benchmarks; build entitlements independently of a chosen gateway | Public competitor retail plans cannot stand in for VSN source rights, API wholesale price, hosting/AI costs or Pakistan payment eligibility. | Owner chooses budget ceiling, billing currency, trial/overage rules and payment route after current vendor/platform review. |
| Admin and landing site | MVP admin: tenant/job/adapter status, budgets, abuse limits and audit; public landing content explains actual supported sources, fields, limits and pricing only | These controls support safe operations and prevent marketing claims exceeding measured capability. | Admin role model, support process, launch claims and metrics after user research. |

## MVP recommendation if evidence supports it

1. Responsive web client, account/workspace isolation and audited admin.
2. One validated segment and one launch geography/niche at a time.
3. Search builder with supported fields, source eligibility, provenance, preview, estimate and hard cap.
4. Manual run and observable job history first; daily local-time scheduling after scheduler/cost design.
5. CSV import and export only under schema/rights/retention controls.
6. User-approved, bounded AI setup assistance; no autonomous spend or outreach sending.
7. Defer native desktop/mobile until the shared API and web flow have user evidence.
8. Do not activate a provider until written rights, policy metadata, sample yield and economics pass gates.

## Acceptance gates and owner inputs

Do not mark WU-SAAS-MVP-DECISIONS complete until:
- WU-SAAS-USER-MARKET-RESEARCH has actual interview evidence or a documented owner-approved blocked disposition; competitor desk research alone is insufficient.
- Owner records accepted/rejected choices for repository boundary, launch segment/market, source funding mode, required fields, plans/quotas, payment route, client order and budget.
- Source rights/cost decisions cite source-specific evidence and qualified review where needed.
- MVP exclusions and measurable success targets are explicit.
- Approved decisions are captured in config/architecture/decision-records.json; no proposal is silently treated as accepted.

## Current truth

- This document is a decision aid, not consent.
- No SaaS code, paid API, data-provider account, payment gateway, hosting service or deployment was enabled.
- No price, market, platform, source, legal position or stack has been approved.
- Existing production operations remain a separate active workstream.
