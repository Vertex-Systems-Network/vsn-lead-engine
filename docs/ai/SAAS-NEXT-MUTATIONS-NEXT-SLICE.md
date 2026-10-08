# Native Next mutations: delivered boundary and next slice

PR #180 delivered native draft/cancellation controls and bounded Django contexts. PR #181 delivered read-only source configuration; PR #182 delivered saved-job state filtering/pagination. PR #184 now delivers native draft validation/correction/conflict, missing-feedback recovery and native sign-out confirmation. Django retains session/tenant/role, CSRF, signed idempotency, cancellation revision and login abuse-control authority.

## Delivered controls

- Native HTML forms post to fixed Django actions. Successful drafts/cancellations return 303 to configured Next job paths; sign-out confirms the existing Django POST logout. No Next mutation proxy or request-selected backend/redirect origin.
- Rejected bounded drafts with valid authority use five-minute session/actor/workspace-bound feedback with the original draft identity. At most three entries; reads do not consume/refresh context. Invalid authority/oversized input retains Django fallback. Physical session retention differs from the read deadline; see the validation/sign-out engineering review.
- Exact authenticated form contexts return bounded public data, masked CSRF and existing signed tokens. Validated CSRF-cookie forwarding applies only to their exact paths; ordinary reads remain session-only, fixed-origin/path, bounded, private and uncached.
- PostgreSQL, migration/settings, Next lint/format/type/build/transport and real HTTP auth/CSRF/role/tenant/replay/correction/conflict/sign-out checks pass. Full browser/deployment acceptance is separate.

## Next: native cancellation errors

1. Present bounded generic cancellation errors alongside the current server job state. A stale revision must require reviewing current details and a fresh explicit confirmation; a feedback read must never auto-cancel, auto-retry or refresh mutation authority.
2. Bind any error handoff to session/actor/workspace/job with expiry and bounded storage. Preserve pending-only rules; running/completed/unknown operations cannot become cancellable through UI recovery. Invalid/expired confirmation may retain Django fallback until an independently reviewed native recovery exists.
3. Verify stale confirmation, changed role, foreign job, expired feedback and started/terminal state, plus release-once/idempotent replay and real PostgreSQL races. Browser focus/keyboard/responsive validation remains necessary.

## Next: native anonymous login

1. Define explicit anonymous CSRF bootstrap and cookie propagation before rendering a native form. Server-component reads cannot silently seed browser cookies; use a narrow reviewed bootstrap path rather than bypassing CSRF or using the authenticated draft context.
2. Post passwords only to the existing fixed Django login handler. Preserve account/IP attempt budgets, trusted connection-address policy, generic credential/rate-limit failures, session rotation and the fixed dashboard return. Never store or render passwords in feedback, query strings or logs.
3. Keep user/account identifiers out of error URLs and review any bounded anonymous feedback mechanism separately. Test missing/mismatched/rotated CSRF, wrong Origin, failed login, attempt exhaustion, success/rotation and old-session denial with real HTTP and PostgreSQL budgets.

Production shared-origin TLS/proxy/cookies, session encryption/retention/cleanup and browser/customer acceptance remain open. Signed billing events and phone-qualified accepted results/export are independent later slices. These frontend steps do not require provider, payment or scheduler activation.
