# SaaS User and Market Research Workbench

Research snapshot: 2026-10-07 PKT — refreshed Lusha pricing and Lead411 offer comparison  
ANPOS work unit: WU-SAAS-USER-MARKET-RESEARCH  
Status: active — desk-research package refreshed; external validation pending  
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

### External participant routing and coverage plan

Use the participant's most recent real task to classify them; do not classify only by job title or employer. Record a primary segment and, when applicable, a secondary role. Keep internal VSN operators as a separate first-party comparison and do not count them as external validation.

| Code | Candidate segment | Count as a fit when the recent task shows… | Keep distinct from |
|---|---|---|---|
| AGENCY | Agency/BPO or lead-generation service | They personally built, bought, or quality-checked a business/contact list for an external client | In-house staff creating lists for their own employer |
| INHOUSE | In-house B2B sales/marketing team | They personally built, bought, or used a list for their own organization's sales/marketing process | A consultant or vendor delivering a client list |
| INDEPENDENT | Independent consultant/researcher | They personally assembled a business dataset for their own research or a client project, with no regular in-house team workflow | A list recipient who did not take part in sourcing or acceptance |
| OTHER | Other/unclear job | They have relevant list use but do not fit the three groups above, or their role is only recipient/approver | Do not silently reassign OTHER to the closest-sounding segment |

For an 8–12 person exploratory sample, recruit external participants across at least two of AGENCY, INHOUSE and INDEPENDENT; aim for 3–4 in each selected segment where recruitment allows. Include at least two people whose current workflow works adequately or who do not buy prospecting tools. These are coverage targets, not statistical quotas or a representative sample. Report every segment's actual n, including zero; if a cell is not recruited, mark it “not observed” rather than generalizing. Capture target countries/niches as participant experience, with no launch geography presumed.

### First-party operating case: VSN's existing lead workflow (repository evidence, not customer validation)

The audited production engine provides one concrete internal workflow to compare against the segment hypotheses: 56 configured US/Canada geographies and 12 fixed categories; free-only source mode; an operating target of 1,000 records per category; normalized phone required for acceptance; Google Sheets delivery; cross-day deduplication using an R2 fingerprint ledger; and fixed GitHub Actions scheduling with Asia/Karachi safeguards. These are repository configuration/runtime facts and operating choices, not measured SaaS demand, a yield guarantee, or a validated customer requirement.

Use this case to ask in future interviews which parts generalize: phone-required acceptance, repeated scheduled collection, category/location controls, spend/source visibility, cross-run deduplication, and spreadsheet/CRM handoff. Treat the 1,000-per-category target, fixed geography/taxonomy, free-only mode, and operator-driven recovery as VSN-specific constraints until another user demonstrates the same need. The audit found no SaaS tenancy, subscription, API or customer job scheduler in the current repo.

Source: `docs/ai/LEAD-SAAS-CURRENT-ENGINE-AUDIT.md` (read-only audit against main commit `ba7a8bcc224f429d5ab85d8cff076a3c9eccffa2`). No live production run, customer workbook, provider account or yield sample was examined.

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
| Yelp Places API | Business Search, Phone Search, Business Match and Details cover local listing lookup; API result listings require user-generated content or contributions, Search is capped at 50/page and 240/query. Yelp FAQ allows 24-hour content cache, says commercial analysis is not permitted, and reserves additional fields/use cases for Yelp Places Enterprise. Trial is evaluation-only; paid call allowance is metered and exact price isn't stated in the public FAQ. | Strong product/rights mismatch risk for a persistent lead export: retain only IDs indefinitely per FAQ, not full content; written Enterprise/paid terms must explicitly clear VSN's intended multi-tenant storage/export/analysis before even a pilot. Desk research only; no demand signal. FAQ gives 5,000 calls/30-day trial, while rate-limit docs state 300/day for a Starter trial plan, so actual plan/quota must be confirmed. | Yelp's reviewed source constraints signal a potential mismatch but aren't a legal conclusion about any negotiated Enterprise agreement. No vendor contacted and no source selected. |
| Foursquare Places | Foursquare advertises 100M+ commercial POIs, 200+ countries/territories and 1,100+ venue categories across its Places products; the API uses Pro/Premium endpoint pricing, and a separate flat-file offer is available. | A relevant location-source comparator; evaluate business/place discovery separately from named-contact prospecting and exact requested fields. | Vendor coverage claims are not independent yield evidence. Pricing page conflict: its Pro table lists 500 free calls, while the page footer says up to 10,000 free Pro calls; field tier changes endpoint pricing. Current new Places API terms for persistent lead storage, export/resale and attribution, flat-file quote/rights, contact-field availability, and market/niche yield remain unresolved. Legacy V3 endpoints had a May 15, 2026 deprecation date; validate against the current API. No selection. |

This is competitor/source workflow desk research only. It does not constitute customer validation, comparative testing, a legal determination, or source selection. Evidence IDs EVID-000023–000032 and EVID-000043–000052 are in the registry (54 entries total). The separate first-party incumbent workflow case is EVID-000033.


### Source evidence crosswalk for sections 3B–3D

The competitor statements above map to the existing ANPOS evidence registry as follows. These registry items establish documented workflows and source terms only; they are not user-demand findings or legal approvals. Lusha's current public plan/credit snapshot is EVID-000052.

