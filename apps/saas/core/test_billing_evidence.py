import hashlib
import hmac
import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

from django.test import SimpleTestCase, override_settings
from rest_framework.exceptions import ValidationError

from .billing_evidence import BillingBinding, verified_billing_event

# Synthetic normalized adapter fixture only; no real provider secrets or account.
KEY = b"synthetic-billing-verifier-test-key-0000000"
NOW = datetime(2026, 10, 8, 15, 0, tzinfo=UTC)


@override_settings(SAAS_BILLING_VERIFIERS={"fixture": {"test": KEY}})
class BillingEvidenceTests(SimpleTestCase):
    def setUp(self):
        self.binding = BillingBinding(uuid4(), uuid4(), "fixture")
        self.data = {
            "version": 1,
            "key_id": "test",
            "event_ref": "fixture:event:1",
            "issuer_code": "fixture",
            "binding_id": str(self.binding.id),
            "workspace_id": str(self.binding.workspace_id),
            "revision": 1,
            "issued_at": int(NOW.timestamp()),
            "valid_until": int(NOW.timestamp()) + 86400,
            "active": True,
            "limits": {"leads": 100, "jobs": 10, "provider_calls": 20, "exports": 5},
        }
        clock = patch("core.billing_evidence.timezone.now", return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)

    def verify(self, data=None, body=None, signature=None, binding=None):
        if body is None:
            body = json.dumps(self.data if data is None else data).encode()
        if signature is None:
            signature = hmac.new(KEY, body, hashlib.sha256).hexdigest()
        return verified_billing_event(body, signature, self.binding if binding is None else binding)

    def denied(self, **kwargs):
        with self.assertRaisesMessage(
            ValidationError, "Billing evidence is unavailable or invalid."
        ):
            self.verify(**kwargs)

    def test_valid_snapshot_is_immutable_and_has_no_database_or_secret_payload(self):
        event = self.verify()
        self.assertEqual(
            (event.revision, event.active, event.leads, event.exports), (1, True, 100, 5)
        )
        self.assertEqual(event.issued_at, NOW)
        self.assertNotIn("fixture:event", repr(event))
        self.assertFalse(hasattr(event, "body"))
        self.assertFalse(hasattr(event, "signature"))
        with self.assertRaises(FrozenInstanceError):
            event.leads = 999
        # SimpleTestCase forbids DB access; identical validation has no replay side effect.
        self.assertEqual(event, self.verify())

    def test_default_unknown_revoked_and_badly_configured_keys_fail_closed(self):
        for registry in [
            {},
            {"fixture": {}},
            {"fixture": {"test": b"short"}},
            {"fixture": {"test": "not-bytes"}},
            None,
        ]:
            with (
                self.subTest(registry=registry),
                override_settings(SAAS_BILLING_VERIFIERS=registry),
            ):
                self.denied()
        self.denied(data={**self.data, "key_id": "unknown"})

    def test_exact_bytes_and_signature_shape_prevent_tampering(self):
        body = json.dumps(self.data).encode()
        sig = hmac.new(KEY, body, hashlib.sha256).hexdigest()
        self.denied(body=body + b" ", signature=sig)
        self.denied(
            data={**self.data, "limits": {**self.data["limits"], "leads": 999}}, signature=sig
        )
        for signature in ["0" * 64, sig.upper(), "", b"0" * 64, sig + "x"]:
            self.denied(signature=signature)

    def test_signed_foreign_workspace_binding_or_issuer_cannot_cross_trusted_scope(self):
        for field in ["workspace_id", "binding_id", "issuer_code"]:
            self.denied(data={**self.data, field: str(uuid4())})
        self.denied(binding=replace(self.binding, workspace_id=uuid4()))
        self.denied(binding=replace(self.binding, id=uuid4()))
        self.denied(binding=replace(self.binding, issuer_code="bad issuer"))
        self.denied(binding={"id": self.binding.id})

    def test_duplicate_unknown_missing_and_oversized_json_is_denied(self):
        body = json.dumps(self.data).encode()
        self.denied(body=body[:-1] + b',"revision":1}')
        self.denied(body=body.replace(b'"leads": 100', b'"leads": 100, "leads": 100'))
        for body in [b"", b"[]", b"null", b"{", b"\xff", b" " * 8193]:
            self.denied(body=body)
        self.denied(data={**self.data, "payment_proof": True})
        self.denied(data={key: value for key, value in self.data.items() if key != "active"})

    def test_boolean_float_negative_overflow_and_incomplete_limits_are_denied(self):
        for value in [True, 1.0, -1, 2147483648, "1", None]:
            self.denied(data={**self.data, "limits": {**self.data["limits"], "leads": value}})
        for limits in [{}, [], {**self.data["limits"], "money": 1}]:
            self.denied(data={**self.data, "limits": limits})
        self.denied(data={**self.data, "active": 1})
        self.denied(data={**self.data, "active": False})
        event = self.verify(
            data={
                **self.data,
                "active": False,
                "valid_until": int(NOW.timestamp()),
                "limits": dict.fromkeys(self.data["limits"], 0),
            }
        )
        self.assertFalse(event.active)

    def test_version_revision_and_reference_boundaries_are_strict(self):
        for version in [True, 1.0, 2, "1"]:
            self.denied(data={**self.data, "version": version})
        for revision in [True, 0, -1, 1.0, 2147483648]:
            self.denied(data={**self.data, "revision": revision})
        for value in ["", "x" * 97, "space value", "raw\nvalue", 1]:
            self.denied(data={**self.data, "event_ref": value})
        # Verification does not enforce ordering; the future ledger must do so.
        self.assertEqual(self.verify(data={**self.data, "revision": 2}).revision, 2)

    def test_stale_future_noninteger_and_unrepresentable_issuance_is_denied(self):
        stamp = int(NOW.timestamp())
        for issued in [stamp - 86401, stamp + 301, True, float(stamp), 10**100, -(10**100)]:
            self.denied(data={**self.data, "issued_at": issued})
        for issued in [stamp - 86400, stamp + 300]:
            self.assertIsNotNone(self.verify(data={**self.data, "issued_at": issued}))

    def test_expired_unbounded_or_ambiguous_validity_is_denied(self):
        stamp = int(NOW.timestamp())
        for deadline in [stamp, stamp - 1, stamp + 366 * 86400 + 1, True, 1.0, 10**100]:
            self.denied(data={**self.data, "valid_until": deadline})
        self.denied(
            data={**self.data, "active": False, "limits": dict.fromkeys(self.data["limits"], 0)}
        )
        self.assertIsNotNone(self.verify(data={**self.data, "valid_until": stamp + 366 * 86400}))

    def test_nonbytes_or_deeply_nested_inputs_fail_without_database_access(self):
        for body in [None, "{}", bytearray(b"{}"), 1]:
            with self.assertRaises(ValidationError):
                verified_billing_event(body, "0" * 64, self.binding)
        self.denied(body=b"[" * 2000 + b"0" + b"]" * 2000)
        for encoding in ["utf-16", "utf-32"]:
            self.denied(body=json.dumps(self.data).encode(encoding))
