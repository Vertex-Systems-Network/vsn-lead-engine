import re

from django.core import mail
from django.test import TestCase

from .models import User

PASSWORD = "original-passphrase-5521"
NEW = "replacement-passphrase-8812"


class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="reset-owner", email="owner@reset.example", password=PASSWORD
        )

    def request_reset(self, email="owner@reset.example"):
        return self.client.post("/accounts/password-reset/", {"email": email})

    def test_reset_link_sets_a_new_password_once(self):
        self.assertContains(self.client.get("/accounts/login/"), "Forgot your password?")
        response = self.request_reset("OWNER@reset.example")
        self.assertRedirects(response, "/accounts/password-reset/sent/")
        self.assertEqual(len(mail.outbox), 1)
        link = re.search(r"https?://[^/\s]+(/accounts/reset/\S+/)", mail.outbox[0].body).group(1)
        form_page = self.client.get(link, follow=True)
        self.assertContains(form_page, "Choose a new password")
        set_url = form_page.redirect_chain[-1][0]
        done = self.client.post(set_url, {"new_password1": NEW, "new_password2": NEW})
        self.assertRedirects(done, "/accounts/reset/done/")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW))
        self.assertContains(self.client.get(link, follow=True), "Link expired")

    def test_unknown_address_gets_the_same_response_and_no_email(self):
        response = self.request_reset("nobody@reset.example")
        self.assertRedirects(response, "/accounts/password-reset/sent/")
        self.assertEqual(mail.outbox, [])

    def test_requests_are_rate_limited(self):
        for _ in range(10):
            self.request_reset()
        response = self.request_reset()
        self.assertContains(response, "Too many requests", status_code=429)
        self.assertEqual(len(mail.outbox), 10)
