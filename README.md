# VSN Lead Engine

Zero-paid-discovery-API lead engine for Vertex Systems Network.

## Runtime status

Real lead collection has been **APPROVED** by the user and the runtime gate is enabled.

The scheduled runner enforces a Google credential preflight. If the GitHub
secret `GOOGLE_SERVICE_ACCOUNT_JSON` is missing, the real run exits safely
without collecting or writing leads.

## Daily objective

- Countries: United States + Canada
- 12 categories
- 1,000 accepted unique phone-qualified leads/category/day
- 12,000/day target
- Registry-first writes
- Cross-day dedupe through a pluggable Registry backend
- FREE discovery mode: no paid Places/search API

The 12,000/day figure is a target, not a guarantee; output depends on source
coverage, public contact completeness, query execution, classification precision
and dedupe.


## SaaS milestone roadmap

<!-- ANPOS-CONTINUITY:BEGIN -->
### AI-Native continuity — verified development snapshot

- Verified plan snapshot: **2026-10-10**. Exact main SHA/PR come from git; at this snapshot main was `36348cb5` (PR #250). The v3 batch-evidence series (PRs #209–#238) is default-off, unreachable and **frozen** by CI stop-loss. Queued SaaS jobs can now be fulfilled end to end by `manage.py run_jobs` against the dev-only `local-fixture` source.
- Runtime mode: `degraded_no_verified_supervisor`. Persistent multi-agent dispatch is **not active**; sessions run as manifest role `single_session_developer`. Repository instructions do **not** keep a chat or Codex session running after host termination.
- Work units: **9 complete / 6 in progress / 1 blocked / 2 deferred / 3 not started (21 total)**. These are canonical `config/ai/project-state.json` work-unit states; the milestone percentages below are separate engineering estimates.
- Next work unit: `WU-SAAS-COLLECTION`. Priority (owner direction 2026-10-10: SaaS first, production quota not a current work item): staging deployment (external host/SMTP selection still required), independent public marketing UI in progress → M8 admin after web gates → M9 launch. Customer sign-up, submit, the Overture source and the non-DEBUG fulfilment signer are done. Do not activate payments, providers, production collections or a customer launch without verified gates.
- Continuation: **full ready frontier per invocation**; milestone/PR completion is a checkpoint, not an instruction to stop. Bounded by `config/runtime/budgets.json` (token, PR-per-invocation and CI-minute limits). Recoverable errors are AI-owned; human approval is reserved for genuine external authorization/consent/paid or irreversible commitments. CI runs `scripts/verify_readme_progress.py` (README/machine-state divergence) and `scripts/verify_product_progress.py` (frozen v3 modules, no chained non-code PRs).

<!-- ANPOS-CONTINUITY:END -->

Snapshot: **2026-10-08 PKT**, reconciled through protected feature `main` commit `2c422919` / merged PR #220. Scoped filters/CSV/receipt history and isolated normalized billing-evidence validation are verified through required checks, 375 PostgreSQL tests and 14-test Next/HTTP CI. Internal ledger reconciliation and validity guards are verified but default disabled; live payments/signers/consumers stay disabled. Production P01–P70 runtime remains separate. Bars are engineering estimates, not customer/provider/legal/deployment/launch certification.

| Milestone | Start date | Status | Progress |
|---|---:|---|---|
| M0 — Current engine audit and SaaS boundary | 2026-10-04 | Complete | `██████████` 100% |
| M1 — User/market and competitor desk research | 2026-10-04 | Desk research complete; external validation pending | `███████░░░` 70% |
| M2 — MVP options, scope and success criteria | 2026-10-05 | Reversible development boundary/defaults accepted; external market/commercial validation still open | `███████░░░` 70% |
| M3 — System, tenant and threat-model design | 2026-10-07 | System/threat, API/data and UX design contracts reconciled; runtime assurance tracked separately | `██████████` 100% |
| M4 — Technology stack and repository decision | 2026-10-07 | Development stack selected: Next.js + TypeScript frontend; Django 5.2 LTS + DRF + PostgreSQL backend, additive current-repo boundary; production vendors/hosting remain gated | `███████░░░` 70% |
| M5 — SaaS foundation: workspace, roles, entitlements and tenant-safety contracts | 2026-10-07 | Isolated Django session/workspace/draft API and initial migrations implemented; owner-safe membership lifecycle and bounded login protection implemented; persisted internal entitlements and atomic usage reservations added; explicit period/rollover and readonly window visibility verified by PostgreSQL concurrency and Next/HTTP CI; disabled internal event ledger, contiguous revisions and entitlement deadlines verified through PR #207 and 290 PostgreSQL cases; real payment/provider acceptance remains open | `████████░░` 85% |
| M6 — Source policy, adapters and job orchestration | 2026-10-07 | Source-policy identity and source-aware export authorization hardened; internal source-gated atomic job/reservation/outbox and pre-dispatch cancellation implemented; bounded pre-dispatch lease fencing and membership/entitlement/source rechecks implemented; operator-driven expiry/recovery implemented; internal write-ahead start/unknown ledger verified including PostgreSQL start/cancel races; signed terminal-receipt/whole-job accounting and usage bypass guards verified by PostgreSQL receipt races/migration CI; internal disabled daily occurrence/DST/bounded draft foundation verified by PostgreSQL duplicate/revocation CI; dual-attested internal accepted-result storage and atomic nonzero accounting verified with v1 compatibility and PostgreSQL races; real R2 signer/consumer/live adapter/customer scheduler remain open | `███████░░░` 75% |
| M7 — Lead web workflow, filters and export | 2026-10-08 | Native Next account/job/source/draft/cancel/correction, accepted results, guarded CSV/expiry and country/category/source selection verified. Readonly scoped receipt history, signed 25-row continuation and recovery metadata verified by 259 PostgreSQL tests and 14-test Next/HTTP CI (PR #202). Broader batch pagination, browser/customer/privacy/backup acceptance and deployment remain open | `████████░░` 86% |
| M7a — Public SaaS marketing preview | 2026-10-10 | Home, capabilities, provisional plans and data-handling pages implemented in Next; anonymous HTTP/SEO checks added, browser/WCAG/imagery/performance/launch review pending | `████░░░░░░` ~40% engineering-page indicator |
| M8 — Admin controls and bounded AI | 2026-10-07 | Not started | `░░░░░░░░░░` 0% |
| M9 — Production readiness, desktop/mobile and launch | 2026-10-07 | Not started | `░░░░░░░░░░` 0% |
| **Overall SaaS direction** | **2026-10-04** | **Design and contract implementation advancing; runtime, provider, validation and launch gates remain open** | **`████░░░░░░` ~52% engineering-plan indicator** |

Progress notes:
- 2026-10-10 M7 all-page job status summary: workspace-authorized `GET /api/v1/workspaces/<uuid>/job-summary/` groups **all** persisted jobs by the eight real states (including zeros), not just the current 25-row page. Next overview shows true totals with direct status-filter links and explicit distinction between job count and accepted leads. API refuses foreign/revoked/anonymous access, URL filters and all write methods; tenant isolation, no-store, transport and HTTP tests included. This is development code, not a deployed customer analytics or collection success claim.
- 2026-10-10 active workspace identity (M7): new authenticated, no-store, GET-only `/api/v1/workspaces/<uuid>/` requires current membership. Next overview and member screens show authorized workspace name/timezone rather than relying on hidden client state. Foreign, revoked and anonymous access and write-method refusal get dedicated tests; no tenant data rights or deployment state changed.
- 2026-10-10 workspace member visibility (M7): native Next page shows bounded, read-only member UUIDs/roles using Django owner/admin permissions, generic foreign-denial handling and an explicit session-only transport allowlist. The stale overview text now differentiates drafts from submitted jobs and does not claim production SaaS deployment. HTTP tenant-denial tests added; invitations/role changes in Next remain future work.
- 2026-10-10 public SaaS marketing (WU-SAAS-MARKETING): Next.js homepage replaces the former `/` → `/dashboard` redirect. Anonymous home, capabilities, unpriced plan concepts and data-handling pages use responsive styling, reduced-motion handling and honest implemented/planned/externally-gated status. HTTP integration asserts public access, safe claims and no private tenant data. This is not a public deployment or completed WCAG/browser/SEO certification.
- 2026-10-10 container packaging (M9 preparation; no deploy): host-neutral Docker image recipes for Django API, Next web and bounded Overture worker, with pinned serving dependencies, non-root runtime, secret-excluding build context and a separate build-only CI workflow. No registry publish, provider provisioning or reverse-proxy acceptance. See `deploy/README.md`.
- 2026-10-10 SaaS staging preflight (M9 preparation; no deploy): added fail-closed `manage.py check_staging` for non-DEBUG security, explicit hosts/Next origin, SMTP, real-source key configuration, read-only PostgreSQL connectivity and pending migrations. It does not replace live proxy, email-delivery, source-rights, backup or customer acceptance. No hosting/SMTP provider has been provisioned.
- Owner-selected Next.js UI is recorded in [ADR-SAAS-002](docs/ai/ADR-SAAS-002-NEXT-FRONTEND-20261008.md); backend auth/tenant authority remains Django. Percentages describe implemented engineering slices; browser/customer/deployment/release limits remain open.
- M0 is complete from repository audit evidence.
- 2026-10-10 job progress (M7): queued/running job pages refresh themselves (Next `router.refresh()` every 15 s for up to 30 min; Django `meta refresh`), and stop once the job finishes. 1 new test; the HTTP smoke checks the queued copy.
- 2026-10-10 password reset (M5): sign-up now requires a unique email; `/accounts/password-reset/` uses Django's one-time expiring reset tokens, gives the same answer for unknown addresses and is rate-limited per address and IP. Email goes to the console in debug and to SMTP when `SAAS_EMAIL_HOST` is set. Sign-in pages link to it. 4 new tests.
- 2026-10-10 production fulfilment signer (M6): `SAAS_FULFILMENT_KEYS_FILE` loads four distinct random keys from an owner-only JSON file (`manage.py generate_fulfilment_keys`), so `run_jobs` works without debug mode; only real sources (`overture`) are registered and the synthetic fixture can never run there. Live check: the `SaaS Overture Smoke` run on main fulfilled a real job with 10 Phoenix salon leads. 4 new tests; 473 SaaS tests pass.
- 2026-10-10 real Overture source (M6): `core.sources.OvertureSource` serves SaaS jobs from Overture Maps Places through the production collector's query code (lazy duckdb import; collector geographies; NANP-normalised phones; keeps searching past leads the workspace already has, bounded to 6 queries). Dev mode registers the local signer for `overture`; `seed_local_source --source overture` creates its policy. Manual `SaaS Overture Smoke` workflow fulfils a real job end to end. 5 new tests.
- 2026-10-10 self-service sign-up (M5/M7): `/accounts/sign-up/` and a native Next `/account/sign-up` page create the account, an owned workspace and an optional starter allowance (`SAAS_STARTER_ENTITLEMENT`), then sign the customer in. Rate-limited with the login buckets; on by default only in debug, production needs `SAAS_SIGNUP_ENABLED=1`. 7 new tests; the HTTP smoke signs up through the native form.
- 2026-10-10 customer submit (M7): draft jobs get a **Submit job** button (Next + Django) that reserves allowance and queues the job through `enqueue_job` with a revision-bound, separately salted confirmation; limits/plan/source refusals are explained without queueing. Job pages show queued/collecting/no-new-leads states. 7 new Django tests; the Next/Django HTTP smoke now submits through the native form.
- 2026-10-10 SaaS fulfilment worker (M6): `manage.py run_jobs` claims queued v2 intents, runs the source adapter, filters workspace duplicates and settles through the existing candidate + dual-attested acceptance path (or a no-effect receipt that releases the reservation). Dev-only: `SAAS_LOCAL_FULFILMENT=1` requires `SAAS_DEBUG=1`, keys derive from `SECRET_KEY` and attest only `local-fixture`; production verifier registries stay empty. 10 new tests; 450 SaaS tests pass on SQLite smoke.
- 2026-10-10 AI-plan stop-loss (no milestone change): v3 batch-evidence modules frozen, chained non-code PRs rejected, explicit token/PR/CI-minute budgets, `single_session_developer` role, slimmer agent context (README history moved to `docs/production/COLLECTOR-REFERENCE.md`), optional AI reviewer workflow.
- 2026-10-10 audit fixes (production collector, no milestone change): daily category-sheet appends now skip unique keys already on the tab so a retry after a timed-out-but-applied append cannot duplicate rows; Overpass city names are properly escaped in QL string literals; `.env.example` lists the real Google OAuth/R2 variables and no longer suggests a rejected public Overpass endpoint.
- M1 remains desk research only; no external interviews or customer-demand validation are counted as complete.
- M2 development sequencing/defaults are no longer blocked on technical owner confirmation; external market, pricing, provider-rights and launch decisions remain separate evidence/authorization gates.
- M3 evidence: PR #141 added the stack-neutral system/threat-model baseline, PR #145 added versioned API/data contracts, and PR #150 added the responsive MVP UX interaction contract.
- M4 evidence: PR #146 accepted the reversible development stack of Django 5.2 LTS + Django REST Framework + PostgreSQL with server-rendered progressive-enhancement UI and no new paid service activation.
- M5 evidence: PRs #147 and #149 hardened tenant-bound authorization. `apps/saas/` adds opt-in Django session identity, PostgreSQL models/migrations, transactional workspace ownership and an idempotent draft-job API. The isolated test suite covers cross-tenant reads/writes, stale membership, viewer denial, CSRF, validation, pagination and PostgreSQL duplicate-create concurrency; CI verifies forward/back/forward migration. PR #154 passed all required checks and PostgreSQL concurrency/migration CI. Member list/role-change/removal now re-resolve server membership, preserve the last owner under a workspace row lock, restrict ownership changes to owners and record transactional audit events. PR #155 passed PostgreSQL concurrent last-owner verification. The login form now applies atomic account/IP attempt caps using expiring keyed fingerprints, generic rate-limit responses and CSRF protection; deployment abuse/recovery review remains open. PR #156 passed PostgreSQL concurrent login-budget verification. Persisted internal entitlements default inactive/zero; usage reserve/settle/release services enforce tenant scope, replay conflicts and atomic hard caps. Signed billing activation/reconciliation remains unavailable; later PRs added internal outbox and explicit manual accounting periods. PR #157 passed PostgreSQL concurrent reservation-cap tests. The isolated quality workflow now includes pinned Ruff lint/format gates, compilation and the existing migration/security/concurrency suite. This is development foundation, not deployed persistence or SaaS production certification.
- M6/M7 evidence: PR #148 separated search eligibility from source-aware export authorization and added export-field policy tests. No provider adapter, customer scheduler, production SaaS database, billing gateway, or deployed web UI is claimed. Draft creation cannot dispatch providers or consume paid usage.
- Existing production collector, Google Sheets delivery and R2 dedupe authority remain isolated from the SaaS work. A separate compatible dependency maintenance change regenerates the reviewed Linux/CPython 3.12 hash locks to replace failed Dependabot #136; collection algorithms/configuration, production secrets and quota claims are unchanged.
- Project-specific tenant identity, draft idempotency and usage requirements now trace to delivered files, migrations, merged PRs and PostgreSQL tests in `config/traceability/requirements-traceability.json`; production/customer acceptance remains partial.
- Overall progress is an engineering planning/implementation indicator, not a claim of customer demand, source rights, coverage, legal compliance, paid-service activation, deployment or launch readiness.

## Production collector reference

Daily workbook model, sources, scheduler, R2 dedupe ledger, credentials, cutover certification and the full P01–P70 history live in [docs/production/COLLECTOR-REFERENCE.md](docs/production/COLLECTOR-REFERENCE.md). Data-source licensing notes are in [DATA_SOURCES.md](DATA_SOURCES.md).
