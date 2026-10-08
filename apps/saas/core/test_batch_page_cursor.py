"""DB-forbidden v3 page cursor boundary and binding tests."""

from dataclasses import replace
from uuid import uuid4

from django.test import SimpleTestCase, override_settings
from rest_framework.exceptions import ValidationError

from .batch_page_cursor import PAGE_SIZE, PagePosition, decode_page_cursor, encode_page_cursor


@override_settings(SAAS_BATCH_PAGE_SIGNING_KEY="cursor-test-key-32-bytes-long-and-separate")
class BatchPageCursorTests(SimpleTestCase):
    def setUp(self):
        self.workspace = uuid4()
        self.job = uuid4()
        self.actor = uuid4()
        self.request_hash = "a" * 64
        self.upper = PagePosition("beta", 1000, PAGE_SIZE, str(uuid4()))
        self.last = PagePosition("alpha", 1, 1, str(uuid4()))

    def issue(self, **overrides):
        args = dict(
            workspace_id=self.workspace,
            job_id=self.job,
            actor_id=self.actor,
            request_hash=self.request_hash,
            watermark=self.upper,
            after=self.last,
            country="CA",
            category="1",
            source="0",
            now=1000,
        )
        args.update(overrides)
        return encode_page_cursor(**args)

    def read(self, cursor, **overrides):
        args = dict(
            workspace_id=self.workspace,
            job_id=self.job,
            actor_id=self.actor,
            request_hash=self.request_hash,
            country="CA",
            category="1",
            source="0",
            now=1001,
        )
        args.update(overrides)
        return decode_page_cursor(cursor, **args)

    def test_round_trip_fixed_watermark_and_maximum_position(self):
        continuation = self.read(self.issue())
        self.assertEqual(continuation.watermark, self.upper)
        self.assertEqual(continuation.after, self.last)

    def test_context_filter_or_revision_change_invalidates_cursor(self):
        cursor = self.issue()
        for changed in (
            {"workspace_id": uuid4()},
            {"job_id": uuid4()},
            {"actor_id": uuid4()},
            {"request_hash": "b" * 64},
            {"country": "US"},
            {"category": "2"},
            {"source": "1"},
        ):
            with self.subTest(changed=changed), self.assertRaises(ValidationError):
                self.read(cursor, **changed)

    def test_expiry_future_timestamp_tampering_and_size_fail_closed(self):
        cursor = self.issue()
        for altered, extra in (
            (cursor, {"now": 1900}),
            (cursor, {"now": 969}),
            (cursor[:-1] + ("A" if cursor[-1] != "A" else "B"), {}),
            (cursor + ".", {}),
            ("x" * 2049, {}),
            ("", {}),
        ):
            with self.subTest(altered=altered[:20], extra=extra), self.assertRaises(ValidationError):
                self.read(altered, **extra)

    def test_wrong_shape_bounds_order_and_filter_denied_at_issue(self):
        for changed in (
            {"after": replace(self.last, position=0)},
            {"after": replace(self.last, position=26)},
            {"after": replace(self.last, batch=1001)},
            {"after": replace(self.last, source="../../")},
            {"after": replace(self.last, row_id="invalid")},
            {"after": replace(self.upper, source="zeta")},
            {"watermark": replace(self.upper, position=True)},
            {"request_hash": "a" * 63},
            {"country": "GB"},
        ):
            with self.subTest(changed=changed), self.assertRaises(ValidationError):
                self.issue(**changed)

    @override_settings(SAAS_BATCH_PAGE_SIGNING_KEY="")
    def test_missing_signing_key_denies_issue_and_read(self):
        with self.assertRaises(ValidationError):
            self.issue()
        with self.assertRaises(ValidationError):
            self.read("arbitrary")

    @override_settings(SAAS_BATCH_PAGE_SIGNING_KEY="short")
    def test_weak_key_denied(self):
        with self.assertRaises(ValidationError):
            self.issue()
