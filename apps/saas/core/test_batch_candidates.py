import hashlib
import hmac
import json
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .batch_candidates import CandidateBatchBinding, verified_batch_candidates

KEY = b"synthetic-batch-candidate-key-000000000000"


@override_settings(SAAS_BATCH_CANDIDATE_VERIFIERS={"fixture": {"candidate": KEY}})
class BatchCandidateTests(SimpleTestCase):
    def setUp(self):
        now = timezone.now()
        self.binding = CandidateBatchBinding(
            uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), "fixture", "a" * 64, "b" * 64, now, 25
        )
        self.search = {
            "result_limit": 25,
            "countries": ["US", "CA"],
            "categories": ["software"],
            "required_fields": ["phone"],
            "statuses": [],
        }
        self.policy = SimpleNamespace(
            code="fixture",
            controls={
                "result_contract": {
                    "version": 1,
                    "purpose": "fixture",
                    "retention_version": "fixture-v1",
                    "max_age_seconds": 3600,
                    "display_fields": ["business_name", "phone"],
                    "storage_fields": ["business_name", "phone"],
                    "display_allowed": True,
                    "storage_allowed": True,
                }
            },
        )
        self.data = {
            name: str(getattr(self.binding, name))
            for name in (
                "workspace_id",
                "job_id",
                "operation_id",
                "batch_id",
                "provider_key",
                "source_code",
                "request_hash",
                "policy_fingerprint",
            )
        }
        self.row = {
            "record_ref": "record-1",
            "country": "US",
            "category": "software",
            "observed_at": int(now.timestamp()),
            "fields": {"business_name": "Fixture only", "phone": "+12025550123"},
            "field_lineage": {"business_name": "record-1", "phone": "record-1"},
            "purpose": "fixture",
            "retention_version": "fixture-v1",
        }
        self.data.update(
            version=3,
            kind="candidate-batch",
            source_key_id="candidate",
            event_ref="event-1",
            issued_at=int(now.timestamp()),
            records=[self.row],
        )

    def verify(self, data=None, body=None, binding=None, signature=None):
        body = json.dumps(self.data if data is None else data).encode() if body is None else body
        return verified_batch_candidates(
            body,
            signature or hmac.new(KEY, body, hashlib.sha256).hexdigest(),
            binding or self.binding,
            self.policy,
            self.search,
        )

    def denied(self, **kwargs):
        with self.assertRaisesMessage(
            ValidationError, "Batch candidate evidence is unavailable or invalid."
        ):
            self.verify(**kwargs)

    def test_redacted_immutable_review_never_accesses_database(self):
        review = self.verify()
        self.assertEqual(review.candidate_count, 1)
        self.assertEqual(review, self.verify())
        self.assertFalse(hasattr(review, "records"))
        self.assertNotIn("record-1", repr(review))

    def test_unknown_revoked_or_bad_key_fails_closed(self):
        with override_settings(SAAS_BATCH_CANDIDATE_VERIFIERS={}):
            self.denied()
        self.denied(signature="0" * 64)
        self.denied(data={**self.data, "source_key_id": "unknown"})
        self.policy.code = "foreign"
        self.denied()

    def test_batch_operation_and_request_coordinates_cannot_cross_scope(self):
        for name in (
            "workspace_id",
            "job_id",
            "operation_id",
            "batch_id",
            "provider_key",
            "source_code",
            "request_hash",
            "policy_fingerprint",
        ):
            self.denied(data={**self.data, name: "foreign"})
        self.denied(binding=replace(self.binding, batch_id=uuid4()))
        for version in (1, True, 3.0):
            self.denied(data={**self.data, "version": version})
        self.denied(data={**self.data, "kind": "accepted-batch"})

    def test_raw_extra_duplicate_missing_and_oversized_envelopes_fail_closed(self):
        for body in (b"", b"[]", b"\xff", b" " * 131073):
            self.denied(body=body)
        raw = json.dumps(self.data).encode()
        self.denied(body=raw[:-1] + b',"batch_id":"duplicate"}')
        self.denied(data={**self.data, "extra": "raw"})
        self.denied(data={k: v for k, v in self.data.items() if k != "records"})

    def test_phone_territory_taxonomy_lineage_and_payload_rules_preserved(self):
        for changes in (
            {"country": "GB"},
            {"category": "unknown"},
            {"fields": {"business_name": "Fixture", "phone": "email-only"}},
            {"field_lineage": {"phone": "foreign"}},
            {"purpose": "other"},
        ):
            self.denied(data={**self.data, "records": [{**self.row, **changes}]})

    def test_current_result_rights_retention_and_expiry_are_required(self):
        for changes in (
            {"storage_allowed": False},
            {"display_allowed": False},
            {"max_age_seconds": True},
            {"storage_fields": ["phone"]},
        ):
            policy = deepcopy(self.policy)
            self.policy.controls["result_contract"].update(changes)
            self.denied()
            self.policy = policy
        old = int((timezone.now() - timedelta(hours=2)).timestamp())
        self.denied(data={**self.data, "records": [{**self.row, "observed_at": old}]})
        self.denied(
            data={**self.data, "issued_at": int((timezone.now() - timedelta(days=2)).timestamp())}
        )

    def test_duplicate_records_and_trusted_bounds_cannot_expand_batch(self):
        self.denied(data={**self.data, "records": [self.row, self.row]})
        self.denied(binding=replace(self.binding, reserved_leads=True))
        self.denied(binding=replace(self.binding, reserved_leads=1))
        self.denied(
            binding=replace(self.binding, operation_created_at=timezone.now().replace(tzinfo=None))
        )

    def test_twenty_five_is_maximum_even_for_one_thousand_requested(self):
        rows = []
        for index in range(25):
            ref = f"record-{index}"
            rows.append(
                {
                    **self.row,
                    "record_ref": ref,
                    "field_lineage": {"business_name": ref, "phone": ref},
                }
            )
        self.search["result_limit"] = 1000
        binding = replace(self.binding, reserved_leads=1000)
        self.assertEqual(
            self.verify(data={**self.data, "records": rows}, binding=binding).candidate_count, 25
        )
        self.denied(
            data={**self.data, "records": rows + [{**rows[0], "record_ref": "extra"}]},
            binding=binding,
        )
