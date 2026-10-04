# SaaS User and Market Research Workbench

Research snapshot: 2026-10-05 PKT  
ANPOS work unit: WU-SAAS-USER-MARKET-RESEARCH  
Status: active — desk research and interview preparation only  
Evidence boundary: No customer interviews, surveys, pricing tests, or product trials have been conducted for this plan. Competitor documentation describes vendor workflows; it does not validate VSN customer demand or vendor performance.

## 1. Research questions

1. Which specific user segment has a frequent, costly business-lead discovery job that this product can solve?
2. What result counts as a “useful lead” for that segment: correct business, required fields, freshness, contactability, source rights, or all of these?
3. How do users currently select country/region, niche, business/contact filters, source, schedule and export?
4. Which failures cost users time or money: low coverage, duplicates, stale details, unclear status, manual list cleanup, unpredictable credits, or missed schedules?
5. Do users need place/business discovery, named-contact prospecting, email verification, or workflow orchestration? These are different jobs and products.
6. Which controls make a user comfortable with recurring collection: preview, sources, cost cap, no-paid-fallback guarantee, pause/cancel, history, and deletion?
7. Which client is needed at launch? Test whether desktop/mobile means a separately installed app or a responsive web experience.
8. What is a credible paid outcome and acceptable spending model? Do not ask only whether someone “likes” the idea.

## 2. Initial segment hypotheses (unvalidated)

| Segment hypothesis | Job to test | Evidence needed |
|---|---|---|
| Small lead-generation/BPO agency | Produce client-specific business lists repeatedly, with required fields and a clean export | Actual weekly workflow, client acceptance rules, staff hours, current tools/cost, sample brief |
| Small B2B sales/marketing team | Find businesses in chosen markets and maintain repeatable, fresh segments | Search frequency, CRM handoff, freshness needs, source requirements, existing enrichment spend |
| Independent researcher/consultant | Build one-off niche/country datasets with clear provenance | Repeat rate, filtering needs, acceptable CSV/import process, rights obligations |
| Existing VSN lead-engine operator | Reuse the proven source/runtime capabilities through a customer-safe multi-tenant service | Which existing steps are reusable, what is operator-specific, operational capacity and isolation requirements |

Do not pick a launch segment from this table without observed interviews and sample workflows.

## 3. Competitor workflow desk review

| Product | Documented journey | Useful product lesson | Important boundary |
|---|---|---|---|
| Apollo | Search people or companies; combine filters; save lists/saved searches; enrich records; optionally move them into sequences/workflows and export | Make filter logic understandable, preserve reusable searches/lists, distinguish discovery from enrichment, and show where outreach begins | Apollo is a broad B2B people/company prospecting and engagement suite. Its public features do not show demand for VSN's business-location discovery workflow or grant VSN any data rights. |
| Clay | Start with a table/audience or workflow; add enrichment; configure provider waterfall order, inputs, skipped providers, run conditions and optional successful-provider output | Let users control provider order and conditions; preview successful provider/provenance; reuse a proven workflow template; expose cost per enrichment action | Clay is orchestration/enrichment-focused. Workflow complexity and per-action credits may not suit a simple recurring niche-business search. |
| Hunter | Discover companies by industry/location/keywords; inspect/filter email data; save leads; find or verify email; export CSV | Treat email discovery and verification as a distinct optional step, with explicit verification status and separate usage | Hunter focuses on email/company/contact workflow, not guaranteed phone-first POI discovery. |
| VSN candidate | Configure location, niche, status and fields; choose eligible source mode; preview coverage/limits/cost; run or schedule; review provenance/results; filter/export | Differentiate with understandable source eligibility, daily schedule controls, field completeness and paid-spend consent | Entire customer journey is still a design hypothesis. Validate with interviews before MVP commitment. |

Apollo's official guidance documents AND logic across filters and OR logic among values in one filter; its workflows include saved lists/searches, enrichment and optional outreach. Clay documents reorderable/skip-enabled provider waterfalls, run conditions and optional successful-provider output. Hunter documents company discovery filters, saved leads, email finding/verification and CSV export. These observations guide question design; they are not comparative usability tests or customer evidence.