| Competitor / claim group | Evidence IDs | Scope |
|---|---|---|
| Apollo filter/search and usage/resale terms | EVID-000014, EVID-000017, EVID-000020 | Official product/pricing/terms documentation; no VSN license inferred. |
| Clay provider waterfalls and two-meter model | EVID-000005, EVID-000018, EVID-000016, EVID-000022 | Official workflow and pricing comparator. |
| Hunter discovery/email verification/plans | EVID-000006, EVID-000015, EVID-000019, EVID-000021 | Official product/API/pricing comparator. |
| Seamless.AI contact workflow | EVID-000023 | Vendor-described workflow; marketing claims not independently tested. |
| Outscraper task flow, price and terms | EVID-000024, EVID-000025 | Product/pricing/terms capture; no upstream permission or redistribution rights inferred. |
| Google Places policy and field-mask billing | EVID-000002, EVID-000013, EVID-000026 | Official storage/display policy and SKU/field pricing evidence. |
| Yelp Places workflow, cache/analysis and rate limits | EVID-000030–EVID-000032 | Official API docs; plan-specific limits and intended SaaS use still need confirmation. |
| Foursquare product, pricing and self-service restrictions | EVID-000027–EVID-000029, EVID-000035 | Official public pages and self-service EULA; obtain qualified review of the exact VSN subscription and use. |
| LinkedIn Sales Navigator saved lead/search workflow | EVID-000034 | Official help workflow only; no data extraction/storage rights inferred. |
| VSN internal comparison case | EVID-000033 | Repository facts only; not customer or market validation. |
| Overture Places licensing, source fields and release lineage | EVID-000043–000045 | Official Overture Places guide, attribution/licensing page, and release catalog; source candidate only, no VSN sample. |
| OpenStreetMap data license and service boundary | EVID-000046 | Official copyright/license page; ODbL and service policies are separate checks. |
| Apollo current data licensing and API restrictions | EVID-000047–000048 | Current official Developer FAQ and API Terms; no VSN custom contract exists. |
| Lusha contact prospecting and public pricing | EVID-000049, EVID-000052 | Official help workflow and a dated dynamic pricing-page snapshot; retail plan facts only, no independent quality, VSN demand or downstream rights. |
| Lead411 SMB local-business leads and commercial claims | EVID-000050–000051 | Vendor-advertised daily small-business lead dashboard/API/CSV/MCP workflow, size/freshness claims, and unreconciled product-vs-general pricing displays; performance unverified. |

The hypothesis set H1–H7 is a researcher-generated set of propositions informed by the desk evidence and incumbent case. It has no direct participant evidence; keep all seven marked unvalidated until interviews/task tests produce observations.


## 3G. Adjacent competitor workflows: contact prospecting and local SMB leads (2026-10-06)

These official pages clarify that the competitive set spans different jobs. Lusha is a named-contact prospecting tool; Lead411 advertises newly registered small-business leads and recurring delivery. Its SMB page claims 1.1M+ leads across 1,400+ categories, access within days of formation, daily dashboard/email/CSV/API/MCP delivery, and plans starting at $49/month. A separate general pricing page displays Basic at $99/month per user, 200 US contacts/month, and a three-month minimum (EVID-000051). The pages do not explain whether these are the same product or comparable entitlements. Neither category is interchangeable with a local POI dataset or VSN demand evidence; all coverage/freshness figures remain vendor claims.

| Product/job | Vendor-documented workflow | Comparison implication | Evidence limit |
|---|---|---|---|
| Lusha — named-contact prospecting (EVID-000049) | Search contacts or companies with role/location/company filters; reveal contact details for credits; save to tables; reuse searches; export CSV or CRM records with plan-dependent limits. | Separate search, reveal/enrichment, saving, and export in any workflow comparison; ask whether buyers need people/contact details or just business records. | Lusha describes its own product; no independent contact accuracy, market demand, or VSN redistribution rights established. Credit values/limits can change. |
| Lead411 SMB Sales Boost — newly registered local SMB leads (EVID-000050–000051) | Lead411 advertises 1.1M+ leads across 1,400+ categories, access within days of formation, daily dashboard/email/CSV/API/MCP delivery, and a $49/month starting price. Its separate general pricing page shows a $99/month/user Basic plan for 200 US contacts/month with a three-month minimum. | Compare delivery, filters, freshness definition, geography, dedupe, output/API options, and user task fit; ask for a like-for-like plan quote. | Coverage and freshness are vendor claims. The pages do not clarify whether offers are comparable; quality and VSN downstream rights remain untested. |

**Effect on hypotheses:** the competitive evidence supports testing at least two distinct jobs—(1) local-business list acquisition and recurring delivery, and (2) named-person/contact prospecting with reveal-credit economics. It does not show which one VSN users want or whether Lead411’s advertised segment overlaps VSN’s eventual target market. Keep H1–H7 unvalidated pending external interviews and observed tasks.

## 4. Competitor pricing and commercial shape (official pages, 2026-10-05)

Prices below are vendor-published retail plan observations, not wholesale API rates and not a recommendation for VSN prices.

| Product | Public pricing/usage observed | Product implication and limit |
|---|---|---|
| Apollo | Pricing page names Free, Basic, Professional and Custom; describes credits pooled across a team, reset each billing cycle, with admin per-user credit caps. Exact dollar amounts were not exposed in the page text fetched for this review. Apollo explicitly says standard plans are for internal business use and powering customer-facing products/sharing/resale requires a separate custom-priced agreement. | Credit caps/usage ledger are relevant patterns; do not infer API resale economics from seats or standard plans. Request a written VSN-specific quote/contract before any cost model. |
| Hunter | Public page showed Free at $0/50 monthly credits; Starter $34/month with 24,000 annual credits; Growth $104/month with 120,000 annual credits; Scale $209/month with 300,000 annual credits; Enterprise custom. The page also showed a separate API-only Data Platform with configurable search and verification credit purchases. Displayed yearly-billing comparisons and the plan table summarize credits differently by period (monthly card vs annual totals), so preserve period when comparing. | A focused email product bundles discovery, verification, enrichment and outreach. API-only credits differ from product-seat plans; customer-facing data rights and VSN wholesale rates remain unverified. |
| Clay | Official page shows a free tier (100 Data Credits/month and 500 Actions/month). Pricing page content returned multiple visible Launch/Growth figures: Launch card $167/month while a page summary says starts at $185/month; Growth card $446/month while summary says starts at $495/month. Annual/action/data-credit figures also vary by selected billing display. | Treat the page as internally/dynamically inconsistent in this captured view; do not select a number as canonical without checking the live checkout state. Clay is a workflow comparator; end-customer redistribution/provider rights are not established. |
| Lusha | Official pricing selector showed Free $0/40 credits monthly; Starter $37.45/mo billed yearly, 4,800 credits/year, 1 seat; Pro $52.45/mo billed yearly, 7,200 credits/year, 2 seats; Premium $299.95/mo billed yearly, 40,800 credits/year, 5 seats; Scale custom. Email reveal=1 credit, phone reveal=5 credits. | Snapshot is tied to a dynamic page configuration and annual billing; verify selected allowance/current terms at checkout. Retail workspace price is not a VSN wholesale rate or redistribution right. |

