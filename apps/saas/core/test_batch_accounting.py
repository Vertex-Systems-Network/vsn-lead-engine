"""Pure v3 accounting rejects incomplete, ambiguous and over-budget sets."""

from dataclasses import replace
from uuid import uuid4

from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError

from .batch_accounting import SourceAccounting, checked_batch_settlement


class BatchAccountingTests(SimpleTestCase):
    def setUp(self):
        self.a = SourceAccounting(uuid4(), "alpha", "started", 3, 2, 4, 2, 3)
        self.b = SourceAccounting(uuid4(), "beta", "started", 2, 1, 1, 1, 1)
        self.sources = (self.a, self.b)
        self.expected = frozenset({"alpha", "beta"})

    def check(self, sources=None, expected=None, leads=8, calls=5):
        return checked_batch_settlement(
            self.sources if sources is None else sources,
            self.expected if expected is None else expected,
            leads,
            calls,
        )

    def denied(self, **changes):
        with self.assertRaises(ValidationError):
            self.check(**changes)

    def test_exact_complete_source_set_has_no_database_access_or_side_effect(self):
        result = self.check()
        self.assertEqual(
            (result.leads, result.jobs, result.provider_calls, result.exports), (5, 1, 4, 0)
        )
        self.assertEqual(
            result.operation_ids, tuple(sorted((self.a.operation_id, self.b.operation_id)))
        )
        self.assertNotIn("alpha", repr(result))

    def test_missing_extra_or_duplicate_source_never_settles(self):
        for items in ((self.a,), (self.a, self.a), (self.a, replace(self.b, source_code="alpha"))):
            self.denied(sources=items)
        self.denied(expected=frozenset({"alpha", "gamma"}))

    def test_duplicate_operation_id_cannot_be_counted_twice(self):
        self.denied(sources=(self.a, replace(self.b, operation_id=self.a.operation_id)))

    def test_unknown_or_noeffect_operation_is_not_reconciled(self):
        for status in ("unknown", "noeffect", "success", ""):
            self.denied(sources=(replace(self.a, operation_status=status), self.b))

    def test_empty_and_unaccepted_batch_sets_are_not_refunds(self):
        self.denied(sources=())
        for change in ({"batch_count": 0}, {"accepted_count": 0}, {"committed_batch_calls": 0}):
            self.denied(sources=(replace(self.a, **change), self.b))

    def test_original_job_and_source_caps_are_enforced(self):
        self.denied(leads=4)
        self.denied(calls=3)
        self.denied(sources=(replace(self.a, final_provider_calls=4), self.b))
        self.denied(sources=(replace(self.b, accepted_count=26), self.a))

    def test_final_calls_cannot_understate_committed_batch_calls(self):
        self.denied(sources=(replace(self.a, final_provider_calls=1), self.b))
        self.denied(sources=(replace(self.a, committed_batch_calls=1), self.b))

    def test_boolean_float_oversized_and_wrong_container_values_fail_closed(self):
        for value in (True, 5.0, 0, 2147483648):
            self.denied(leads=value)
            self.denied(calls=value)
        self.denied(sources=list(self.sources))
        self.denied(expected={"alpha", "beta"})
        self.denied(sources=(replace(self.a, accepted_count=True), self.b))
