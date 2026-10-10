"""Staging preflight tests do not require network, credentials or a real database."""

from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from .management.commands.check_staging import configuration_issues, database_issues


def secure_config(**changes):
    baseline = {
        "DEBUG": False,
        "SECRET_KEY": "a" * 64,
        "ALLOWED_HOSTS": ["saas.staging.example"],
        "SECURE_SSL_REDIRECT": True,
        "SESSION_COOKIE_SECURE": True,
        "CSRF_COOKIE_SECURE": True,
        "SECURE_CONTENT_TYPE_NOSNIFF": True,
        "WEB_DASHBOARD_URL": "https://saas.staging.example/dashboard",
        "DATABASES": {"default": {"ENGINE": "django.db.backends.postgresql"}},
        "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "DEFAULT_FROM_EMAIL": "no-reply@staging.example",
        "SAAS_LOCAL_FULFILMENT": False,
        "SAAS_FULFILMENT_SOURCES": ("overture",),
        "SAAS_FULFILMENT_KEYS_FILE": "/private/keys.json",
    }
    return SimpleNamespace(**(baseline | changes))


class ConfigurationPreflightTests(SimpleTestCase):
    def test_explicit_staging_configuration_is_eligible_for_database_check(self):
        self.assertEqual(configuration_issues(secure_config()), [])

    def test_rejects_local_dev_signer_sqlite_and_insecure_transport(self):
        issues = configuration_issues(
            secure_config(
                DEBUG=True,
                ALLOWED_HOSTS=["localhost", "*"],
                SECRET_KEY="short",
                SECURE_SSL_REDIRECT=False,
                SESSION_COOKIE_SECURE=False,
                DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3"}},
                SAAS_LOCAL_FULFILMENT=True,
                SAAS_FULFILMENT_SOURCES=("local-fixture",),
                SAAS_FULFILMENT_KEYS_FILE="",
            )
        )
        self.assertGreaterEqual(len(issues), 7)
        self.assertTrue(any("PostgreSQL" in issue for issue in issues))
        self.assertTrue(any("synthetic" in issue for issue in issues))
        self.assertTrue(any("fulfilment keys" in issue for issue in issues))

    def test_cross_origin_dashboard_cannot_share_host_only_sessions(self):
        issues = configuration_issues(
            secure_config(WEB_DASHBOARD_URL="https://other.staging.example/dashboard")
        )
        self.assertEqual(len(issues), 1)
        self.assertIn("same public HTTPS host", issues[0])

    def test_refuses_console_email_and_missing_next_origin(self):
        issues = configuration_issues(
            secure_config(
                WEB_DASHBOARD_URL=None,
                EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
                DEFAULT_FROM_EMAIL="no-reply@localhost",
            )
        )
        self.assertEqual(len(issues), 2)

    def test_configuration_failure_never_queries_database(self):
        with (
            patch(
                "core.management.commands.check_staging.configuration_issues",
                return_value=["Incomplete staging settings."],
            ),
            patch("core.management.commands.check_staging.database_issues") as database,
        ):
            with self.assertRaisesMessage(CommandError, "Incomplete staging settings."):
                call_command("check_staging", stdout=StringIO())
            database.assert_not_called()

    def test_command_reports_only_narrowly_verified_checks(self):
        output = StringIO()
        with (
            patch(
                "core.management.commands.check_staging.configuration_issues",
                return_value=[],
            ),
            patch("core.management.commands.check_staging.database_issues", return_value=[]),
        ):
            call_command("check_staging", stdout=output)
        self.assertIn("checks passed", output.getvalue())
        self.assertIn("Not a deployment", output.getvalue())


class DatabasePreflightTests(SimpleTestCase):
    def test_readonly_query_and_migration_plan(self):
        with (
            patch("core.management.commands.check_staging.connections") as connections,
            patch("core.management.commands.check_staging.MigrationExecutor") as executor,
        ):
            connection = connections.__getitem__.return_value
            connection.cursor.return_value.__enter__.return_value.fetchone.return_value = (1,)
            executor.return_value.loader.graph.leaf_nodes.return_value = [("core", "0001")]
            executor.return_value.migration_plan.return_value = []
            self.assertEqual(database_issues(), [])
            connection.cursor.return_value.__enter__.return_value.execute.assert_called_once_with(
                "SELECT 1"
            )
            executor.return_value.migration_plan.return_value = [object()]
            self.assertIn("migrations are pending", database_issues()[0])

    def test_does_not_expose_database_exception_details(self):
        with patch("core.management.commands.check_staging.connections") as connections:
            connections.__getitem__.side_effect = RuntimeError("password=private-secret")
            issues = database_issues()
        self.assertEqual(len(issues), 1)
        self.assertNotIn("private-secret", issues[0])
