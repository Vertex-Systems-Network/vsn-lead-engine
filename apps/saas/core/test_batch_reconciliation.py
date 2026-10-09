"""Adversarial pure bounds for positive and explicitly signed zero-effect sets."""

from dataclasses import replace
from uuid import uuid4

from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError

from .batch_reconciliation import SourceEvidenceTotals, bounded_source_evidence


class SourceEvidenceTests(SimpleTestCase):
    def setUp(self):
        self.positive = SourceEvidenceTotals(
            uuid4(), "alpha", "started", "source-final", 3, 2, 4, 2, 3
        )
        self.zero = SourceEvidenceTotals(
            uuid4(), "beta", "unknown", "source-noeffect", 2, 1, 0, 0, 0
        )
        self.sources = (self.positive, self.zero)
        self.expected = frozenset({"alpha", "beta"})

    def check(self, sources=None, expected=None, leads=5, calls=5):
        return bounded_source_evidence(
            self.sources if sources is None else sources,
            self.expected if expected is None else expected,
            leads,
            calls,
        )

    def denied(self, **changes):
        with self.assertRaises(ValidationError):
            self.check(**changes)

    def test_mixed_explicit_set_is_pure_and_not_a_settlement(self):
        totals = self.check()
        self.assertEqual((totals.leads, totals.provider_calls), (4, 3))
        self.assertEqual(totals.positive_operation_ids, (self.positive.operation_id,))
        self.assertEqual(totals.noeffect_operation_ids, (self.zero.operation_id,))
        self.assertFalse(hasattr(totals, "jobs"))

    def test_all_noeffect_requires_every_original_source(self):
        other = replace(
            self.positive,
            outcome="source-noeffect",
            accepted_leads=0,
            accepted_calls=0,
            final_calls=0,
        )
        totals = self.check(sources=(other, self.zero))
        self.assertEqual((totals.leads, totals.provider_calls), (0, 0))
        self.denied(sources=(self.zero,))
        self.denied(sources=())

    def test_missing_duplicate_or_foreign_source_and_operation_denied(self):
        for sources in (
            (self.positive, self.positive),
            (self.positive, replace(self.zero, source_code="alpha")),
            (self.positive, replace(self.zero, operation_id=self.positive.operation_id)),
        ):
            self.denied(sources=sources)
        self.denied(expected=frozenset({"alpha", "gamma"}))

    def test_zero_effect_cannot_hide_calls_or_accepted_payload(self):
        for changed in ({"accepted_leads": 1}, {"accepted_calls": 1}, {"final_calls": 1}):
            self.denied(sources=(self.positive, replace(self.zero, **changed)))

    def test_ambiguous_or_unbounded_positive_evidence_denied(self):
        for changed in (
            {"outcome": "unknown"},
            {"accepted_leads": 0},
            {"accepted_leads": 51},
            {"accepted_calls": 0},
            {"final_calls": 1},
            {"final_calls": 4},
            {"allocated_batches": 0},
        ):
            self.denied(sources=(replace(self.positive, **changed), self.zero))
        self.denied(sources=(replace(self.zero, operation_status="success"), self.positive))

    def test_original_reservation_caps_and_strict_input_types(self):
        self.denied(leads=3)
        self.denied(calls=2)
        for value in (True, 2.0, 0, 2147483648):
            self.denied(leads=value)
            self.denied(calls=value)
        self.denied(sources=list(self.sources))
        self.denied(expected={"alpha", "beta"})
        self.denied(sources=(replace(self.zero, final_calls=True), self.positive))
