"""DB-forbidden adversarial zero-effect proof tests."""

import hashlib
import hmac
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from django.test import SimpleTestCase, override_settings
from rest_framework.exceptions import ValidationError

from .batch_noeffect_manifest import (
    NoEffectBatch,
    NoEffectBinding,
    verified_noeffect_manifest,
)

KEY = b"isolated-noeffect-source-key-for-tests-12345"


@override_settings(SAAS_BATCH_NOEFFECT_VERIFIERS={"fixture": {"zero": KEY}})
class NoEffectManifestTests(SimpleTestCase):
    def setUp(self):
        self.binding = NoEffectBinding(
            uuid4(),
            uuid4(),
            uuid4(),
            uuid4(),
            "fixture",
            "a" * 64,
            "b" * 64,
            (NoEffectBatch(uuid4(), "c" * 64), NoEffectBatch(uuid4(), None)),
        )
        self.data = {
            "version": 3,
            "kind": "source-noeffect",
            "workspace_id": str(self.binding.workspace_id),
            "job_id": str(self.binding.job_id),
            "operation_id": str(self.binding.operation_id),
            "provider_key": str(self.binding.provider_key),
            "source_code": "fixture",
            "request_hash": "a" * 64,
            "policy_fingerprint": "b" * 64,
            "source_key_id": "zero",
            "receipt_ref": "noeffect-1",
            "issued_at": int(datetime.now(UTC).timestamp()),
            "provider_calls": 0,
            "batches": sorted(
                [
                    {
                        "batch_id": str(item.batch_id),
                        "candidate_body_hash": item.candidate_body_hash,
                    }
                    for item in self.binding.batches
                ],
                key=lambda row: row["batch_id"],
            ),
        }

    def verify(self, data=None, binding=None, key=KEY):
        raw = json.dumps(self.data if data is None else data).encode()
        signature = hmac.new(key, raw, hashlib.sha256).hexdigest()
        return verified_noeffect_manifest(raw, signature, binding or self.binding)

    def denied(self, **changes):
        with self.assertRaises(ValidationError):
            self.verify(data={**self.data, **changes})

    def test_exact_signed_set_is_pure_and_zero_calls(self):
        proof = self.verify()
        self.assertEqual(proof.batch_count, 2)
        self.assertEqual(len(proof.body_hash), 64)
        self.assertNotIn("fixture", repr(proof))

    def test_empty_set_requires_explicit_signed_zero_effect(self):
        binding = replace(self.binding, batches=())
        proof = self.verify(binding=binding, data={**self.data, "batches": []})
        self.assertEqual(proof.batch_count, 0)
        self.denied(batches=[])

    def test_scope_key_issuance_and_nonzero_calls_fail_closed(self):
        for changed in (
            {"workspace_id": str(uuid4())},
            {"operation_id": str(uuid4())},
            {"provider_key": str(uuid4())},
            {"policy_fingerprint": "d" * 64},
            {"source_code": "foreign"},
            {"source_key_id": "wrong"},
            {"provider_calls": 1},
            {"provider_calls": False},
            {"kind": "source-final"},
            {"issued_at": int((datetime.now(UTC) - timedelta(days=2)).timestamp())},
            {"unexpected": "value"},
        ):
            with self.subTest(changed=changed):
                self.denied(**changed)
        with override_settings(SAAS_BATCH_NOEFFECT_VERIFIERS={}):
            with self.assertRaises(ValidationError):
                self.verify()

    def test_allocated_identity_candidate_and_order_must_match_exactly(self):
        rows = self.data["batches"]
        changed_candidate = [
            {**row, "candidate_body_hash": None} if row["candidate_body_hash"] is not None else row
            for row in rows
        ]
        for altered in (
            rows[:1],
            rows + rows[:1],
            list(reversed(rows)),
            changed_candidate,
            [{**rows[0], "batch_id": str(uuid4())}, rows[1]],
        ):
            with self.subTest(altered=altered):
                self.denied(batches=altered)

    def test_invalid_binding_duplicate_ids_oversize_and_bad_signature(self):
        with self.assertRaises(ValidationError):
            self.verify(binding=replace(self.binding, batches=self.binding.batches * 501))
        with self.assertRaises(ValidationError):
            self.verify(binding=replace(self.binding, batches=(self.binding.batches[0],) * 2))
        with self.assertRaises(ValidationError):
            self.verify(key=b"different-key-32-bytes-long-for-tests")
        raw = json.dumps(self.data).encode()
        with self.assertRaises(ValidationError):
            verified_noeffect_manifest(
                raw + b" ", hmac.new(KEY, raw, hashlib.sha256).hexdigest(), self.binding
            )
