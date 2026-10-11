from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from .models import Entitlement, LoginBucket, Membership, User, Workspace

STARTER = {"lead_limit": 100, "job_limit": 10, "provider_call_limit": 10, "export_limit": 10}
PASSWORD = "a-long-unusual-passphrase-42"


@override_settings(SAAS_SIGNUP_ENABLED=True, SAAS_STARTER_ENTITLEMENT=STARTER)
class SignUpTests(TestCase):
    url = "/accounts/sign-up/"

    def post(self, **changes):
        data = {
            "username": "new-customer",
            "email": "owner@acme.example",
            "password1": PASSWORD,
            "password2": PASSWORD,
            "workspace_name": "Acme Leads",
            **changes,
        }
        return self.client.post(self.url, data)

    def test_sign_up_creates_owner_workspace_starter_allowance_and_session(self):
        self.assertContains(self.client.get(self.url), "Create account")
        response = self.post()
        self.assertEqual((response.status_code, response.url), (303, "/"))
        user = User.objects.get(username="new-customer")
        membership = Membership.objects.get(user=user)
        self.assertEqual(membership.role, "owner")
        self.assertEqual(membership.workspace.name, "Acme Leads")
        entitlement = Entitlement.objects.get(workspace=membership.workspace)
        self.assertTrue(entitlement.is_current)
        self.assertEqual(entitlement.lead_limit, 100)
        self.assertEqual(self.client.get("/api/v1/workspaces/").status_code, 200)

    def test_default_workspace_name(self):
        self.post(workspace_name="")
        self.assertEqual(Workspace.objects.get().name, "new-customer's workspace")

    @override_settings(SAAS_STARTER_ENTITLEMENT={})
    def test_no_starter_allowance_when_unconfigured(self):
        self.post()
        self.assertTrue(Workspace.objects.exists())
        self.assertFalse(Entitlement.objects.exists())

    def test_invalid_and_duplicate_sign_ups_create_nothing(self):
        self.assertEqual(self.post(password2="different-passphrase-99").status_code, 400)
        self.assertEqual(self.post(password1="123", password2="123").status_code, 400)
        self.assertFalse(User.objects.exists())
        self.post()
        self.client.logout()
        self.assertEqual(self.post(username="NEW-customer").status_code, 400)
        self.assertEqual(
            self.post(username="other-customer", email="OWNER@acme.example").status_code, 400
        )
        self.assertEqual(self.post(username="no-email", email="").status_code, 400)
        self.assertEqual((User.objects.count(), Workspace.objects.count()), (1, 1))

    @override_settings(WEB_DASHBOARD_URL="http://localhost:3000/dashboard")
    def test_native_sign_up_redirects_to_dashboard_or_notice(self):
        bad = self.post(native_signup="1", password2="different-passphrase-99")
        self.assertEqual(bad.url, "http://localhost:3000/account/sign-up?notice=invalid")
        good = self.post(native_signup="1")
        self.assertEqual(good.url, "http://localhost:3000/dashboard")
        self.client.logout()
        taken = self.post(native_signup="1", username="New-Customer")
        self.assertEqual(taken.url, "http://localhost:3000/account/sign-up?notice=taken")
        taken_email = self.post(native_signup="1", username="another", email="Owner@Acme.example")
        self.assertEqual(taken_email.url, "http://localhost:3000/account/sign-up?notice=taken")

    def test_database_rejects_mixed_case_duplicate_email_even_outside_signup(self):
        User.objects.create_user(
            username="direct-first", email="Contact@Acme.Example", password=PASSWORD
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create_user(
                    username="direct-second", email="contact@acme.example", password=PASSWORD
                )
        self.assertEqual(User.objects.count(), 1)

    def test_legacy_blank_email_accounts_can_coexist(self):
        User.objects.create_user(username="first-no-email", password=PASSWORD)
        User.objects.create_user(username="second-no-email", password=PASSWORD)
        self.assertEqual(User.objects.filter(email="").count(), 2)

    def test_signup_race_rolls_back_new_workspace_and_returns_generic_conflict(self):
        from .signup import register

        for native, email in (
            (False, "race-browser@synthetic.invalid"),
            (True, "race-native@synthetic.invalid"),
        ):
            with self.subTest(native=native):
                competing_username = "competing-native" if native else "competing-browser"

                def register_after_competitor(form):
                    User.objects.create_user(
                        username=competing_username,
                        email=email.upper(),
                        password=PASSWORD,
                    )
                    return register(form)

                with (
                    override_settings(
                        WEB_DASHBOARD_URL="http://localhost:3000/dashboard" if native else ""
                    ),
                    patch("core.signup.register", side_effect=register_after_competitor),
                ):
                    response = self.post(
                        username="raced-native" if native else "raced-browser",
                        email=email,
                        native_signup="1" if native else "0",
                    )
                if native:
                    self.assertEqual(response.status_code, 303)
                    self.assertEqual(
                        response.url, "http://localhost:3000/account/sign-up?notice=taken"
                    )
                else:
                    self.assertContains(
                        response, "An account already uses these details.", status_code=400
                    )
                self.assertEqual(User.objects.filter(email__iexact=email).count(), 1)
                self.assertFalse(Workspace.objects.exists())
                self.assertFalse(Membership.objects.exists())
                self.assertFalse(Entitlement.objects.exists())
                self.assertNotIn("_auth_user_id", self.client.session)

    def test_attempts_are_rate_limited(self):
        for i in range(20):
            self.post(username=f"spam-{i}", email=f"s{i}@x.example", password2="mismatch-pass-1")
        response = self.post(username="spam-final")
        self.assertEqual(response.status_code, 429)
        self.assertFalse(User.objects.exists())
        self.assertTrue(LoginBucket.objects.exists())

    @override_settings(SAAS_SIGNUP_ENABLED=False)
    def test_disabled_sign_up_is_not_found(self):
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.post().status_code, 404)
        self.assertFalse(User.objects.exists())
