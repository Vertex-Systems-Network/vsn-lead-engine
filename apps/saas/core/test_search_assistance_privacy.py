"""Confidential-input safeguards for direct (future-adapter) and HTML callers.

Synthetic secret-like values only. No real credentials, user data, model or network.
"""

import json
from pathlib import Path

from django.test import SimpleTestCase

from .search_assistance import SearchAssistForm, search_assistance_preview, validated_search_intent

FIXTURE = Path(__file__).parent / "fixtures" / "search_assistance_evaluation.json"


class SearchAssistancePrivacyTests(SimpleTestCase):
    def test_direct_function_and_html_form_use_identical_data_minimization(self):
        rows = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
        self.assertEqual(len(rows), 50)
        for row in rows:
            intent = row["intent"]
            with self.subTest(case=row["id"]):
                form = SearchAssistForm(data={"intent": intent})
                if row["status"] == "invalid":
                    self.assertFalse(form.is_valid())
                    with self.assertRaises(ValueError) as caught:
                        search_assistance_preview(intent)
                    self.assertNotIn(intent, str(caught.exception))
                    self.assertNotIn(intent, str(form.errors))
                else:
                    self.assertTrue(form.is_valid())
                    self.assertEqual(validated_search_intent(intent), intent.strip())
                    self.assertEqual(
                        search_assistance_preview(intent),
                        search_assistance_preview(form.cleaned_data["intent"]),
                    )

    def test_no_untyped_bypass_or_secret_reflection(self):
        for candidate in (None, 1, [], {}, b"US spas"):
            with self.subTest(value_type=type(candidate).__name__):
                with self.assertRaises(ValueError):
                    validated_search_intent(candidate)
                with self.assertRaises(ValueError):
                    search_assistance_preview(candidate)

    def test_whitespace_is_normalized_without_expanding_a_sensitive_request(self):
        self.assertEqual(
            validated_search_intent("  US salons  "),
            "US salons",
        )
        with self.assertRaises(ValueError):
            search_assistance_preview(" US salons api_key=FAKEKEY123456 ")
