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
- Tenant-scoped jobs, saved scope/detail and settled/reserved/limit usage. Saved-job state filters reset continuation on change and persist through Next/First page links.
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

Native draft validation uses a bounded five-minute session handoff with the original signed retry identity, preserved inputs and field/error summary. Invalid authority or oversized inputs retain the Django fallback. Native `/account/sign-out` confirms CSRF-protected Django POST logout. Native login and cancellation-error screens remain open. See `docs/ai/SAAS-NEXT-VALIDATION-SIGNOUT-REVIEW-20261008.md` for session retention and acceptance limits.

Native Next sign-in uses explicit browser CSRF bootstrap and direct Django POST with generic fixed failure/limited notices. Native cancellation errors show current job state and require fresh review without issuing confirmation. Frontend origin is opt-in; standalone handlers retain their fallback. See `docs/ai/SAAS-NATIVE-LOGIN-CANCEL-REVIEW-20261008.md` for security, compatibility and acceptance limits.

## Public development preview

The Next root route `/` is a public marketing overview rather than an automatic
redirect into a private dashboard. Anonymous pages `/capabilities`, `/plans`
and `/data-handling` distinguish implemented development features from planned
or externally gated work. The plans page has no pricing/checkout and the data
handling page is expressly **not** a legally reviewed privacy policy. The app's
default metadata is `noindex,nofollow` until a separate public launch decision.
The dashboard still resolves tenant membership through Django, not marketing
navigation visibility.

The introductory workflow illustration is CSS and text only; no real business
records, metrics or unlicensed stock photographs are included. Mobile reflow,
keyboard focus and reduced-motion styles are implemented but do **not** replace
independent browser/WCAG, visual, performance, source-license and legal review.
The disposable HTTP integration smoke asserts public access, safe status labels,
no payment flow and absence of synthetic private tenant content.

## Exact active workspace identity

The Next workspace overview and member pages now read `GET /api/v1/workspaces/<uuid>/`
through the same session-only allowlisted server transport. The backend returns
only the member-authorized workspace name, timezone and existing serializer
metadata with no change endpoint. The UI validates the exact requested ID before
rendering and never reuses a workspaces-list page as an identity source. This
avoids showing another workspace's name when memberships change.

## Member visibility in the web dashboard

The workspace overview links to `/dashboard/workspaces/<workspace-id>/members`.
Only an authenticated owner or administrator may receive the existing Django
member-list API data; viewers, ordinary members and foreign-workspace actors
receive a generic denial. The Next route only performs a server-side GET,
validates a bounded page and the explicit role vocabulary, rejects duplicates,
and renders the returned UUIDs and roles in a labeled table. No names, email
addresses or role mutations are forwarded through the Next server. Role changes,
invitations and removals are **not** presented as operational Next features.
The selected workspace stays in the route, and Next does not make a second
authorization decision in place of Django. The HTTP smoke covers owner access,
foreign denial and the current session transport.