Apollo credit details and the prohibition on using ordinary plans for customer-facing products come from its official pricing FAQ. Hunter values come from the official pricing page accessed on the snapshot date. Clay values are recorded with the observed page inconsistency intact. These plan prices do not establish VSN's cost per rights-eligible usable lead.

## 5. Interview recruitment and protocol

### Recruit
Aim for 8–12 discovery conversations before locking segment/MVP:
- At least 4 people who personally build or purchase B2B/business lead lists.
- At least 3 people from a second plausible segment.
- Recruit 8–12 external participants; internal VSN operators/collaborators are supplementary only (at most 2) and never count toward the external segment sample.
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

## 5A. Interview execution kit (ready to use; no sessions claimed)

### 60-second recruitment screener
Ask only these routing questions; record category/band, not unnecessary personal details:
1. In the last 90 days, have you personally built, purchased, or requested a list of businesses or business contacts? (yes/no)
2. Which best describes your role in that work? (builds lists / requests or approves lists / uses lists / other)
3. How often does this happen? (weekly or more / monthly / less often / never)
4. Which best describes the most recent list job, and for whom was it done? (built a client list at an agency/BPO / built a list for own employer / assembled data as an independent consultant/researcher / only requested or received a list / other)
5. Do you choose or influence tools and spending? (yes / shared / no)
6. Would you be comfortable discussing the workflow without sharing confidential customer or personal data? (yes/no)
7. Which countries/markets and business types did that recent job cover? (record broad categories only; no client or personal details)

Recruit recent, first-hand experience first. Route each qualified screener to AGENCY, INHOUSE, INDEPENDENT or OTHER using the routing table in section 2; record both the recent task and whether it served a client, the participant's own employer, or an independent project. Include people who do not buy tools and those whose current process works well. Do not treat screener responses as interview findings. Track only screener ID, routing bands, recruitment source and interview status; delete contact details when scheduling is complete unless the participant asks for follow-up.

### Copy-ready invitation
> Hi — I’m researching how teams create and use business lead lists. Would you be open to a 30-minute conversation about a recent real workflow? This is research, not a sales call. Please don’t share confidential client records or sensitive personal data. Participation is optional, and you can skip any question or stop at any time. I’ll take anonymized notes; I will not record audio/video unless we separately agree first. Would [two time windows] work for you?

### Opening consent script
> Thanks for your time. I’m trying to understand what you actually did the last time you needed a business or contact list. There are no right answers, and criticism is useful. Please avoid naming clients or sharing confidential records. May I take anonymized notes? I will not record this call. You may skip a question or stop whenever you want. Is that okay?

Record the response as yes/no and proceed only after a clear yes to notes. If audio/video recording is desired, seek separate explicit permission before recording and follow the participant's applicable privacy expectations. Do not infer consent from attendance.

### Interviewer run sheet
- Before: assign an interview ID; check the screener fit; prepare a blank capture form; do not show the concept until the recent workflow is understood.
- During: ask for one recent example; separate what happened from opinions or future guesses; ask “what happened next?” and “how did you decide?”; capture exact wording only with identifying details removed.
- If shown a concept: label it as an unvalidated VSN concept, present the same neutral flow to every participant, and ask what is confusing or missing before asking preference.
- After: within 24 hours, separate observation, participant quote, interpretation and open question; note contradictions and confidence; remove direct identifiers from research notes.

### Synthesis worksheet (one row per observation)
| Interview IDs | Observed job/trigger | Current workaround | Cost or failure described | Required lead fields/quality | Schedule/device need | Evidence type | Counterexample | Confidence | Decision affected |
|---|---|---|---|---|---|---|---|---|---|
| pending | pending | pending | pending | pending | pending | pending | pending | unassessed | pending |

Use counts as “n of interviewed participants,” not market prevalence. Keep a separate row for disconfirming evidence. Do not rank a segment solely by enthusiasm for a mockup; prioritize recent behavior, repeat frequency, measurable failure/cost, purchasing influence, and a legally feasible path to deliver the needed data.

### Session completion checklist
A session is usable evidence only when its record contains screener fit, consent-to-notes status, a concrete recent workflow, observed steps/tools, quality acceptance/rejection rules, spend/source constraints, a direct anonymized quote or artifact reference (if available), researcher interpretation separated from fact, and at least one uncertainty or contradiction check. Missing items remain unknown; do not fill gaps from assumptions.

This execution kit is preparation only. At snapshot time, no participant has been recruited or interviewed through this plan; WU-SAAS-USER-MARKET-RESEARCH remains in progress.

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
- Foursquare Places API pricing: https://foursquare.com/pricing/
- Foursquare Places delivery overview: https://docs.foursquare.com/data-products/docs/places-delivery-overview
- Foursquare Places API migration/pricing notice: https://docs.foursquare.com/developer/reference/upcoming-changes
- Foursquare Developer Console terms onboarding: https://docs.foursquare.com/developer/docs/developer-console-get-started
- Foursquare FSQ OS Places release notes: https://docs.foursquare.com/data-products/docs/fsq-os-places-release-notes
- Yelp Places FAQ and rates: https://docs.developer.yelp.com/docs/places-faq and https://docs.developer.yelp.com/docs/places-rate-limiting


