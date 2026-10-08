import hashlib
import hmac
import json
from dataclasses import replace
from uuid import uuid4

from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .terminal_manifest import TerminalBatch, TerminalBinding, verified_terminal_manifest

KEY = b"synthetic-source-terminal-key-000000000000"


@override_settings(SAAS_BATCH_TERMINAL_VERIFIERS={"fixture": {"terminal": KEY}})
class TerminalManifestTests(SimpleTestCase):
    def setUp(self):
        self.binding = TerminalBinding(
            uuid4(),
            uuid4(),
            uuid4(),
            uuid4(),
            "fixture",
            "a" * 64,
            "b" * 64,
            50,
            5,
            (TerminalBatch(uuid4(), "c" * 64, 25, 2), TerminalBatch(uuid4(), "d" * 64, 1, 1)),
        )
        self.data = {
            name: str(getattr(self.binding, name))
            for name in (
                "workspace_id",
                "job_id",
                "operation_id",
                "provider_key",
                "source_code",
                "request_hash",
                "policy_fingerprint",
            )
        }
        self.data.update(
            version=3,
            kind="source-final",
            source_key_id="terminal",
            receipt_ref="final-1",
            issued_at=int(timezone.now().timestamp()),
            provider_calls=4,
            batches=sorted(
                [
                    dict(
                        batch_id=str(b.batch_id),
                        acceptance_body_hash=b.acceptance_body_hash,
                        accepted_count=b.accepted_count,
                        provider_calls=b.provider_calls,
                    )
                    for b in self.binding.batches
                ],
                key=lambda row: row["batch_id"],
            ),
        )

    def verify(self, data=None, binding=None, body=None, signature=None):
        raw = json.dumps(self.data if data is None else data).encode() if body is None else body
        return verified_terminal_manifest(
            raw,
            signature or hmac.new(KEY, raw, hashlib.sha256).hexdigest(),
            binding or self.binding,
        )

    def denied(self, **kwargs):
        with self.assertRaisesMessage(
            ValidationError, "Terminal manifest is unavailable or invalid."
        ):
            self.verify(**kwargs)

    def test_exact_set_proof_is_immutable_redacted_and_database_forbidden(self):
        proof = self.verify()
        self.assertEqual(
            (proof.batch_count, proof.accepted_count, proof.provider_calls), (2, 26, 4)
        )
        expected = hashlib.sha256(
            json.dumps(self.data["batches"], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self.assertEqual(proof.batch_set_hash, expected)
        self.assertEqual(
            proof, self.verify(binding=replace(self.binding, batches=self.binding.batches[::-1]))
        )
        self.assertFalse(hasattr(proof, "batches"))
        self.assertNotIn("final-1", repr(proof))

    def test_empty_set_can_attest_zero_or_nonzero_calls_without_implied_refund(self):
        binding = replace(self.binding, batches=())
        for calls in (0, 3):
            proof = self.verify(
                data={**self.data, "batches": [], "provider_calls": calls}, binding=binding
            )
            self.assertEqual((proof.accepted_count, proof.provider_calls), (0, calls))

    def test_revoked_missing_wrong_source_and_weak_keys_fail_closed(self):
        for registry in ({}, {"fixture": {"terminal": b"short"}}, {"other": {"terminal": KEY}}):
            with override_settings(SAAS_BATCH_TERMINAL_VERIFIERS=registry):
                self.denied()
        self.denied(signature="0" * 64)
        self.denied(data={**self.data, "source_key_id": "unknown"})

    def test_signed_context_and_v2_wrong_kind_fail_closed(self):
        for name in (
            "workspace_id",
            "job_id",
            "operation_id",
            "provider_key",
            "source_code",
            "request_hash",
            "policy_fingerprint",
        ):
            self.denied(data={**self.data, name: "foreign"})
        for version in (2, True, 3.0):
            self.denied(data={**self.data, "version": version})
        self.denied(data={**self.data, "kind": "accepted-batch"})

    def test_missing_added_duplicate_reordered_or_mutated_batches_fail_closed(self):
        rows = self.data["batches"]
        for values in (rows[:1], rows + rows[:1], rows[:1] * 2, rows[::-1]):
            self.denied(data={**self.data, "batches": values})
        for name, value in (
            ("batch_id", str(uuid4())),
            ("acceptance_body_hash", "e" * 64),
            ("accepted_count", 2),
            ("provider_calls", 3),
            ("extra", "raw"),
        ):
            self.denied(data={**self.data, "batches": [{**rows[0], name: value}, rows[1]]})

    def test_call_totals_cannot_undercount_accrued_usage_or_exceed_reservation(self):
        for value in (2, 6, True, 4.0):
            self.denied(data={**self.data, "provider_calls": value})
        self.denied(binding=replace(self.binding, reserved_calls=2))
        self.denied(binding=replace(self.binding, reserved_leads=25))

    def test_trusted_batches_must_be_typed_unique_and_individually_bounded(self):
        batch = self.binding.batches[0]
        for batches in (
            [batch],
            (batch, batch),
            (None,),
            (replace(batch, accepted_count=26),),
            (replace(batch, provider_calls=0),),
            (replace(batch, accepted_count=True),),
            (replace(batch, batch_id="foreign"),),
        ):
            self.denied(binding=replace(self.binding, batches=batches))
        for caps in (
            {"reserved_calls": True},
            {"reserved_leads": 0},
            {"reserved_calls": 2147483648},
        ):
            self.denied(binding=replace(self.binding, **caps))
        self.denied(
            binding=replace(
                self.binding,
                batches=tuple(TerminalBatch(uuid4(), "a" * 64, 1, 1) for _ in range(1001)),
                reserved_leads=1001,
                reserved_calls=1001,
            )
        )

    def test_duplicate_json_keys_oversize_missing_fields_and_payload_are_rejected(self):
        body = json.dumps(self.data).encode()
        for value in (b"", b"[]", b"\xff", b" " * 262145, body[:-1] + b',"version":3}'):
            self.denied(body=value)
        self.denied(data={**self.data, "phone": "+12025550123"})
        self.denied(data={k: v for k, v in self.data.items() if k != "batches"})
        rows = self.data["batches"]
        body = json.dumps(
            {**self.data, "batches": [{**rows[0], "accepted_count": True}, rows[1]]}
        ).encode()
        self.denied(body=body)

    def test_issuance_limits_and_noninteger_timestamps_are_rejected(self):
        now = int(timezone.now().timestamp())
        for issued in (now - 86401, now + 301, True, 1.0, 10**100):
            self.denied(data={**self.data, "issued_at": issued})

    def test_one_thousand_batches_remain_bounded_and_do_not_expand_payload(self):
        batches = tuple(TerminalBatch(uuid4(), "a" * 64, 1, 1) for _ in range(1000))
        binding = replace(self.binding, batches=batches, reserved_leads=1000, reserved_calls=1000)
        rows = sorted(
            [
                dict(
                    batch_id=str(b.batch_id),
                    acceptance_body_hash=b.acceptance_body_hash,
                    accepted_count=1,
                    provider_calls=1,
                )
                for b in batches
            ],
            key=lambda row: row["batch_id"],
        )
        proof = self.verify(
            data={**self.data, "batches": rows, "provider_calls": 1000}, binding=binding
        )
        self.assertEqual((proof.batch_count, proof.accepted_count), (1000, 1000))
