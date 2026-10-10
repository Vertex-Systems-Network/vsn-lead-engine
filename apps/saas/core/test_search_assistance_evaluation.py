"""Golden, offline abstention coverage for bounded no-model search setup preview.

This exercise deliberately uses synthetic public words, not contacts/real leads,
and SimpleTestCase denies database reads or writes.
"""

import json
from collections import Counter
from pathlib import Path

from django.test import SimpleTestCase

from .search_assistance import SearchAssistForm, search_assistance_preview

FIXTURE = Path(__file__).parent / "fixtures" / "search_assistance_evaluation.json"


class SearchAssistanceEvaluationTests(SimpleTestCase):
    def test_all_fixed_synthetic_cases(self):
        corpus = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(corpus["schema_version"], 1)
        rows = corpus["cases"]
        self.assertEqual(len(rows), 50)
        self.assertEqual(len({row["id"] for row in rows}), len(rows))
        tally = Counter(row["status"] for row in rows)
        self.assertGreaterEqual(tally["ready_for_manual_review"], 12)
        self.assertGreaterEqual(tally["needs_details"], 15)
        self.assertGreaterEqual(tally["invalid"], 19)
        for row in rows:
            with self.subTest(id=row["id"]):
                self.assertEqual(
                    set(row),
                    {"id", "intent", "status", "countries", "categories"},
                )
                form = SearchAssistForm(data={"intent": row["intent"]})
                if row["status"] == "invalid":
                    self.assertFalse(form.is_valid())
                    continue
                self.assertTrue(form.is_valid(), str(form.errors))
                preview = search_assistance_preview(form.cleaned_data["intent"])
                self.assertEqual(preview["mode"], "rules_only_no_model")
                self.assertFalse(preview["model_invoked"])
                self.assertTrue(preview["needs_user_review"])
                self.assertEqual(preview["status"], row["status"])
                if row["status"] == "needs_details":
                    self.assertIsNone(preview["search"])
                    self.assertTrue(preview["missing"])
                    self.assertEqual(row["countries"], [])
                    self.assertEqual(row["categories"], [])
                else:
                    self.assertEqual(preview["search"]["countries"], row["countries"])
                    self.assertEqual(preview["search"]["categories"], row["categories"])
                    self.assertEqual(preview["search"]["source_codes"], [])
                    self.assertEqual(preview["search"]["statuses"], [])
                    self.assertEqual(preview["search"]["required_fields"], ["phone"])
                    self.assertEqual(preview["search"]["result_limit"], 25)
                    self.assertEqual(preview["missing"], [])
