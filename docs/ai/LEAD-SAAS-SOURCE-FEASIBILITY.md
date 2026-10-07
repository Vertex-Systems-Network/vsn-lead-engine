# SaaS Source Feasibility Matrix

Research snapshot: 2026-10-05 PKT  
ANPOS work unit: WU-SAAS-SOURCE-FEASIBILITY  
Scope: Official public documentation/terms plus repository adapter facts. No vendor was contacted, API key used, purchase made, or legal conclusion obtained. Candidate does not mean approved.

## Decision summary

- Open batch discovery candidate: Overture Places, subject to preserving each record's source/license/attribution and measuring coverage by country and niche. Dataset access is free; compute and operations are not necessarily free.
- Open fallback: OSM extracts or a managed/self-hosted Overpass service, only after ODbL review, attribution/share-alike design, and capacity planning. Do not build recurring SaaS on an unqualified public community endpoint.
- Paid broad B2B data: Apollo documents a reseller route, but standard API terms do not allow third-party data access/resale; written approval, scoped terms, coverage and quote are required.
- Paid email enrichment: Hunter supports discovery, email finding and verification APIs with credit/rate limits. It is not a phone-first place database; its redistribution/storage/key terms for VSN remain unverified.
- Google Places has paid SKU pricing and restrictive storage/display conditions; it is a poor default for a persistent, cross-provider lead database.
- Yelp Places is a conditional local-listing comparator with material retention/analysis constraints; it is not approved for persistent lead storage/export.
- Clay is a competitor/workflow comparator, not an established VSN data license.
- Custom should start with user-authorized CSV import; later support allowlisted documented connectors. BYOK does not override provider terms. No arbitrary URL scraping.

No provider, source mode, rate card, country promise, or legal interpretation is selected by this matrix.

## Source matrix

