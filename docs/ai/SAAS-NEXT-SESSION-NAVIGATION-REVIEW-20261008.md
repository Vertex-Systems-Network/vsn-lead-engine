# Next session navigation integration

M7 continuation keeps Django as the only identity/session and CSRF authority. Next gains a sign-out link to an authenticated Django confirmation form. GET never logs out; the form submits a CSRF-protected POST to the existing Django LogoutView, which invalidates the session before returning to the dashboard.

`SAAS_WEB_ORIGIN` is optional trusted Django startup configuration. When set, default login/logout return goes to its fixed `/dashboard` path. Credentials, paths, query/fragment delimiters, control characters and non-HTTP(S) URLs are rejected; HTTP is allowed only for loopback in debug mode. Production requires HTTPS. An absent origin preserves standalone Django redirect defaults. No request can add hosts to Django's safe `next` redirect allowlist; Django retains its own same-host relative-next behavior and rejects attacker-selected external hosts. Configuration does not provision TLS, proxy routing or CSRF trust.

The actual localhost HTTP test logs in through Django with a real password/CSRF token and cookie jar, follows the fixed return to Next, renders the assigned workspace, visits confirmation and posts logout. It verifies GET/missing-CSRF rejection, then checks anonymous Next rendering and rejection of the old session cookie. Unit regressions cover malicious origins, external `next`, same-host relative `next`, anonymous confirmation and cross-origin logout even with a token. Existing login rate limits remain in effect.

React review: both edited components remain server components, use plain accessible anchor navigation, forward no secrets as props, add no client effects/bundles and keep authenticated reads without shared caches. Lint, formatting, six transport tests, build/type and real HTTP checks run before publication and in Web Quality. Browser visual/keyboard/customer acceptance is still pending; HTTP is not a browser assessment.

Native Next login/draft/cancel forms and a reviewed production shared-origin cookie/TLS/CSRF deployment remain future work. This change improves navigation across the existing Django forms; it does not claim that those forms have migrated to Next or that a deployment is live.
