# Ready next slice: native Next draft and cancellation screens

Implementation plan after verified PR #178, not delivered API/UI. Preserve Django session/tenant/role, signed draft idempotency and revision-bound cancellation authority. Start with draft and pending cancellation; account forms, accepted leads/export and automatic scheduling are independent later slices.

## Proposed boundary

1. Add narrowly scoped authenticated GET form-context endpoints for a workspace draft and an existing draft/queued job cancellation. Return only validated bounded form data, short-lived user/workspace/job/revision-bound tokens, masked CSRF token and current server-resolved capabilities. Recheck current membership before issuing context; keep private/no-store responses. Never expose session-cookie values, raw CSRF secrets, arbitrary backend URLs or financial authority.
2. Extend server-only Next transport only for those exact context paths. Any CSRF-cookie forwarding is limited to form-context reads and must validate the value. Keep session-only ordinary reads, fixed trusted origins, response-size/timeout bounds, no redirects and no shared cache. A missing CSRF cookie must use an explicit reseeding/login path, rather than bypassing CSRF or inventing a token.
3. Render native semantic Next form controls for the existing normalized US/CA/phone search contract. A signed draft nonce carries the stable retry key. Native cancellation must show pending-only state and a confirmation bound to the exact server job revision; browser-supplied role/status/usage never authorizes writes.
4. Prefer progressive HTML form submission directly to a narrow existing Django mutation handler, with fixed server-configured action URLs and retained backend form validation. For local separate ports, any added CSRF trusted origin must be an explicit validated configured frontend origin and receive an independent regression review; never allow wildcard/request-selected origins. Production shared-origin routing still needs TLS/cookie/proxy acceptance. A server-action alternative needs a separate origin/CSRF/session-forwarding review and must not create a general public proxy.
5. Successful mutations may return only to a fixed configured Next job path built from server-resolved UUIDs. Preserve generic error/role/tenant failures, stable replay and visible validation errors; do not treat a redirect or requested result limit as completed collection. Keep the Django forms available while native flows are verified.

## Required verification

- Real password login/CSRF cookie through Django; GET context and rendered Next controls for the actual member.
- Valid form submission creates one normalized draft, duplicate submission creates none extra, changed payload conflicts. Viewer, stale role, forged/expired nonce and foreign IDs fail without writes.
- Confirmed cancellation releases only pending capacity once; wrong revision, expired token, started/unknown operations and replay conflicts stay safe.
- Missing/mismatched CSRF cookie/token and untrusted Origin fail. No wildcard trust, cross-user cached context, arbitrary fetch target or session/token logging.
- Real PostgreSQL concurrency/migration/security checks and Next lint/format/type/build/HTTP flow. Browser keyboard, focus/error handling and responsive acceptance require a usable browser runtime and must not be inferred from HTTP rendering.

Current controls: `core/forms.py`, `core/cancellation_forms.py`, `core/views.py`, `core/jobs.py`, `apps/web/lib/transport.mjs`, and the real auth/CSRF cookie jar in `apps/web/test/integration_smoke.py`. No provider, billing or queue consumer activation is needed for this slice.