| Candidate / role | Geography and useful fields | Rights, storage and attribution | Cost, limits and operating shape | Feasibility |
|---|---|---|---|---|
| **Overture Places — open batch discovery** | Intended global Places dataset; actual density varies by country, niche and upstream source. Schema offers name, point geometry, taxonomy/category, confidence, optional addresses, websites, socials, emails, phones and optional operating status. operating_status is not opening hours or current-time open status. Optional fields mean phone/email completeness must be measured. | Mixed-license data: CDLA Permissive 2.0 and Apache 2.0 depending on source. Source metadata/license is per record. Foursquare-sourced records have Apache notice/change-date requirements. Preserve source/license/attribution and quarantine unknown or incompatible rights. No blanket license assumption. Qualified review needed for VSN display, retention, enrichment and redistribution model. | Published S3/Azure data access is free; batch release-based. Compute, requests/egress, storage, refresh and operations can cost. No contact-field completeness or yield SLA established. | Strongest initial batch candidate if license-aware ingestion and market/niche coverage benchmark are P0 gates. Free access does not mean zero operating cost or blanket redistribution rights. |
| **OpenStreetMap + self-hosted Overpass/extracts — fallback** | Global community map. Business tags and optional phone, website, address and status-like data vary by contributor/location. Global extent does not imply equal POI/contact coverage. | ODbL requires attribution and may require share-alike when a derivative database is publicly conveyed. Exact combination with other sources and customer exports needs qualified ODbL review. OSM editing API is not a read-only bulk-search API. Overpass public instances have finite, operator-specific policies; Overpass guidance says cache/rate-limit and use extracts for large work. | Open data has no purchase fee; self-hosting requires compute, storage, replication, monitoring. Public endpoint capacity is not an SLA. Hosted service quote is provider-specific. | Conditional fallback only; prefer extracts or owned/contracted endpoint with license, attribution and shutdown controls. |
| **Foursquare Places API / flat file — conditional location-data candidate** | Foursquare markets 100M+ commercial POIs, 200+ countries and territories, and 1,100+ categories. This is vendor-stated total coverage, not evidence of phone/email completeness or yield in a target niche. | Public pages reviewed do not establish VSN's rights to retain provider attributes in a multi-tenant lead database, export/redistribute them to end users, or required attribution for that use. Legacy Personalization API guidelines are explicitly scoped to that API and must not be generalized to the new Places API. Obtain the applicable current contract/terms and qualified review. | New Places API Pro/Premium usage is pay-as-you-go by endpoint/call tier; exact fields can change tier. The current pricing page conflicts: Pro table shows 500 free calls, its footer advertises up to 10,000 free calls. Flat-file terms/pricing are not established by the reviewed public pages. Legacy V3 endpoint migration date was May 15, 2026; any evaluation must use the current API. | Possible location-source alternative to qualify; first resolve current terms/pricing, then benchmark labeled country/niche samples. Not approved or selected. |
| **Yelp Places API — conditional, review-rich local listing source** | Search/phone search/business match/details endpoints expose business name, address, phone, rating, price, review count, categories and coordinates; Yelp's API FAQ says results are from geographies where Yelp is available. Yelp says listings need Yelp user-generated content or other user contributions, creating a likely selection bias toward reviewed/updated businesses. Search is capped at 50 results per request and 240 per originating query. | Public FAQ permits caching Places content for at most 24 hours and says Yelp Business IDs can be stored indefinitely. It says commercial analysis is not permitted for Places integrations. Public getting-started guidance directs commercial use in a consumer product to Yelp Places Enterprise. These conditions appear poorly matched to a persistent/exportable lead database; exact VSN use, export and derived-analysis rights require written plan-specific clearance and qualified review. | FAQ: trial up to 5,000 calls over 30 days, evaluation only; paid default 30,000/month, daily limit up to 5,000, then overage in 1,000-call increments; exact price is not public in the docs. Rate-limiting page separately says signup-selected Starter trials may have 300 calls per 24 hours. Treat the plan-specific discrepancy as unresolved and read the actual account quota headers. | Low-priority conditional comparator; do not use trial commercially or assume persistent lead storage/export is allowed. Require exact Enterprise/paid terms, live quota and per-country/niche yield validation. Not selected. |
| **Google Places API — paid, constrained lookup** | Search/details expose place attributes based on requested fields/SKU; target-market and field availability need probes. Do not merge status/fields blindly into a universal schema. | Generally may not prefetch/cache/store Places content beyond allowed exceptions; Place IDs are exempt. Display rules require Google Maps/logo/attribution in applicable contexts. This conflicts with a normal long-lived multi-provider lead export unless the flow is specifically designed for permitted use. | Pay-as-you-go by SKU. Current table (checked 2026-10-05): monthly free caps include 10,000 Essentials and 5,000 Pro billable events. Examples: Place Details Essentials $5 per 1,000 at first paid tier after cap; Nearby Search Pro $32 per 1,000 at first paid tier after cap. Not total system cost; request fields affect SKU. | Not a default persistent lead source. Consider only a terms-compliant interactive/map feature with SKU cost controls and live re-check. |
| **Apollo API / Data Reseller — paid B2B source** | People/company search and enrichment include professional contacts and company information, with filters such as location/job/seniority. Exact country-level availability and phone/email coverage for VSN's segment need trial/sample evaluation. | Standard API terms limit use to internal purposes and prohibit third-party access/sublicensing absent another Apollo agreement. Developer FAQ says exposing/reselling data to non-Apollo users needs a custom contract. Apollo documents a reseller program with partnership review, trial and reseller agreement. Confirm exports, storage, retention, customer access, source-combining and AI uses in written terms. | Ordinary API plans/credits exist, but reseller prices/limits are not public in reviewed sources. Partnership, trial and agreement required. Do not model SaaS margins from seat pricing. | Best conditional paid-source path to qualify for broad B2B contacts. No adapter until Apollo approves VSN's exact distribution model and commercial terms. |
| **Hunter API / Data Platform — email enrichment** | Company discovery, domain search, email finder/verifier and email enrichment. Coverage does not establish phone-first business discovery. | API keys are private. Public docs explain features/rate limits but do not settle VSN customer-facing resale, long-term storage, exports, retention or multi-tenant key model. Obtain applicable terms before exposing output to SaaS users. | Credit-based. Examples from public docs: Domain Search 1 credit per 1–10 addresses/domain; Email Finder 1 credit when email is found; verification/enrichment rules depend on plan. Limits: Domain Search/Email Finder 15 req/s, 500/min; Verifier 10/s, 300/min; Discover 5/s, 50/min. Data Platform uses separate Search/Verification credits and annual billing; exact current amount must be verified at checkout/vendor. | Possible optional email adapter, not primary discovery nor proof of mandatory phone coverage. Confirm price/rights/country samples and impose tenant budget caps. |
| **Clay — workflow/marketplace comparator** | Public product describes 200+ providers, marketplace and waterfalls; this does not establish each downstream source may be redistributed by VSN. | Public pages reviewed do not establish embedding/resale rights to VSN end users. Each underlying partner's terms may govern; direct written confirmation required. | Public pricing checked 2026-10-05: Free includes 100 Data Credits/500 Actions monthly; Launch starts $185/mo; Growth starts $495/mo; Enterprise custom. These are Clay workspace prices, not VSN wholesale per-lead economics. | Keep as competitor/workflow benchmark, not an MVP source dependency. |
| **Custom user data/connectors** | Begin with schema-validated customer CSV; later add specific customer-authorized provider integrations. Fields/markets belong to each connector contract. | Require rights attestation and provider-specific terms. BYOK does not fix restrictions on third-party access/resale. Keep keys tenant-scoped; allowlist sources. No arbitrary scraper, undocumented endpoint or access-control bypass. | CSV has no provider charge; validation, storage, security and support still cost. Each connector displays its own credits/limits/cost before a run. | CSV first; then allowlisted connectors with a source contract record and kill switch. |

