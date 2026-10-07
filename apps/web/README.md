# Next.js workspace frontend

Isolated Next.js 16.4 App Router, React 19.3 and TypeScript app. Django/DRF remains the authority for sessions, workspace membership, roles, jobs and usage. No collector dependencies or stores are used. Exact npm versions and a lockfile are committed.

## Run locally

Use Node 24.19 and the separately configured development Django app at `http://localhost:8000` (see `../saas/README.md`). From this directory:

```sh
npm ci
cp .env.example .env.local
npm run dev
```

Open `http://localhost:3000/dashboard`. Set `SAAS_WEB_ORIGIN=http://localhost:3000` in the Django development process to return automatically after login/logout. Sign in uses the Django account form. Without that optional setting, return to the dashboard manually. Both processes must use **localhost**, not mixed localhost/127.0.0.1 hosts: Django's HTTP-only `sessionid` cookie is shared across localhost ports in this development setup. No cross-origin browser API requests or weakened Django CSRF configuration are required. Draft and cancellation screens now render in Next and submit directly to the existing Django handlers with masked CSRF and signed bound tokens. Source configuration now has a bounded native Next screen. Missing form cookies use the account session-check link.

`SAAS_BACKEND_ORIGIN` is trusted server-only configuration for API reads. `SAAS_PUBLIC_ORIGIN` selects links to Django pages. These must be origin-only URLs without credentials, paths, query or fragment; remote origins require HTTPS. Defaults are localhost:8000 for development only. For production, select explicit HTTPS origins; configure a reviewed shared public origin/reverse proxy routing `/dashboard` to Next and `/accounts`, `/api/v1`, `/workspaces` to Django. Cookie scope, TLS, forwarded headers and CSRF origin checks need deployment integration tests before release. Fixed login/logout return and confirmation are verified over localhost HTTP, not a production proxy. This app does not provision that proxy or deployment.

## Delivered

- Session-authenticated workspace dashboard with bounded pagination.
- Tenant-scoped jobs, saved scope/detail and settled/reserved/limit usage.
- Parallel job/usage reads, loading/error/empty/access-denied states, semantic tables, skip link, focus styles and responsive CSS.
- Server-only GET transport with fixed API path allowlist, validated trusted origin, session cookie only, no shared cache, no redirects, five-second timeout and bounded JSON responses. No backend errors or credentials are logged/rendered.
- Native read-only source configuration with empty/unknown/truncated metadata states, omitted evidence/controls and explicit limits on configuration claims.
- Optional trusted fixed dashboard return after Django login/logout, with an authenticated CSRF POST logout confirmation link from Next.
- Native draft and confirmed pending cancellation screens use private Django form-context reads and direct HTML POST to fixed Django action URLs. Invalid submissions open its existing validation forms. Successful submissions return to configured Next detail paths.
- Only form-context reads forward a bounded CSRF cookie with the session; ordinary reads remain session-only. The explicitly configured frontend origin is the sole added Django CSRF trusted origin; no wildcard trust or Next write proxy. Viewer links never imply permission.

## Checks

```sh
npm run lint
npm test
npm run build
npm run typecheck
# With the isolated SaaS Python dependencies installed:
python test/integration_smoke.py
```

The HTTP test creates its own temporary SQLite database, synthetic accounts/workspaces and local servers. It checks real Next rendering against Django API/session data, tenant denial, pagination presence, usage/detail contracts and anonymous/cache isolation. It never uses configured customer/production databases. PostgreSQL concurrency is separately verified by SaaS Quality. Browser interaction, visual/responsive verification, WCAG assessment, native Next account forms/native mutation error rendering and production proxy acceptance and customer acceptance are pending.

ESLint 9 is pinned because the current React/a11y plugin peer ranges do not accept ESLint 10. npm marks ESLint 9 unsupported; replacing those compatible plugins or adopting a maintained lint toolchain is required before production approval. Runtime/build dependencies have independent update review through Dependabot; a successful build is not a security certification.
