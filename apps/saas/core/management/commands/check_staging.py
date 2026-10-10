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
    if not hosts or hosts & unsafe_hosts:
        issues.append("Set SAAS_ALLOWED_HOSTS to explicit non-local staging hostnames.")
    if not all(
        (
            config.SECURE_SSL_REDIRECT,
            config.SESSION_COOKIE_SECURE,
            config.CSRF_COOKIE_SECURE,
            config.SECURE_CONTENT_TYPE_NOSNIFF,
        )
    ):
        issues.append("Require HTTPS, secure cookies and nosniff headers.")
    if not config.WEB_DASHBOARD_URL:
        issues.append("Configure SAAS_WEB_ORIGIN for the separate Next dashboard.")
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