## Product and engineering controls

1. Preserve field-level provenance: provider, upstream source, source record ID, license/terms ID, retrieval time, freshness, confidence and transformation history.
2. Keep a source-eligibility catalog: countries, niches/taxonomy, fields, permitted storage/display/export, attribution, cost model, limits, credentials, deletion, reviewer status.
3. Before a run, show sources, fields, expected credits/cost and hard cap. Paid sources stay off until explicit opt-in and an eligible plan/budget.
4. Add provider and tenant budgets, rate controls, backoff, circuit breakers, usage ledger and source kill switch before paid launch.
5. Benchmark labeled sample searches by country/niche. Measure count, phone/email/address presence, duplicates, status, age, rights eligibility and cost. Show measured ranges; never promise a fixed lead count.
6. Prevent exports from bypassing source-specific storage/redistribution rules.
7. Store BYOK keys only as encrypted tenant-scoped secret references; never expose them in browser storage, logs, prompts or shared caches.
8. Obtain qualified review for ODbL, provider agreements, privacy/retention and downstream contact-data use before launch.

## Evidence gaps and gates

- No provider contacted; no reseller/redistribution agreement obtained.
- No head-to-head country/niche sample benchmark run.
- Public field descriptions do not establish completeness or accuracy.
- Exact cost per accepted, rights-eligible lead is unknown for Apollo, Hunter, Clay and custom providers.
- Hunter customer-facing rights and multi-tenant key conditions remain unverified.
- Overture licensing obligations need implementation against actual record source metadata and qualified review.
- Legal/compliance review is not complete; this is not legal advice.
- Launch countries, niche order, phone/email requirements, source funding model and monthly budget remain undecided.

## Official sources reviewed (accessed 2026-10-05 unless noted)

- Overture Places guide: https://docs.overturemaps.org/guides/places/
- Overture Place schema: https://docs.overturemaps.org/schema/reference/places/place/
- Overture attribution/licensing: https://docs.overturemaps.org/attribution/
- Overture multi-license release note: https://docs.overturemaps.org/blog/2025/09/24/release-notes/
- OSM copyright/license: https://www.openstreetmap.org/copyright/en
- OSMF API policy: https://operations.osmfoundation.org/policies/api/
- Overpass usage guidance: https://dev.overpass-api.de/overpass-doc/en/preface/commons.html
- Google Places API policies: https://developers.google.com/maps/documentation/places/web-service/policies
- Google Maps pricing: https://developers.google.com/maps/billing-and-pricing/pricing
- Apollo API terms: https://www.apollo.io/terms/api
- Apollo developer FAQ: https://docs.apollo.io/docs/developer-faqs
- Apollo reseller program: https://www.apollo.io/partners/api-reseller
- Hunter API: https://help.hunter.io/en/articles/1970956-hunter-api
- Hunter Data Platform API: https://help.hunter.io/en/articles/12149400-hunter-api-for-data-plans
- Hunter rate limits: https://help.hunter.io/en/articles/1971004-is-there-a-request-per-second-limit
- Hunter plans/credits: https://help.hunter.io/en/articles/11131690-pricing-plans-and-feature-faqs
- Clay pricing: https://www.clay.com/pricing
- Foursquare Places API pricing: https://foursquare.com/pricing/
- Foursquare Places delivery overview: https://docs.foursquare.com/data-products/docs/places-delivery-overview
- Foursquare Places API migration/pricing notice: https://docs.foursquare.com/developer/reference/upcoming-changes
- Foursquare Developer Console terms onboarding: https://docs.foursquare.com/developer/docs/developer-console-get-started
- Foursquare FSQ OS Places release notes: https://docs.foursquare.com/data-products/docs/fsq-os-places-release-notes
- Yelp Places getting started: https://docs.developer.yelp.com/docs/places-intro
- Yelp Places FAQ: https://docs.developer.yelp.com/docs/places-faq
- Yelp Places rate limits: https://docs.developer.yelp.com/docs/places-rate-limiting