## 3B. User/market hypothesis and competitor workflow synthesis refresh (2026-10-05)

Status: desk research synthesized; external validation remains pending. Sources were public official product/help/pricing/policy documentation reviewed on 2026-10-05. Competitor descriptions are vendor-documented workflows and are not independent usability, quality, demand, or legal assessments.

### Testable hypotheses (not findings)

| ID | Hypothesis | Disconfirming evidence to seek | Minimum next validation |
|---|---|---|---|
| H1 | Small lead-generation/BPO agencies may need repeatable local-business discovery when they currently assemble lists from directories, spreadsheets, and scripts. | Recent workflows show no meaningful time/cost loss, or users primarily need named contacts instead of business records. | Recent-workflow interviews plus one niche/city task prototype. |
| H2 | Search-to-export repeatability (saved criteria, job status/history, filters, freshness and provenance) may matter more than maximizing raw lead count. | Users only need one-off spreadsheets and do not value saved searches or repeat runs. | Walk through last real job; compare task completion with a neutral prototype. |
| H3 | Phone-qualified records may differentiate VSN for calling workflows, but a phone-required rule may suppress usable coverage. | Phone is optional or its requirement sharply reduces acceptable coverage. | Let users choose required fields and measure acceptance/rejection on a permitted sample. |
| H4 | Users may value visible per-job estimates and hard usage caps over vague/unlimited claims. | Users prefer fixed pricing and find metered estimates confusing or irrelevant. | Compare comprehension of mocked fixed-cap and usage-based flows; no real charges. |
| H5 | Free-source-first with optional paid enrichment may be attractive only if source rights and field yield are viable. | Free data is insufficient, paid providers prohibit customer-facing use, or costs exceed viable economics. | Authorized small benchmark and written provider clearance for the exact SaaS use. |
| H6 | Responsive web may satisfy initial demand before separate desktop/mobile apps. | Buyers need native/offline workflows or platform integrations that web cannot support. | Same task prototype tested at desktop and mobile breakpoints. |
| H7 | Local business/place discovery and named-contact prospecting may be distinct products and should be tested separately. | Same buyer demonstrates a unified recent workflow and a common success metric. | Separate task tests; compare buyer, required data, source rights and unit economics. |

These hypotheses are not ranked or validated. Existing VSN engine use is an internal operating case only, not external demand or willingness-to-pay evidence.

### Competitor workflow comparison

| Product | Documented flow | Product/commercial implication | Rights/validation boundary |
|---|---|---|---|
| Apollo | Apply people/company filters; review records; save lists or searches; enrich; export or sync CRM; optionally enroll in multi-touch sequences. | Benchmark understandable filter logic, reusable lists and a visible handoff from discovery to outreach. | Standard plan terms do not permit powering an external product, sharing customer-facing data or resale absent separate agreement. No SaaS rights assumed. |
| Clay | Build a table/workflow; run enrichment/AI steps; order/skip providers with conditions; monitor Actions and Data Credits; sync results. BYOK changes data-credit treatment. | Benchmark per-step cost/provenance, workflow preview, provider order and explicit stop conditions. | It is an orchestration comparator, not a VSN data license. |
| Hunter | Discover companies/domains; find and verify emails; save leads; use sequences; export or API. | Treat email finding/verification as a separate optional workflow and expose verification state and credit use. | Not evidence for phone-first place-discovery coverage or customer-facing data rights. |
| LinkedIn Sales Navigator | Search/filter leads and accounts; save them into lists; save searches for alerts; share/collaborate; selected CRM actions depend on plan. | Saved criteria, list reuse and alerts are useful UX patterns to test. | Product UI access does not grant permission to extract, retain or resell LinkedIn data. |
| Seamless.AI | Search/filter company/contact records; build lists; export or sync CRM; vendor describes extension, data verification and outreach actions. | Benchmark guided contact reveal, list handoff and CRM workflow. | Vendor performance claims are not independently tested; no redistribution rights assumed. |
| Outscraper | Submit category/location queries; choose locations and filters; create synchronous/asynchronous tasks; poll status; enrich domains/emails; export files. | Strong local-search task/status/export comparator; test estimate, progress and partial/failure states. | Published service/pricing does not itself establish upstream data permission or rights to redistribute within a SaaS. |
| Google Places API | Text/nearby search and place details with requested fields; content must be displayed according to attribution and API policies. | Exact field mask should drive cost preview; show source-aware display and limitations. | Places content is subject to caching/storage restrictions; place IDs are an exception. Not a default persistent bulk lead feed. |
| Yelp Places API | Business search/details and related local lookup endpoints; access is key/plan/quota controlled. | Benchmark lookup/filter functionality, but do not infer bulk prospecting use from API availability. | FAQ states content cache up to 24 hours, business IDs may be stored indefinitely, and commercial analysis is not permitted for Places integrations. Plan-specific written clearance needed for any SaaS storage/export use. |
| Foursquare Places API | Search/discover POIs and request details; entitlement/SLA depends on commercial terms. | Keep location discovery separate from contact prospecting and evaluate exact fields/yield. | Self-service terms restrict third-party/bulk availability, systematic locality extraction, service bureau/application provider use and lead generation unless expressly authorized via subscription. Treat as blocked absent explicit written rights. |

### VSN prototype requirements suggested by desk research

