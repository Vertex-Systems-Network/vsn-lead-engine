# SaaS Direction — Existing Lead Engine Capability Audit

Audit date: 2026-10-05 PKT  
Audited production ref: `main` at `ba7a8bcc224f429d5ab85d8cff076a3c9eccffa2`  
ANPOS work unit: `WU-SAAS-CURRENT-ENGINE-AUDIT`  
Method: Read-only inspection of repository files and workflow/configuration; no live production run, customer workbook, secrets, or provider account was accessed. This is a code/repository capability audit, not a security certification or proof of current data yield.

## Executive finding

The repository contains a mature, single-pipeline Python lead collection and operations engine. It does **not** contain an implemented multi-tenant SaaS application. Its collection, normalization/enrichment, deduplication and observability components are potential worker/domain assets, but they are coupled to one repository runtime configuration, GitHub Actions orchestration, Google Drive/Sheets output, and production-specific geography/category/phone rules.

Treat the SaaS as a separate product boundary in the design. Whether its code belongs in this repository or a dedicated application repository remains an owner decision. Do not expose the present production pipeline directly to SaaS users or change its operating constraints as part of discovery.

## Capability map

| Area | Verified in repository | SaaS gap / consequence |
|---|---|---|
| Runtime shape | Python package and CLI in `src/vsn_lead_engine/`; no HTTP/API server, browser UI, desktop packaging, or mobile application appears in the audited tree. `pyproject.toml` exposes `vsn-lead-engine` CLI. | Build a user-facing product/API and shared client contracts; keep the existing CLI pipeline isolated until an explicit boundary/design decision. |
| Geography and taxonomy | `config/runtime.json` has 56 configured geographies, exactly US/Canada validation, and 12 fixed categories. `config.py` rejects other countries, requires exactly 12 categories, requires a 1,000/category target, and rejects any mode other than `free`. | Country, niche, volume and source-mode choices cannot be safely made tenant-configurable by simply changing the current shared config. Needs tenant-scoped validated search definitions and per-job limits. |
| Collection sources | `sources/__init__.py` builds Overture and optional Overpass adapters. Overture is enabled in runtime config; Overpass is disabled and requires a configured endpoint, rejecting known public community instances for recurring commercial operation. No paid/BYOK/custom-provider adapter registry was found. | Source catalog, per-source country/field/rights/cost metadata, credential isolation, consent, budgets, kill switches and adapter contract are new work. Do not infer “free source” means unrestricted reuse or storage. |
| Lead normalization/enrichment | `models.py` defines one `Lead` data class with contact, location, website and source fields. `enrichment.py` performs bounded public-site contact discovery and phone validation. `website_status` is only a derived Listed/Missing value; the model does not express a general business operating status. | User field selection, business status taxonomy, field-level provenance/confidence/freshness and source-specific retention need design. Existing enrichment is not a paid enrichment provider integration. |
| Existing selection rules | Engine applies configured category/geography selection, requires a normalized phone for acceptance, handles duplicate checks and quality/scoring. | These are production rules, not demonstrated SaaS user-configurable filters. Define which filters are supported by each provider and separate platform safety/entitlement rules from user criteria. |
| Scheduling and jobs | `.github/workflows/lead-engine.yml` has a fixed cron `7 8-23 * * *`; Python scheduling gates it against the configured `Asia/Karachi` window and midnight/runtime safeguards. Runs are GitHub Actions workflow executions with CLI modes, supervision and recovery. | No per-user schedule records, durable SaaS queue, user timezone/DST lifecycle, subscription-aware scheduler, tenant fair-use or job history API is evidenced. GitHub Actions cron is not the SaaS scheduling backend. |
| Persistence and delivery | Google Drive/Sheets manages dated workbooks and a master registry (`sheets.py`). R2 stores the production cross-day dedupe fingerprint ledger (`packed_registry.py`). | Neither is a tenant-scoped product database or general lead search/filter/export API. Retention, deletion, access control, consistency and backup need product system design. |
| Identity and billing | `identity.py` only creates a versioned network User-Agent. No account, workspace, session, RBAC, subscription, entitlement or payment implementation was found. | Identity, tenant authorization, subscription lifecycle, entitlements and usage ledger are net-new foundations. |
| Admin and AI | Existing admin-like controls are repository/GitHub ANPOS workflows and operator CLI commands. No SaaS admin UI or AI runtime/tool integration was found in the application package/dependencies. | Tenant/provider operations console, audited support actions and bounded/evaluated AI assistance are net-new; AI must not spend or run paid sources without explicit controls. |
| Landing/marketing UX | No web/marketing frontend or visual asset application appears in this repo tree. | Landing site, product visuals, accessibility and motion system require a separate UX/frontend workstream. |
| Reliability foundations | Existing code has bounded retries/timeouts, health/yield telemetry, run supervision, dedupe recovery and extensive Python tests. Latest observed PR-head checks for this planning branch passed: Lead Engine validation/tests, AI Native Quality Gates, and CodeQL (commit `630206671fa89d891845ecc375ce2eff93f20541`). | These checks validate the existing repository and planning artifacts; they do not certify SaaS tenant security, billing correctness, provider rights, app UX or production readiness. |

## Reuse assessment

**Candidate to reuse behind a controlled worker boundary:** source adapter concepts, Overture query implementation subject to current terms and field rights, normalization, phone validation, taxonomy mapping, dedupe algorithms, bounded website enrichment, and health/yield patterns.

**Requires substantial refactor or a new product implementation:** tenant-aware domain/API, user-configurable search and status filters, source-policy catalog, per-tenant credentials/quotas, durable scheduled jobs, subscription entitlements and metering, user-facing storage/search/export, admin console, AI orchestration, and web/desktop/mobile/marketing clients.

**Must remain isolated until separately designed:** current free-only mode, US/Canada and 12-category constraints, phone-required acceptance rule, daily 1,000-per-category operating target, fixed Actions cron, existing Google workbook and R2 registry semantics, and production credentials/workflows. The target is an operating objective, not a SaaS yield guarantee.

## Boundary recommendation for system design

Evaluate two explicit options before coding:

1. Dedicated SaaS application repository/service; current repo remains the production engine and could later expose a versioned, authenticated worker/API contract.
2. A deliberately isolated monorepo product boundary with separate deployables, data stores, secrets, schedules, CI gates and ownership.

Do not merge customer tenancy into the existing global runtime configuration or reinterpret the current GitHub Actions workflow as the customer job scheduler. Compare operating cost, team ownership, deployment coupling, security isolation and reuse effort in the architecture decision record. This audit does not select either option.

## Verified references

- `config/runtime.json`, `src/vsn_lead_engine/config.py`
- `src/vsn_lead_engine/engine.py`, `scheduler.py`, `schedule.py`, `cli.py`
- `src/vsn_lead_engine/sources/__init__.py`, `sources/overture.py`, `sources/overpass.py`
- `src/vsn_lead_engine/models.py`, `enrichment.py`, `identity.py`
- `src/vsn_lead_engine/sheets.py`, `packed_registry.py`, `health.py`
- `pyproject.toml`, `.github/workflows/lead-engine.yml`, `DATA_SOURCES.md`
