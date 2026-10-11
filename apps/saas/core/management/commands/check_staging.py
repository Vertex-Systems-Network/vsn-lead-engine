"""Fail-closed, read-only deployment readiness checks for the isolated SaaS service.

This checks local configuration and database state, *not* provider rights,
reverse-proxy behavior, source coverage, SMTP delivery, backups or launch consent.
No credentials, hostnames, queries or exception messages are printed.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.db.migrations.executor import MigrationExecutor


def configuration_issues(config):
    """Return public, secret-free reasons a staging environment is not ready."""
    issues = []
    hosts = {str(host).strip().lower() for host in config.ALLOWED_HOSTS}
    unsafe_hosts = {"", "*", "localhost", "127.0.0.1", "[::1]", "::1"}
    if config.DEBUG:
        issues.append("Disable SAAS_DEBUG before staging.")
    if len(config.SECRET_KEY) < 50:
        issues.append("Configure a strong, independently generated SAAS_SECRET_KEY.")
    # Both browser apps are served through one trusted staging HTTPS host. A
    # second host, dotted suffix, wildcard or port in Django's host allowlist
    # could expose account/session routes via an unintended proxy vhost.
    if (
        len(config.ALLOWED_HOSTS) != 1
        or len(hosts) != 1
        or any(
            host in unsafe_hosts
            or host.startswith(".")
            or any(char in "*/:" or char.isspace() for char in host)
            for host in hosts
        )
    ):
        issues.append("Set SAAS_ALLOWED_HOSTS to one exact non-local staging hostname.")
    if not all(
        (
            config.SECURE_SSL_REDIRECT,
            config.SESSION_COOKIE_SECURE,
            config.CSRF_COOKIE_SECURE,
            config.SECURE_CONTENT_TYPE_NOSNIFF,
        )
    ):
        issues.append("Require HTTPS, secure cookies and nosniff headers.")
    dashboard = urlsplit(config.WEB    # Accept exactly the canonical externally visible HTTPS URL, without an
    # explicit port (even :443), userinfo, encodings, URL parameters or an
    # alternate spelling of the staging hostname. Comparing to a constructed
    # constant also avoids URL parser exceptions from malformed inputs.
    dashboard = config.WEB_DASHBOARD_URL or ""
    expected_origin = f"https://{next(iter(hosts))}" if len(hosts) == 1 else None
    dashboard_valid = (
        isinstance(dashboard, str)
        and expected_origin is not None
        and dashboard == expected_origin + "/dashboard"
    )
 issues.append(
            "Route Django and Next through the same public HTTPS host; "
            "set SAAS_WEB_ORIGIN to that shared origin."
        )
    else:
        # Public form POSTs require the identical HTTPS origin. Never allow
        # broad suffix/wildcard trust or unrelated browser origins at staging.
        trusted = getattr(config, "CSRF_TRUSTED_ORIGINS", None)
        if not isinstance(trusted, (list, tuple)) or list(trusted) != [expected_origin]:
            issues.append("Trust only the exact shared HTTPS origin for browser CSRF.")
    if config.DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
        issues.append("Use PostgreSQL, not the disposable SQLite smoke database.")
    if (
        config.EMAIL_BACKEND != "django.core.mail.backends.smtp.EmailBackend"
        or not config.DEFAULT_FROM_EMAIL
        or config.DEFAULT_FROM_EMAIL.lower().endswith("@localhost")
    ):
        issues.append("Configure a real SMTP sender for password recovery.")
    if config.SAAS_LOCAL_FULFILMENT or "local-fixture" in config.SAAS_FULFILMENT_SOURCES:
        issues.append("Disable the synthetic development fulfilment signer/source.")
    if not config.SAAS_FULFILMENT_KEYS_FILE or "overture" not in config.SAAS_FULFILMENT_SOURCES:
        issues.append("Load owner-only fulfilment keys for the real Overture source.")
    return issues


def database_issues():
    """Read only: confirm PostgreSQL reachability and all migrations applied."""
    try:
        connection = connections["default"]
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            if cursor.fetchone() != (1,):
                return ["Database readiness query failed."]
        executor = MigrationExecutor(connection)
        if executor.migration_plan(executor.loader.graph.leaf_nodes()):
            return ["Database migrations are pending; deploy them before staging traffic."]
    except Exception:
        # Deployment exception text may contain connection credentials/hostnames.
        return ["Database connectivity or migration state could not be verified."]
    return []


class Command(BaseCommand):
    help = "Read-only SaaS staging preflight; never deploys or modifies the database."

    def handle(self, *args, **options):
        issues = configuration_issues(settings)
        if not issues:
            issues = database_issues()
        if issues:
            raise CommandError("SaaS staging preflight blocked:\n- " + "\n- ".join(issues))
        self.stdout.write(
            self.style.SUCCESS(
                "SaaS staging configuration and database checks passed. "
                "Not a deployment, source-rights, TLS-proxy, SMTP-delivery or launch certification."
            )
        )
