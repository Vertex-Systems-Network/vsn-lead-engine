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

## All-page job state counts

The workspace overview reads `GET /api/v1/workspaces/<uuid>/job-summary/`
through the same server-only session transport as the authorized job list. The
backend groups every job belonging to that workspace (not only the first 25
results) by the eight existing job states. It returns no lead payload, personal
contact data, pricing or cross-tenant totals. Each state card links to the
already-protected status-filtered saved-search list; the contract verifies the
exact workspace UUID, status vocabulary, count integers and summed total.
Draft/job counts do **not** represent collected or accepted leads. The endpoint
has no client-selectable filters or mutating methods. PostgreSQL tests cover
viewer/owner membership, revocation, anonymous and foreign denial and all-page
counts; disposable Next/Django HTTP checks cover the visible count and links.

## Daily local-time preview

Workspace overview has a normal link to Django's member-scoped
`/workspaces/<uuid>/schedule-preview/` (through the fixed trusted
`SAAS_PUBLIC_ORIGIN`). It is deliberately a read-only Django GET page, not a
Next browser-origin write proxy. Users can inspect the next three possible
daily execution decisions for an IANA timezone and local time, including DST
folds/gaps, but cannot create, activate or dispatch a recurring schedule.
Django authorization, validation and calendar tests plus real Next-to-Django
HTTP link coverage are required; automatic scheduling is a later milestone.

## Save disabled daily plan from a draft

The Next saved-draft detail links to Django's existing-session route
`/workspaces/<uuid>/jobs/<draft-id>/daily-plan/`, with the trusted fixed backend
public origin. This is an explicit CSRF-protected Django form; Next does not
proxy a write or treat visible links as authorization. Owners/admins/members can
save an inactive plan based only on the persisted draft search and a chosen
local time. The backend enforces exact actor/job binding, idempotency and
`enabled=False`, with no recurrence or source dispatch. Real Next/Django HTTP
checks exercise the link and form; authorization and replay have PostgreSQL
regressions. No UI action here activates scheduling.

## Saved daily plans listing

The authenticated Next workspace route `/dashboard/workspaces/<uuid>/daily-plans`
shows a read-only table of persisted daily schedule plans and their actual
`enabled` state. The Django API `GET /api/v1/workspaces/<uuid>/daily-plans/`
requires current membership, returns minimal fields only, uses a stable bounded
25-row UUID continuation, and refuses unsupported query arguments or writes.
It never reveals plan search contents or lead/contact data. All roles can review
plans they are authorized to see, but none can activate or mutate them through
this page. A record marked enabled may only have been changed by a separate
operator pathway; a visible state is not evidence that a hosted recurring worker
is operating. No automatic collection, source request, or payment is activated.

## Daily plan detail review

Click **Review plan** in the read-only daily-plan list to inspect a specific
saved local time and normalized search scope at
`/dashboard/workspaces/<uuid>/daily-plans/<plan-id>`. The fixed server-only
transport requests only a verified workspace-member plan via the exact Django
GET endpoint; the typed contract bounds search arrays and required fields.
Current workspace identity and plan identity must match the route before
rendering. The screen offers no edit, enable, source dispatch or billing action.
The rendered values are saved preferences, not verified provider coverage,
accepted results, or an active recurring schedule.

## Owner/admin daily due diagnostics

The workspace overview links to
`/dashboard/workspaces/<uuid>/daily-diagnostics` for a read-only snapshot of
stored daily plans. Current Django workspace membership requires owner or admin
for the underlying `/api/v1/workspaces/<uuid>/daily-diagnostics/` API. The Next
server transport allows only this exact read and an optional UUID cursor;
returned plan entries, gate names, timestamps, dates and status vocabulary are
bounded at runtime. Viewers and foreign members get a generic denied state,
with no leakage of another workspace's plan IDs, source-search payload or
credentials. The UI explains that due candidates are **not** a runnable schedule,
no change/activation controls exist, and source rights, quotas, credentials,
operator release and actual deployment still need independent authorization.

## Pause future daily plan occurrences

When the **server** reports an enabled plan, its native Next detail screen links
to the fixed-origin Django pause-only confirmation. The Django action is
CSRF-protected, signed to current owner/admin identity and revision, and can
only change `enabled` to false. No direct Next mutation API is exposed. A
read-only plan or an ordinary member/viewer never gains permission by seeing a
link. Existing created jobs are not cancelled by this operation; the page
explicitly discloses that limit. Real Django/Next HTTP, owner/admin, foreign,
revocation, stale revision and PostgreSQL scheduler-race regressions cover the
feature. This is a **safety stop**, not recurring collection activation.

## Recorded daily plan occurrence and job history

The member-scoped Next page
`/dashboard/workspaces/<uuid>/daily-plans/<plan-id>/occurrences` shows an audited,
read-only list of previously persisted schedule decisions. An exact backend
session allowlist permits only the matching GET API and a strict local-date
continuation; typed validation checks plan/workspace IDs, unique descending
dates, status vocabulary, job IDs and skipped-day semantics. Where an occurrence
has an existing job, the UI links to the already tenant-protected job detail.
Neither viewing history nor pausing a plan erases those jobs or starts a worker.
The PostgreSQL tests cover actual materialization-and-pause visibility, a
29-day keyset history, foreign/revoked/anonymous access, unsupported fields and
write refusal; disposable Django/Next HTTP checks cover the page and tenant denial.

## Daily plan internal source readiness

The saved-plan detail links to
`/dashboard/workspaces/<workspace-id>/daily-plans/<plan-id>/readiness`.
Next uses the trusted server-only session for a fixed, exact Django GET path,
strictly validates blocked/internal-catalog-only status, five check names and
all independent unverified execution gates, then renders a human-readable
review. Django limits this snapshot to current workspace owners/admins;
viewers and foreign members receive generic denial without plan leakage.
This is deliberately a read-only diagnostic, not a live source-coverage,
commercial rights, credentials, quota or scheduler approval. No activate/submit
button is exposed. Disposable Django/Next HTTP tests cover the navigation.
