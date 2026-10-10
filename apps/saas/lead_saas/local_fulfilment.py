"""Dev-only in-process result attestation keys for the local fixture source.

Production verifier registries stay empty. These keys exist only when
SAAS_LOCAL_FULFILMENT=1 with SAAS_DEBUG=1, are derived from SECRET_KEY, and are
registered only for the source codes below.
"""

import hashlib
import hmac

SOURCE_CODE = "local-fixture"
OVERTURE = "overture"
LOCAL_SOURCES = (SOURCE_CODE, OVERTURE)
ROLES = ("candidate", "acceptance", "dedupe", "receipt")
NAMESPACE_PREFIX = "saas-results/v1/"


def derived_keys(secret_key):
    """Four distinct 32-byte keys; distinct roles keep the verifiers independent."""
    return {
        role: hmac.new(
            secret_key.encode(), f"vsn-local-signer/v1/{role}".encode(), hashlib.sha256
        ).digest()
        for role in ROLES
    }


class NamespaceKeys(dict):
    """Dedupe verifiers are keyed per workspace namespace; answer for every one."""

    def __init__(self, key):
        super().__init__()
        self._key = key

    def get(self, namespace, default=None):
        if isinstance(namespace, str) and namespace.startswith(NAMESPACE_PREFIX):
            return {"local-dedupe": self._key}
        return default


def verifier_settings(secret_key):
    keys = derived_keys(secret_key)
    return {
        "SAAS_LOCAL_SIGNER_KEYS": keys,
        "SAAS_RESULT_VERIFIERS": {c: {"local-candidate": keys["candidate"]} for c in LOCAL_SOURCES},
        "SAAS_ACCEPTANCE_VERIFIERS": {
            c: {"local-acceptance": keys["acceptance"]} for c in LOCAL_SOURCES
        },
        "SAAS_DEDUPE_VERIFIERS": NamespaceKeys(keys["dedupe"]),
        "SAAS_RECEIPT_VERIFIERS": {c: {"local-receipt": keys["receipt"]} for c in LOCAL_SOURCES},
    }