## 3A. Relevant alternatives added to desk review (official documentation, accessed 2026-10-05)

| Alternative | Documented workflow/commercial detail | Research implication | Boundary |
|---|---|---|---|
| Seamless.AI Prospector | Contact-first B2B prospecting with AI-enhanced filters; official FAQ advertises 50 free search credits without a card, then directs users to sales for customized plans. | Compare named-contact search as a distinct optional job, and test whether users want it alongside place/business discovery. | Official pricing page did not expose usable price text in this capture. Free credits and product claims do not validate VSN demand, contact quality, or VSN redistribution rights. |
| Outscraper | Markets a Google Maps crawler flow: choose location/category, set parameters, run a task, download results. Pricing page shows a displayed B2B database initial tier at $2/1,000 businesses for first 5k records; its short terms require a payment method before first use and reference a separate Global Services Agreement. | Cost per record, payment-method requirement, recurring use, and rights must be separate filters in any free/paid comparison. A nominal free threshold may still require a card. | This is scraping of Google Maps according to Outscraper's own product description. Published price is not permission from the upstream data source or a distribution/license clearance. Keep unselected pending qualified review and written exact rights. |
| Google Places API (New) | Search/details returns depend on requested fields; field masks control response fields and mixing Essentials + Pro fields bills at the highest applicable SKU. | Cost preview must be generated from the exact field mask and refresh when users add/remove fields; broad “paid source” toggles are insufficient. | Field-mask billing documentation does not resolve Places storage/display restrictions; see source-feasibility matrix and re-check current policies before use. |

This is competitor/source workflow desk research only. It does not constitute customer validation, comparative testing, a legal determination, or source selection. Evidence IDs EVID-000023–000026 are in the registry.

## 4. Competitor pricing and commercial shape (official pages, 2026-10-05)

Prices below are vendor-published retail plan observations, not wholesale API rates and not a recommendation for VSN prices.

| Product | Public pricing/usage observed | Product implication and limit |
|---|---|---|
| Apollo | Pricing page names Free, Basic, Professional and Custom; describes credits pooled across a team, reset each billing cycle, with admin per-user credit caps. Exact dollar amounts were not exposed in the page text fetched for this review. Apollo explicitly says standard plans are for internal business use and powering customer-facing products/sharing/resale requires a separate custom-priced agreement. | Credit caps/usage ledger are relevant patterns; do not infer API resale economics from seats or standard plans. Request a written VSN-specific quote/contract before any cost model. |
| Hunter | Public page showed Free at $0/50 monthly credits; Starter $34/month with 24,000 annual credits; Growth $104/month with 120,000 annual credits; Scale $209/month with 300,000 annual credits; Enterprise custom. The page also showed a separate API-only Data Platform with configurable search and verification credit purchases. Displayed yearly-billing comparisons and the plan table summarize credits differently by period (monthly card vs annual totals), so preserve period when comparing. | A focused email product bundles discovery, verification, enrichment and outreach. API-only credits differ from product-seat plans; customer-facing data rights and VSN wholesale rates remain unverified. |
| Clay | Official page shows a free tier (100 Data Credits/month and 500 Actions/month). Pricing page content returned multiple visible Launch/Growth figures: Launch card $167/month while a page summary says starts at $185/month; Growth card $446/month while summary says starts at $495/month. Annual/action/data-credit figures also vary by selected billing display. | Treat the page as internally/dynamically inconsistent in this captured view; do not select a number as canonical without checking the live checkout state. Clay is a workflow comparator; end-customer redistribution/provider rights are not established. |

Apollo credit details and the prohibition on using ordinary plans for customer-facing products come from its official pricing FAQ. Hunter values come from the official pricing page accessed on the snapshot date. Clay values are recorded with the observed page inconsistency intact. These plan prices do not establish VSN's cost per rights-eligible usable lead.

## 5. Interview recruitment and protocol

### Recruit
Aim for 8–12 discovery conversations before locking segment/MVP:
- At least 4 people who personally build or purchase B2B/business lead lists.
- At least 3 people from a second plausible segment.
- At most 2 close collaborators from VSN to reduce internal confirmation bias.
- Include non-users/currently manual workflows; do not recruit only enthusiastic friends.
- Record role, company size band, target markets, list frequency and whether participant controls tool spending. Avoid collecting unnecessary personal data.

