# Native Next mutations: delivered boundary and next slice

PR #180 delivered native Next draft/cancellation screens and bounded Django form contexts. PR #181 delivered read-only source configuration; PR #182 delivered saved-job state filtering and retained pagination. Django retains session/tenant/role, signed draft idempotency and revision-bound cancellation authority. Successful direct HTML POSTs return to fixed configured Next job paths. Invalid input currently renders the existing escaped Django form with validation errors; it is not yet native Next error handling.

## Delivered controls

- Exact authenticated draft/cancellation context GET paths issue masked CSRF and signed actor/workspace/job/revision-bound tokens only after current authorization checks. Responses are private and uncached.
- Next transport forwards a validated CSRF cookie only to those exact paths. Other reads forward session only; origin/path, response size, timeout and redirect constraints remain enforced.
- Missing CSRF cookies require explicit authenticated reseeding. Native forms submit to fixed Django actions; one validated frontend origin supplies CSRF trust, with no wildcard or request-selected destination.
- Real HTTP CI covers password login, cookies, Origin/CSRF, duplicate/conflicting draft submissions, viewer/tenant denial, stale cancellation and pending release-once. PostgreSQL concurrency, migration/settings and Next lint/format/type/build gates pass.

## Next implementation: native validation and account flows

1. Choose a bounded validation handoff that keeps submitted search values out of URL query strings, arbitrary redirects and shared cache. Retain Django's existing POST validation and CSRF checks. Any server-side handoff must expire, be bound to the current actor/workspace and use bounded allowlisted fields/error messages; do not serialize credentials or authority-bearing backend internals.
2. Render semantic field errors and an error summary on Next, preserving entered values and the original draft retry identity. Correcting a rejected payload may create one draft; replaying an accepted identity with changed content remains a conflict. Recheck membership before rendering or resubmitting; a handoff cannot authorize a mutation.
3. Handle missing/expired handoff, lost session, rotated CSRF, role revocation and stale cancellation explicitly. Keep generic tenant/auth failures and the backend fallback usable. Do not invent fresh authority from browser-supplied status, roles or counters.
4. Design native account/login/logout context separately from authenticated draft context. Anonymous login requires its own CSRF-cookie/bootstrap and bounded abuse-control review. Never pass passwords through validation handoff storage or render them back; existing Django login budgets and generic failure behavior remain authoritative.
5. Verify real Django/Next HTTP correction/replay/conflict, escaping, expiry, cross-actor/workspace attempts and trusted-origin failures, then PostgreSQL gates. Browser keyboard, focus, errors and responsive checks require a usable browser runtime. Production shared-origin TLS/proxy/cookie acceptance remains separate.

Current implementation surfaces: `apps/saas/core/form_context.py`, `core/forms.py`, `core/cancellation_forms.py`, `core/views.py`, `core/jobs.py`, `apps/web/lib/transport.mjs` and `apps/web/test/integration_smoke.py`. Signed billing events and accepted phone-qualified results/export remain independent later slices. No provider, payment or scheduler activation is needed for native validation work.
