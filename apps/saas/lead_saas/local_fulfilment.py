"""In-process result attestation keys for job fulfilment (manage.py run_jobs).

Two ways to enable it; with neither, every verifier registry stays empty:

* dev: SAAS_LOCAL_FULFILMENT=1 with SAAS_DEBUG=1 derives keys from SECRET_KEY and
  registers the synthetic fixture and Overture sources;
* staging/production: SAAS_FULFILMENT_KEYS_FILE names an owner-only JSON file of
  four distinct random keys (manage.py generate_fulfilment_keys) and registers
  real sources only. Keys never come from environment values or HTTP input.
"""

import hashlib
import hmac
import json
import os
import stat

SOURCE_CODE = "local-fixture"
OVERTURE = "overture"
LOCAL_SOURCES = (SOURCE_CODE, OVERTURE)
PRODUCTION_SOURCES = (OVERTURE,)
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


def verifier_maps(keys, sources):
    return {
        "SAAS_LOCAL_SIGNER_KEYS": keys,
        "SAAS_FULFILMENT_SOURCES": tuple(sources),
        "SAAS_RESULT_VERIFIERS": {c: {"local-candidate": keys["candidate"]} for c in sources},
        "SAAS_ACCEPTANCE_VERIFIERS": {c: {"local-acceptance": keys["acceptance"]} for c in sources},
        "SAAS_DEDUPE_VERIFIERS": NamespaceKeys(keys["dedupe"]),
        "SAAS_RECEIPT_VERIFIERS": {c: {"local-receipt": keys["receipt"]} for c in sources},
    }


def verifier_settings(secret_key):
    return verifier_maps(derived_keys(secret_key), LOCAL_SOURCES)


def new_keys():
    return {role: os.urandom(32).hex() for role in ROLES}


def load_keys_file(path):
    """Four distinct >=32-byte hex keys from an owner-only file, or ValueError."""
    info = os.stat(path)
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise ValueError("fulfilment keys file must be a regular file readable by its owner only")
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or set(data) != set(ROLES):
        raise ValueError(f"fulfilment keys file must contain exactly {', '.join(ROLES)}")
    keys = {}
    for role in ROLES:
        value = data[role]
        if not isinstance(value, str) or len(value) < 64:
            raise ValueError(f"fulfilment key {role} must be at least 32 bytes of hex")
        keys[role] = bytes.fromhex(value)
    if len(set(keys.values())) != len(ROLES):
        raise ValueError("fulfilment keys must be distinct")
    return keys