1. Search by market and niche, with optional location/area and only source-supported filters; visibly identify unsupported filters.
2. Preview query scope, eligible source, fields, expected cost/cap and known limitations before the user starts a paid job.
3. Show durable job ID and queued/running/partial/failed/completed states, timestamps, progress, cancel/retry and reason for failure.
4. Support saved criteria and workspace deduplication; schedule recurring jobs only after recurrence need and source rights are validated.
5. Show field-level source and last-checked time; distinguish missing from not found; use “verified” only for a defined validation method.
6. Start with CSV export; gate CRM integrations on provider terms, user authorization, mapping and retention/deletion rules.
7. Enforce provider/job/workspace caps and show estimated vs actual usage with a hard stop at the configured limit.
8. Gate each connector by documented purpose, territory, fields, display, retention, onward-sharing, attribution and deletion entitlement, not by API-key presence alone.

### Evidence and completion boundary

Desk-research synthesis for the hypotheses and workflows above is complete for this snapshot. User/market validation is not complete: no participants have been interviewed, no prototype task test has been run, and no segment, price, source or MVP has been approved. Competitor hands-on testing and vendor legal/commercial clearance have not been performed. Keep WU-SAAS-USER-MARKET-RESEARCH active until interviews are completed or explicitly recorded as blocked; do not mark market demand validated from this desk research.

Official references reviewed:
- Apollo prospect filters: https://knowledge.apollo.io/hc/en-us/articles/4412665755661-Use-Search-Filters-to-Find-Prospects
- Apollo pricing/data sharing restrictions: https://www.apollo.io/pricing
- Clay pricing: https://www.clay.com/pricing
- Clay Actions and Data Credits: https://university.clay.com/docs/actions-data-credits
- Hunter plans: https://hunter.io/pricing/
- Hunter plan FAQ: https://help.hunter.io/en/articles/11131690-pricing-plans-and-feature-faqs
- LinkedIn Sales Navigator workflow: https://www.linkedin.com/help/sales-navigator/answer/a10728097
- Seamless.AI contact search: https://seamless.ai/products/solutions/features/contact-search
- Outscraper Maps API: https://docs.outscraper.com/endpoints/maps-search/
- Outscraper pricing: https://outscraper.com/pricing/
- Google Places API policy: https://developers.google.com/maps/documentation/places/web-service/policies
- Yelp Places FAQ: https://docs.developer.yelp.com/docs/places-faq
- Foursquare self-service Places API EULA: https://foursquare.com/legal/terms/apilicenseagreement/
- Foursquare SLA applicability: https://foursquare.com/legal/terms/places-api/sla/


## 3C. Prototype task-test plan (prepared; no tests run)

Purpose: distinguish observed workflow fit from stated interest and clarify whether local-business discovery and named-contact prospecting are one job or two. Use the same neutral low-fidelity prototype and identical fictional data for every participant. This is a research instrument, not a feature commitment.

### Prototype task cards

| Task | Participant prompt (read verbatim) | Observe without coaching | Decision informed |
|---|---|---|---|
| T1 — Local business discovery | “You have been asked to prepare a list of independent auto repair businesses in one city for a client. Use this prototype to create the list you would normally deliver. Stop when you believe it is ready.” | What geography/category they select; which filters they need; their own required fields; how they judge an estimate; whether they inspect source/freshness; when they consider results exportable; confusion or workaround. | Whether local business/place discovery is a coherent first job; required fields/filters; acceptable preview and export. |
| T2 — Named contact vs place record | “For the same client, you now need to contact the person responsible for purchasing. Show what you would do next, using only options you would trust.” | Whether they expect a contact attached to each place, a separate people search, verification, CRM handoff, or manual research; what permissions/cost they expect; whether combining the two jobs creates confusion. | Whether named-person data is a separate phase/product and which source rights/data fields become hard gates. |
| T3 — Recurring run and spend control | “Your client wants an updated list every Monday. Configure the repeat run so you are comfortable leaving it unattended. Show what must be visible before you save.” | Timezone/schedule interpretation; pause/cancel expectations; what estimate/cap they need; no-result/partial/failure handling; notification needs; who can approve paid use. | Whether scheduling belongs in MVP; minimum guardrails and whether manual-first is acceptable. |

Use a clickable prototype or paper screens, not a working source integration. Populate it with clearly fictional/mock records labeled “sample data — not real leads.” Do not include competitor-owned records or imply an actual source license. Present source/cost values as labeled placeholders until benchmarked.

### Moderator protocol and measures

1. First ask the participant to narrate what they would do; do not explain controls unless they are blocked.
2. Record task start/end, completed/abandoned, wrong turns, help needed, misunderstood labels, and any workaround.
3. After each task ask: “What would you do next in your real work?”, “What would make this output unusable?”, and “What information was missing before you would trust/save this?”
4. Ask for a confidence rating only after observing task behavior; retain the participant’s reason in their words. Do not treat a favorable rating as demand proof.
5. Keep a separate note for prototype defects versus product/market mismatch. Any claim about provider coverage, legality, freshness, price or “verified” status must be visibly marked unknown until backed by actual evidence.

### Per-participant result record

| Participant ID / segment | Task | Completed? | Time / help / wrong turns | Fields and source requirements named | Trust/cost concerns | Workaround | Evidence quote/observation | Interpretation / confidence |
|---|---|---|---|---|---|---|---|---|
| pending | T1/T2/T3 | untested | untested | unknown | unknown | unknown | none | none |

### Review rule

Do not predeclare a numeric pass threshold. After the planned sessions, compare actual behaviors and counterexamples across the recruited segments, decide whether task wording/prototype defects biased results, and then propose a threshold with its rationale before any larger usability test. A task that works in a prototype does not prove provider rights, deliverable lead quality, willingness to pay, or market size.

No prototype has been built or tested through this plan as of this snapshot. This section is test preparation only.


## 3D. Low-fidelity screen storyboard for the prototype tasks

