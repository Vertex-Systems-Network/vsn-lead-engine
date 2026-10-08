# Native Next draft validation and sign-out review

Bounded invalid draft submissions now return to the native Next form with entered values, a linked error summary and field errors. Django still validates the POST and performs transactional draft creation. Native sign-out confirmation posts directly to the existing Django logout handler. There is no Next mutation proxy, new dependency, migration, provider execution or commercial activation.

## Validation handoff

With configured WEB_DASHBOARD_URL, a rejected draft with valid original signed draft authority stores allowlisted values/errors in the existing server-side Django session and redirects 303 to the fixed workspace form with a random UUID handle. The URL contains no search values or errors. Each handoff has a five-minute read expiry; at most three are retained per session, and expired entries are pruned on later writes. Physical session rows follow the existing Django session expiry/cleanup policy: five minutes is a read deadline, not a guaranteed physical erasure deadline. Production session encryption, cleanup and retention acceptance remain deployment gates.

Reads recheck current membership/role, actor/workspace/session ownership, expiry, original signed nonce and valid browser CSRF cookie. They are private/no-store, emit a freshly masked CSRF token and do not consume or extend handoffs. Correction retains the original retry identity; accepted replay returns the same job and changed accepted content renders conflict. Unknown POST fields and raw CSRF/password values are never stored. Invalid/expired draft authority, oversized input, repeated scalar fields and unbounded errors retain the escaped Django fallback rather than truncate values or mint replacement authority. Supported checkbox selections and scalar values are restored; invalid unsupported choices remain validation errors and must be corrected using supported controls.

Concurrent requests saving the same session may evict or lose a handoff through ordinary session last-write behavior. Missing context fails closed; this is not a transactionally ordered multi-tab feedback queue. Draft idempotency/authorization still uses the existing database service and does not depend on handoff persistence.

## Sign-out and frontend review

Exact `/api/v1/account/sign-out-form/` context requires an authenticated session and existing validated CSRF cookie; it exposes only a masked token. Native `/account/sign-out` offers explicit POST confirmation and a non-mutating Keep working link. GET logout, missing CSRF and untrusted Origin remain denied; successful logout invalidates the session and clears its feedback. Only exact new context paths receive validated CSRF-cookie forwarding. No arbitrary account API/proxy path is accepted.

React review: server components only, bounded DTO validation, no shared request state/client effects, escaped values/messages, semantic fieldsets/labels, field error associations and summary links; form navigation disables speculative prefetch. Native account login, native cancellation-error handling, browser focus/responsive/WCAG/customer assessment and shared-origin TLS/proxy acceptance remain open.

Validation gates: six handoff tests cover correction/replay/conflict, expiry, session/actor/workspace/role isolation, entry caps, secret omission, fallback, cookie rotation and nonce expiry. Three account tests cover read-only context, explicit reseeding, CSRF/Origin/method denial and session invalidation. Real Django/Next HTTP exercises escaped preserved errors, correction with original nonce, conflict screen and native sign-out. Final-head PostgreSQL and required repository/Next CI remain merge gates.

Local final checks: 154 Django cases (138 passed/16 explicit PostgreSQL-only skips), root 376 passed/1 skipped/28 subtests, ANPOS, Ruff lint/format, no migration drift, Next lint/format/eight transport tests/build/type and the real disposable HTTP correction/conflict/native logout flow passed. SQLite does not certify row-lock concurrency; exact-head PostgreSQL CI remains required.

Verified merge evidence: PR #184 merged at bec879cb7b7ed925e64a623d2ce197c7c590eafa; head 034cd99a40dbd3c2254e1a3a832e01f05f56501c passed required checks/Actions CodeQL, PostgreSQL 37755784470 (154 tests/migration/settings) and Next/HTTP 37755784437 (eight transport tests, escaped feedback/correction/replay/conflict/missing-context recovery and native sign-out).
