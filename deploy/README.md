# SaaS staging images (build-only)

This directory provides **host-neutral packaging**, not a deployed platform, public
launch approval, provider entitlement or production readiness certificate.
`SaaS Staging Image Build` builds the three images without secrets or registry
uploads. Full HTTP/TLS, SMTP delivery, backups, source-use rights and tenant
acceptance remain separate gates.

## Local image builds

Run from the **repository root** with Docker installed:

~~~sh
docker build --target api -f deploy/saas/Dockerfile -t vsn-stage-api:local .
docker build --target worker -f deploy/saas/Dockerfile -t vsn-stage-worker:local .
docker build --target web -f deploy/web/Dockerfile -t vsn-stage-web:local .
~~~

The API image serves Django WSGI with Gunicorn on port 8000; the web image
serves Next on port 3000. Containers use unprivileged users, do not copy
`.env` or fulfilment key files, and do not run migrations at startup.
The worker image includes Overture's pinned collector Python dependencies
plus Django and executes **one bounded `run_jobs --limit 25` batch**, then
exits. An external scheduler must invoke each batch; this image does not
promise persistent background execution, automatic recovery or quota completion.

## Host-provided configuration and services

Before actual staging, separately select and provision a private PostgreSQL
database, a trusted TLS reverse proxy, SMTP sender, secure secret store,
staging DNS, backup destination and a scheduler. The owner has not selected
these services and this PR never creates or connects to them.

- Give both Django processes the same independent `SAAS_SECRET_KEY`,
  PostgreSQL `SAAS_DB_*` values, `SAAS_DEBUG=0`, explicit
  `SAAS_ALLOWED_HOSTS`, `SAAS_WEB_ORIGIN=https://<shared-host>`,
  and the owner-only `SAAS_FULFILMENT_KEYS_FILE` mounted read-only to
  the same path. The key JSON must remain a regular 0600 file accessible
  to the container UID 10001; do not bake it into an image.
- SMTP is separately configured via `SAAS_EMAIL_HOST`,
  `SAAS_EMAIL_USER`, `SAAS_EMAIL_PASSWORD` and
  `SAAS_FROM_EMAIL`. Until a real sender is verified, password
  recovery is not production-ready.
- Provide the Next container with `SAAS_BACKEND_ORIGIN` and
  `SAAS_PUBLIC_ORIGIN` as explicit, trusted origins. The existing
  server transport requires HTTPS for remote origins. Both frontend and
  backend must appear on the **same public HTTPS hostname** so host-only
  cookies work, with path-based proxy routing. Do not assume arbitrary
  `X-Forwarded-Proto` is trusted: Django currently requires a separately
  reviewed proxy/TLS termination integration before staging can accept
  remote traffic.
- Do not publish the raw container ports to the internet. Restrict DB
  network access and outbound Overture endpoints. No paid source adapter,
  billing gateway or user signup is enabled by image creation.
- Use a separately reviewed backup/migration procedure before running
  `manage.py migrate --noinput` in an authorized staging deployment.
  Then run `manage.py check --deploy --fail-level WARNING` and
  `manage.py check_staging`; neither migrates, tests real email delivery
  or exercises actual proxy trust.

The API `/health/` endpoint is an unauthenticated liveness marker;
it does **not** prove Postgres access, worker/scheduler health or readiness.
Fail closed on any real deployment acceptance gap. Pin and review Docker
base-image digests before production release; tags alone are insufficient.