Status: specification only. This defines a neutral, repeatable set of screens for a paper or clickable mock. It is not a product specification or a provider integration. Keep a visible banner on every screen: **“Research prototype — fictional data only — no search or collection runs.”**

| Screen | Contents and controls | Participant sees / does | Research purpose |
|---|---|---|---|
| S0 — Task entry | Three task cards: “Build a local business list,” “Find the right contact,” “Set up a repeat run.” Intro text says this is a research prototype and that records/costs are simulated. | Moderator reads the applicable T1/T2/T3 task card; participant chooses the next action without coaching. | Check whether the user understands the job options and whether place discovery and contact discovery should be separate. |
| S1 — Define search | Fields: target (businesses or people), country, state/region, city, niche/category, optional radius; “business status” is selectable only as a requested filter and annotated “availability depends on source.” A “required fields” checklist is participant-controlled. | Participant configures a task in their own words; capture missing options and order of choices. | Learn the user’s vocabulary, required filters, and whether fields like phone/email are mandatory or optional. |
| S2 — Review source and run estimate | Source cards all labeled “Not selected / permission and coverage not verified”; data fields list; estimate card reads “No verified estimate in this prototype”; hard-cap input reads “Choose a limit for the test”; buttons “Edit search” and “Continue to simulated results.” | Participant decides what evidence/cost/limit they need before proceeding; mock continue does not call a source. | Test trust and spend-control expectations without making false cost, coverage, source or permission claims. |
| S3 — Simulated results | Three synthetic rows named “Example Business A/B/C,” city “Sample City,” fields display “Example only,” status “Mock source,” freshness “Not checked”; filters and export control are visible, but export downloads nothing. | Participant assesses what is missing, marks a hypothetical row usable/unusable, and explains what source/freshness evidence they would need. | Reveal acceptance/rejection criteria, provenance expectations, duplicate checks, and export needs. |
| S4 — Contact discovery branch | After S3, an optional “Find decision-maker contacts” action opens a separate explainer: “This prototype has no contact-data source. What would you do next in your real process?” | Participant narrates whether they expect person records, a separate tool, CRM handoff or manual research; no fake contact records appear. | Distinguish place/business discovery from named-person prospecting and identify provider dependency. |
| S5 — Recurring job | Frequency (off/weekly), day/time, timezone shown explicitly, notification choice, “Pause/cancel anytime” control, and limit field. Confirmation states “Simulation only — no job has been scheduled.” | Participant configures a hypothetical repeat run and explains what failure, partial completion, cost or approval notice they need. | Determine whether recurring schedules belong in the first workflow and what operational controls users need. |

### Navigation and content rules

- T1 uses S0 → S1 → S2 → S3. T2 starts from S3 → S4, then ask what they would do next. T3 uses S0 → S1 → S2 → S5.
- Use the exact same fictional rows, field values, labels and task wording for each participant. Do not use actual business/contact records, competitor data, provider logos, or unverified prices.
- Keep source, coverage, freshness and price as unknown placeholders. Do not let the visual design imply a provider is approved or a result is truly verified.
- Keep all controls keyboard reachable with visible focus; use plain labels, readable contrast and responsive layout. Record accessibility friction as a finding.
- If participant asks to run, export, save, email or schedule real data, explain that the research mock does not perform those actions. Do not enter personal or client data into the prototype.

### Moderator observation sheet

| Participant ID | Task | Starting screen | Click/choice path | Needed help | Confusing/misread control | Required fields named | Trust/cost/freshness evidence requested | Participant workaround | Outcome/quote | Researcher interpretation |
|---|---|---|---|---|---|---|---|---|---|---|
| pending | T1/T2/T3 | untested | untested | untested | untested | unknown | unknown | unknown | none | unassessed |

Record observable behavior separately from opinion. No pass score is assigned in advance; propose thresholds only after the planned sessions and review of counterexamples. Screen completion does not prove demand, data rights, source quality, cost viability, willingness to pay, or product-market fit.

This storyboard is ready for prototyping/review but has not been rendered, tested or shown to participants. The moderated session protocol, observation rubric and synthesis memo template are in [LEAD-SAAS-PROTOTYPE-TEST-RUNBOOK.md](LEAD-SAAS-PROTOTYPE-TEST-RUNBOOK.md). No participants have been recruited or tested; WU-SAAS-USER-MARKET-RESEARCH remains in_progress.

## 3E. Decision synthesis: separate jobs, competitive baseline, and evidence gates (2026-10-06)

**Status:** synthesis of public documentation and repository evidence only. This section does not select a launch segment, prove demand, set a price, select a provider, or authorize implementation.

### Keep the product jobs separate during discovery

| Candidate job | Candidate buyer to interview | Workflow references in this review | VSN evidence today | Decision-critical unknown | Discriminating interview/prototype test |
|---|---|---|---|---|---|
| Build a local-business/place list | Agency/BPO staff producing client lists; possibly local-market sales teams | Outscraper task-based Maps search; Google/Yelp/Foursquare/Overture/OSM place sources | VSN has an internal place/business workflow baseline (EVID-000033), not external demand evidence | Whether buyers need a saved local list repeatedly; mandatory fields and country coverage; rights to retain/export; phone-qualified yield and cost | Have participant show a recent real brief and rejection rules; use task T1 with synthetic records; only later run an authorized, pre-registered source sample |
| Find named people and direct contact details | In-house B2B sales/marketing; agencies that promise named decision-makers | Apollo and Seamless search/lists/CRM flows; Sales Navigator search/alerts; Hunter email finding/verification | No external evidence that VSN users prefer named people over business records | Required role/contact fields, accuracy/freshness standard, CRM destination, applicable data rights, credit economics, jurisdiction/privacy obligations | Task T2 asks participant to continue from a business to a decision-maker; record if they use a separate provider, manual lookup, or do not need this job |
| Clean, verify, or enrich an existing list | Agency/BPO, in-house sales, or consultant with an existing CSV/CRM list | Hunter email verification; Clay multi-step/provider workflow | No participant evidence that list cleanup is a frequent or paid pain | File schema, volume/frequency, required enrichment, acceptable error rate, and source use/retention terms | Ask to walk through the last imported list, show a redacted schema only if voluntarily offered, and identify the exact manual cleanup steps |
| Repeat/schedule collection and govern spend | Buyer/operator already repeating any of the above jobs | Apollo saved-search alerts; Clay action/data-credit meters; Outscraper async task lifecycle | Fixed scheduling and dedupe exist only in VSN's internal workflow | Recurrence frequency, acceptable freshness, desired timezone/failure behavior, cost predictability and cancellation expectations | Task T3 uses a simulated schedule; ask what they do today after partial/late jobs and whether a schedule actually saves work |