### 30-minute interview
1. **Context (3 min):** “Tell me about your role and the kind of customer/market you work with.”
2. **Recent event (8 min):** “Walk me through the last time you needed a list of businesses or contacts, from request to delivery.”
3. **Workflow and tools (6 min):** Ask which sources/tools/files were used, steps and handoffs, where the participant lost time, what was manually corrected, and how duplicates were handled.
4. **Quality and outcome (5 min):** Ask what makes a row usable or rejected, mandatory fields, how quality/freshness is checked, and what happened when volume was too low.
5. **Spend and risk (4 min):** Ask what is paid today, who approves spend, surprise-charge experience, source/retention rules, and acceptable hard caps. Ask for ranges only if participant is comfortable.
6. **Concept test (3 min):** Show a neutral one-page workflow: market/niche → source/fields and cost preview → manual or scheduled run → provenance/filter/export. Ask what they would remove, what is missing, and what would prevent a trial.
7. **Close (1 min):** “What did I fail to ask?” and request permission only if a follow-up or sample artifact is useful.

Avoid leading questions such as “Would you use this AI lead-gen app?” Prefer past behavior, artifacts and specific trade-offs. Do not request confidential client lists.

### Capture form (one record per interview)
- Interview ID; date; interviewer; consent to notes; participant segment/role/company-size band.
- Recent job and trigger; frequency; current steps/tools; time/cost; pain severity.
- Required fields; accepted/rejected criteria; freshness; duplication process.
- Free/paid/BYOK behavior; budget owner; unexpected-cost tolerance; source/privacy restrictions.
- Schedule need and timezone; delivery/export/CRM destination; client device.
- Exact anonymized quote or observed artifact reference (never infer it).
- Evidence class, confidence, contradicting evidence, follow-up, and researcher interpretation separately.

## 6. Synthesis rules and proposed success metrics

After interviews, cluster repeated observed jobs/pains and preserve contradictions. Count participants per observation; do not convert frequency from a small qualitative sample into a population estimate. Follow with a task-based prototype test and a larger survey only if a decision still needs quantification.

Candidate outcome metrics to test with users:
- Time from brief to first rights-eligible, usable lead.
- Accepted-lead rate under user-defined required fields.
- Duplicate and stale-record rates on a labeled sample.
- Setup completion and first successful run.
- Schedule success/partial/failure visibility and recovery time.
- User understanding of source, field provenance and paid cap before run.
- Cost per usable lead by source/market/niche.
- Repeat use and export/CRM handoff completion.

No numerical target is approved yet. Baselines must come from observed workflows and a measured permitted-source sample.

## 7. Decision gates

Do not complete WU-SAAS-USER-MARKET-RESEARCH until:
- The launch segment and top user job have interview evidence and at least one counterexample/contradiction review.
- Competitor comparison uses observed documented workflows/features, not only marketing summaries.
- MVP outcome metric and baseline collection method are chosen with user evidence.
- Business discovery vs named-contact enrichment distinction is resolved.
- Interviews are completed or explicitly recorded as blocked by unavailable participants; do not imply validation if only desk research exists.

After that, take WU-SAAS-MVP-DECISIONS and record owner decisions as ANPOS ADRs. User research does not authorize source use, paid provider activation, stack approval, or implementation.

## Pricing sources
- Apollo pricing and external-product restrictions: https://www.apollo.io/pricing
- Hunter plans and API-only Data Platform: https://hunter.io/pricing
- Clay plans/actions/data credits: https://www.clay.com/pricing
- Seamless.AI Prospector and pricing: https://seamless.ai/products/prospector and https://seamless.ai/pricing
- Outscraper Google Maps crawler, pricing and Terms of Service: https://outscraper.com/google-maps-crawler/, https://outscraper.com/pricing/, https://outscraper.com/terms-of-service/
- Google Places API usage and billing: https://developers.google.com/maps/documentation/places/web-service/usage-and-billing
