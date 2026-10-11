"""Read-only email identity preflight; never prints account values."""

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .models import User


class SignupEmailPreflightTests(TestCase):
    def test_readonly_check_accepts_distinct_users_and_legacy_blank_emails(self):
        User.objects.create_user(
            username="preflight-first",
            email="First@synthetic.invalid",
            password="synthetic-password",
        )
        User.objects.create_user(
            username="preflight-second",
            email="second@synthetic.invalid",
            password="synthetic-password",
        )
        User.objects.create_user(username="preflight-no-email", password="synthetic-password")
        User.objects.create_user(username="preflight-no-email-2", password="synthetic-password")
        output = StringIO()
        call_command("check_signup_emails", stdout=output)
        text = output.getvalue()
        self.assertIn("preflight passed", text)
        self.assertNotIn("synthetic.invalid", text)
        self.assertEqual(User.objects.count(), 4)

    def test_conflict_is_reported_without_addresses_or_mutating_users(self):
        User.objects.create_user(
            username="private-preflight",
            email="private-user@synthetic.invalid",
            password="synthetic-password",
        )
        with patch(
            "core.management.commands.check_signup_emails.has_recovery_email_collisions",
            return_value=True,
        ):
            with self.assertRaises(CommandError) as exc:
                call_command("check_signup_emails", stdout=StringIO())
        self.assertIn("Reconcile", str(exc.exception))
        self.assertNotIn("private-user", str(exc.exception))
        self.assertNotIn("synthetic.invalid", str(exc.exception))
        self.assertEqual(User.objects.count(), 1)

    def test_database_failure_never_reflects_connection_secrets(self):
        with patch(
            "core.management.commands.check_signup_emails.has_recovery_email_collisions",
            side_effect=RuntimeError("password=super-secret; email=private@invalid"),
        ):
            with self.assertRaises(CommandError) as exc:
                call_command("check_signup_emails", stdout=StringIO())
        self.assertIn("preflight unavailable", str(exc.exception))
        self.assertNotIn("super-secret", str(exc.exception))
        self.assertNotIn("private@invalid", str(exc.exception))