A source/API vendor, a workflow-enrichment tool, and a full prospecting suite are not interchangeable direct competitors. Keep three categories in the notes: **(1) data/source options** such as Google Places or Yelp, **(2) orchestration/enrichment** such as Clay, and **(3) end-user prospecting suites** such as Apollo or Seamless. Compare each only on the job it performs; a source's records do not equal a complete SaaS workflow, and a vendor workflow does not grant VSN downstream data rights.

### What competitor evidence supports—and what it does not

The refreshed first-party pages, including the Lead411 pricing cross-check EVID-000051, confirm a competitive workflow baseline: filters plus reusable saved searches/lists; some form of alerts or repeat use; review/export or CRM handoff; asynchronous job tracking for place-search APIs; and usage meters or credit governance. Examples: [Apollo saved searches and alerts](https://knowledge.apollo.io/hc/en-us/articles/4409803718669-Save-Share-and-Set-Alerts-for-Searches) and its [standard-plan external-product restriction](https://www.apollo.io/pricing) (EVID-000036–000037); [Clay's separate Actions and Data Credits](https://www.clay.com/pricing) (EVID-000038); [Hunter's team credit controls and plan separation](https://help.hunter.io/en/articles/11131690-pricing-plans-and-feature-faqs) (EVID-000039); [Sales Navigator saved-search alerts](https://www.linkedin.com/help/sales-navigator/answer/a102024/) (EVID-000040); [Outscraper's async-capable Maps Search task](https://docs.outscraper.com/endpoints/maps-search/) (EVID-000041); and [Google Places storage policy](https://developers.google.com/maps/documentation/places/web-service/policies) (EVID-000042).

These pages establish what vendors document about their products. They do **not** establish that VSN's candidate users have an unmet need, that advertised data is accurate, that usage-based pricing is preferred, that an API's upstream source permits SaaS resale, or that VSN can profitably supply a given country/niche. Broad claims such as “more leads,” “verified,” “real-time,” or “cheaper” are not accepted as facts without independent measurement and appropriate source permission.

The desk review also reduces the strength of a generic positioning claim: **filters, saved searches, lists, exports, CRM handoff, and basic usage controls are not demonstrated differentiators by themselves.** A narrower candidate to test is repeatable local-business list production with configurable required fields, visible provenance/freshness, deduplication, clear partial-job status, and an explicit cost/permission gate. This is a product hypothesis, not a validated wedge; provider rights and phone/field yield could make it infeasible.

### Segment test plan that fits the current evidence

For the planned 8–12 exploratory interviews, use **two primary comparison cohorts**, not all three segments at once: (A) agency/BPO staff who personally source or quality-check client lists, and (B) in-house B2B sales/marketing staff who personally build or use lists. Aim for 3–4 qualified participants in each cohort, then use remaining places for disconfirming/adequate-workaround cases. If recruitment access makes one cohort impossible, record that limitation and test the accessible cohort plus counterexamples; do not silently treat internal VSN users or list recipients as substitutes. Independent consultants remain a follow-up cohort unless evidence shows they are a materially different buyer/job worth testing now.

Use the same recent-work interview prompts and synthetic-data tasks across both cohorts. Record actual last-job date, trigger, frequency, fields rejected, current tools, manual minutes, spend and spend authority, destination, and what happened after a poor result. Distinguish direct observation, participant report, opinion, and researcher inference. “Would use/pay” alone is not validation. Do not collect confidential client records.

### Evidence and decision gates

| Gate | Evidence required | Current status |
|---|---|---|
| Segment/problem | Repeated recent job, concrete failure/cost, required-field rules, identifiable buyer, and counterexamples by segment | **Unknown** — no interviews/surveys |
| Workflow fit | Observed task completion/time and comprehension on the same neutral mock across cohorts | **Not tested** — storyboard only |
| Source feasibility | Written use/storage/export rights, authorized sample, measured rights-eligible usable yield, freshness, duplicates, and unit cost | **Open** — desk matrix only; no provider selected/sample run |
| Price/commercial | Current alternatives/spend authority, tested plan/limit comprehension, real provider and infrastructure cost model | **Unknown** — vendor pricing pages are not VSN willingness-to-pay evidence |
| Market sizing | Named segment, launch geography, repeat-job frequency, buyer count and obtainable channel | **Not estimable without false precision** — segment/geography/MVP are unselected |
| MVP decision | Owner-approved segment/job, fields, source/funding model, exclusions, success metric, platform order and budget | **Blocked** — ADR-0007 remains proposed |

**Research disposition:** desk-research deliverable is complete and refreshed; user/market validation is still **in progress**. Continue WU-SAAS-USER-MARKET-RESEARCH until external sessions are synthesized with counterexamples, or record an actual recruitment blocker. Do not mark it complete from competitor research alone. The next responsible action is participant recruitment and interviews; no external outreach or sessions have been conducted by this research pass.

## 3F. First-party source and API-terms recheck (2026-10-06)

This is a live official-document recheck, captured separately from the earlier vendor workflow review. It remains desk research: no provider was contacted, no dataset was downloaded for VSN, and no legal or source-use approval is recorded.

| Source/terms | Current primary-source observation | Product/research consequence | Still unknown |
|---|---|---|---|
| Overture Places (EVID-000043–000045) | Overture's Places guide says that theme contains no OSM data; it documents source-dependent CDLA-Permissive 2.0, Apache 2.0 and CC0 licensing, a `sources` field, confidence, taxonomy, GERS identity, optional phone/email properties, and dated monthly releases. The published September 2026 source table reports approximately 81M feature records across named providers. | Prioritize Overture Places as the first authorized sample-benchmark candidate. Store release/source lineage and maintain a release-specific source-to-license map; do not claim all records have phone/email or that all Overture themes share the Places license profile. | VSN country/niche yield, field completeness, freshness, permitted customer-facing storage/export and cost. Aggregate counts are vendor-reported and not a usable-record benchmark. |
| OpenStreetMap (EVID-000046) | OSM says data is under ODbL with attribution/share-alike obligations and separately points out that OSMF does not offer free third-party API/tiles. | Evaluate ODbL-derived-database implications and a compliant, operationally appropriate data-access/hosting route separately. | Whether a proposed VSN database triggers specific obligations; whether any public endpoint suits recurring SaaS workloads. Qualified review required. |
| Apollo (EVID-000047–000048) | Current Developer FAQ says sharing, exposing or reselling data to non-Apollo users requires a custom contract; API Terms restrict third-party API access/sublicensing and competitive replication absent an applicable agreement. | Do not treat an ordinary Apollo account/API key as a SaaS source entitlement. Keep Apollo as a workflow comparator unless a VSN-specific contract is evaluated. | Whether Apollo would offer VSN suitable terms, territory/fields, price, and downstream rights; no agreement has been sought or approved. |

**Inference:** the above makes Overture Places the best first *research candidate* from the reviewed source set for an authorized yield test, because its stated Places theme licensing and batch-release model appear more compatible with a retained-data experiment than the reviewed Google Places storage rules. This is not legal clearance, customer demand evidence, provider selection, or proof of quality. OSM remains a separate alternative with a distinct share-alike and operational-access path. Do not join OSM into an Overture-derived customer dataset without qualified review of database obligations.

## 8. Status reconciliation and acceptance gates (2026-10-06)

This section distinguishes the completed desk-research deliverables from the evidence that still requires participants. It does not mark the research work unit complete.

| Research acceptance item | Status | Evidence / honest boundary |
|---|---|---|
| Segment and problem hypotheses | Prepared for testing | H1–H7 are researcher hypotheses informed by public-source desk research and the internal VSN operating case; none is participant-validated. Section 3E keeps place discovery, named-contact prospecting, list enrichment, and recurring workflow as separate jobs. |
| Competitor workflows compared beyond marketing summaries | Complete as public-document review | Apollo, Clay, Hunter, LinkedIn Sales Navigator, Seamless.AI, Outscraper, Google Places, Yelp Places and Foursquare workflows/policy limits are summarized in sections 3B–3E and crosswalked to registry IDs EVID-000017–000050. No hands-on competitive trials or independent usability tests were performed. |
| Interview preparation | Complete as preparation | Screener, invitation, consent script, interviewer guide, capture/synthesis forms and [prototype test runbook](LEAD-SAAS-PROTOTYPE-TEST-RUNBOOK.md) are prepared. No outreach or session has been performed. |
| Prototype screens/tasks | Specified only | Three tasks and screen storyboard are specified; no clickable prototype has been built or shown to participants. |
| User/problem evidence from recent workflows | Pending | No external participant interview, survey, or workflow artifact has been collected. |
| Counterexamples and segment comparison | Pending | No participant evidence or counterexample has been gathered. |
| MVP outcome metric and baseline | Candidate measures only | Candidate metrics are listed in section 6; no user-backed baseline or target has been agreed. |
| User research work-unit exit | Not met | Keep WU-SAAS-USER-MARKET-RESEARCH in_progress until sessions are completed and synthesized, or a genuine recruitment blocker is recorded without claiming validation. |

Source validation is a separate evidence stream from participant research. A rights-aware, pre-registered sample benchmark protocol is in [LEAD-SAAS-SOURCE-SAMPLE-BENCHMARK.md](LEAD-SAAS-SOURCE-SAMPLE-BENCHMARK.md); it remains unrun until an owner-approved market/niche brief and source-specific rights gates exist. It cannot substitute for interviews or validate demand.

### Next execution sequence

1. Recruit participants who pass the screener, with external participants across at least two candidate segments and a mix of tool buyers/non-buyers.
2. Run the same neutral 30-minute protocol and fictional-data tasks; retain anonymized observations, quotes and counterexamples.
3. Synthesize behavior by segment, distinguish participant facts from opinions and interpretation, and record the sample size.
4. If the prototype reveals new requirements, revise the mock and run focused follow-up tasks; do not call the segment validated based on stated interest alone.
5. Submit explicit owner decisions on segment, launch market, source/funding mode, fields, outcome metrics, price/payment, platforms, repository boundary and budget. Until then, downstream MVP and architecture work remain gated.

Recruitment contacts must not be copied into this repository. Do not claim interviews are scheduled or completed until there is session evidence.


### Additional official workflow recheck (2026-10-07)

Seamless.AI documents targeted search, saved lists/searches, credit-based contact research, CRM/CSV export and plan-dependent API access (EVID-000053). Clay documents reusable enrichment Functions, provider waterfalls, conditional fallback and per-action credit consumption (EVID-000054). These are vendor workflow facts only; they do not validate VSN demand, source rights, data quality or unit economics.
