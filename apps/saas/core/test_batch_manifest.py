import hashlib
import hmac
import json
from dataclasses import asdict, replace
from datetime import timedelta
from uuid import uuid4

from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .batch_manifest import BatchBinding, verified_batch_manifest

SOURCE = b"synthetic-batch-source-key-000000000000"
DEDUPE = b"synthetic-batch-registry-key-11111111111"


@override_settings(
    SAAS_BATCH_VERIFIERS={"fixture": {"source": SOURCE}},
    SAAS_BATCH_DEDUPE_VERIFIERS={"isolated/test": {"dedupe": DEDUPE}},
)
class BatchManifestTests(SimpleTestCase):
    def setUp(self):
        self.binding = BatchBinding(
            uuid4(),
            uuid4(),
            uuid4(),
            uuid4(),
            uuid4(),
            "fixture",
            "isolated/test",
            "1" * 64,
            "2" * 64,
            "3" * 64,
            "candidate-1",
            25,
            2,
        )
        self.data = {
            k: str(v)
            for k, v in asdict(self.binding).items()
            if k not in {"reserved_leads", "reserved_calls"}
        }
        self.data.update(
            version=3,
            kind="accepted-batch",
            source_key_id="source",
            dedupe_key_id="dedupe",
            receipt_ref="batch-receipt-1",
            issued_at=int(timezone.now().timestamp()),
            provider_calls=1,
            records=[
                {
                    "record_ref": "record-1",
                    "tokens": ["n:" + "1" * 24, "l:" + "2" * 24, "s:" + "3" * 24],
                }
            ],
            registry_contract="r2-exact-objects-v1",
            qualification_contract="vsn-phone-usca-v1",
            registry_state="committed",
        )

    def verify(self, data=None, body=None, source_signature=None, binding=None):
        body = json.dumps(self.data if data is None else data).encode() if body is None else body
        return verified_batch_manifest(
            body,
            source_signature or hmac.new(SOURCE, body, hashlib.sha256).hexdigest(),
            hmac.new(DEDUPE, body, hashlib.sha256).hexdigest(),
            binding or self.binding,
        )

    def denied(self, **kwargs):
        with self.assertRaisesMessage(ValidationError, "Batch manifest is unavailable or invalid."):
            self.verify(**kwargs)

    def test_immutable_redacted_evidence_has_no_database_or_replay_side_effects(self):
        proof = self.verify()
        self.assertEqual((proof.accepted_count, proof.provider_calls), (1, 1))
        self.assertEqual(proof, self.verify())
        self.assertNotIn("record", repr(proof))
        self.assertFalse(hasattr(proof, "records"))

    def test_empty_revoked_and_same_authority_keys_fail_closed(self):
        with override_settings(SAAS_BATCH_VERIFIERS={}):
            self.denied()
        with override_settings(SAAS_BATCH_DEDUPE_VERIFIERS={}):
            self.denied()
        with override_settings(SAAS_BATCH_DEDUPE_VERIFIERS={"isolated/test": {"dedupe": SOURCE}}):
            self.denied()
        self.denied(source_signature="0" * 64)

    def test_signed_foreign_coordinates_and_candidate_hash_cannot_cross_scope(self):
        for field in asdict(self.binding):
            if field not in {"reserved_leads", "reserved_calls"}:
                self.denied(data={**self.data, field: "foreign"})
        self.denied(binding=replace(self.binding, batch_id=uuid4()))

    def test_v2_and_wrong_kind_cannot_use_v3_contract(self):
        for version in (2, True, 3.0):
            self.denied(data={**self.data, "version": version})
        self.denied(data={**self.data, "kind": "accepted-results"})
        self.denied(data={**self.data, "registry_state": "pending"})
        self.denied(data={**self.data, "qualification_contract": "unqualified"})

    def test_oversized_duplicate_missing_and_raw_payload_envelopes_are_denied(self):
        for body in (b"", b"[]", b"\xff", b" " * 16385):
            self.denied(body=body)
        body = json.dumps(self.data).encode()
        self.denied(body=body[:-1] + b',"version":3}')
        self.denied(data={**self.data, "phone": "+12025550123"})
        self.denied(data={k: v for k, v in self.data.items() if k != "records"})

    def test_batch_record_and_call_limits_are_strict_and_use_trusted_reservation_bounds(self):
        self.denied(data={**self.data, "records": []})
        self.denied(data={**self.data, "records": self.data["records"] * 26})
        for calls in (0, True, 1.0, 3):
            self.denied(data={**self.data, "provider_calls": calls})
        self.denied(binding=replace(self.binding, reserved_calls=True))
        self.denied(binding=replace(self.binding, reserved_leads=0))

    def test_duplicate_records_fingerprints_and_unqualified_token_shapes_are_denied(self):
        row = self.data["records"][0]
        self.denied(data={**self.data, "records": [row, row]})
        self.denied(data={**self.data, "records": [row, {**row, "record_ref": "another"}]})
        for tokens in ([], ["n:" + "1" * 24] * 3, ["n:bad", "l:bad", "s:bad"]):
            self.denied(data={**self.data, "records": [{**row, "tokens": tokens}]})
        self.denied(data={**self.data, "records": [{**row, "fields": {"phone": "raw"}}]})

    def test_stale_future_and_noninteger_issuance_fail_closed(self):
        for issued in (
            int((timezone.now() - timedelta(days=2)).timestamp()),
            int((timezone.now() + timedelta(hours=1)).timestamp()),
            True,
            1.0,
        ):
            self.denied(data={**self.data, "issued_at": issued})

    def test_changed_body_cannot_reuse_exact_signature(self):
        body = json.dumps(self.data).encode()
        self.denied(
            body=body + b" ", source_signature=hmac.new(SOURCE, body, hashlib.sha256).hexdigest()
        )

    def test_twenty_five_unique_records_and_lower_reserved_bound(self):
        rows = [
            {
                "record_ref": f"record-{n}",
                "tokens": [prefix + ":" + f"{n:024x}" for prefix in ("n", "l", "s")],
            }
            for n in range(25)
        ]
        data = {**self.data, "records": rows}
        self.assertEqual(self.verify(data=data).accepted_count, 25)
        self.denied(data=data, binding=replace(self.binding, reserved_leads=24))
        self.denied(
            data={
                **data,
                "records": rows
                + [
                    {
                        "record_ref": "record-26",
                        "tokens": ["n:" + "f" * 24, "l:" + "f" * 24, "s:" + "f" * 24],
                    }
                ],
            }
        )
