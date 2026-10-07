# ADR-SAAS-002: Next.js frontend with the existing Django API

Status: accepted for additive development, 2026-10-08 PKT (2026-10-07 UTC).

## Context and decision

The owner requested milestone-sequenced development and prefers Next.js for the frontend. Use Next.js App Router with TypeScript and React under `apps/web/`. Retain Django 5.2 LTS/DRF, PostgreSQL and Django sessions as the backend authority. This partially supersedes **only the Web UI selection** in `ADR-SAAS-001-STACK-20261008.md`; it does not replace its backend, isolation, transaction, cost or external activation rules. Preserve tested Django forms during incremental migration.

Next.js fits the requested React frontend and server-rendered workspace pages. It is not claimed universally best: templates have lower deployment complexity; Vite/React would suit a client-only application but adds no clear advantage to the selected server-rendered workflow. No framework migration of the production collector or paid deployment service is required.

## Sequence and boundaries

1. Preserve M5 tenant/session/usage foundations and leave billing periods/payment/customer acceptance explicitly open.
2. Add M6 internal write-ahead operation identity and ambiguous-outcome reservation retention before any external adapter. Terminal receipts/settlement, durable scheduler and provider rights remain separate slices.
3. Begin M7 Next workspace/job/usage read workflow on that stable API. Continue native authenticated login/return/logout and draft/cancel migration with CSRF and cross-tenant tests, then lead results/export when backend contracts permit.
4. M8/M9 depend on complete preceding acceptance; no percentage makes those gates complete.

Initial Next reads forward only the Django session cookie from server components, use no shared cache and do not follow redirects. The backend checks membership on every request. Trusted environment configuration chooses a validated fixed origin; browser input cannot choose a target. UUID/path validation, bounded responses and generic failure states constrain the integration. No auth token enters localStorage, no public proxy is created and no mutation skips Django CSRF.

Development uses matching localhost hostnames on separate ports. Production routing/TLS/cookie/proxy/CSRF behavior requires explicit integration acceptance; no production host is selected. Deployment adds a Node runtime/build pipeline, reviewed npm dependency updates and a new monitoring surface. Reversal can route UI back to preserved Django pages without changing backend data or collector storage.

## Evidence and limits

Selected exact runtime versions: Next 16.4.0, React/ReactDOM 19.3.0; Node 24.19.0 used locally and in CI. Read version-matched Next documentation bundled under `node_modules/next/dist/docs` for installation, async cookies/params and external API data security. Official references: https://nextjs.org/docs/app/getting-started/installation and https://nextjs.org/docs/app/guides/data-security . Local build/type/lint/transport and disposable HTTP checks are recorded separately from CI. No browser, customer validation, security certification or production deployment is inferred from these checks. The ESLint 9/plugin compatibility limitation is recorded in `apps/web/README.md`.
