#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

DEFAULT_PATH = Path("config/audit/audit-journal.json")


def canonical_entry_bytes(entry: dict) -> bytes:
    payload = dict(entry)
    payload.pop("entry_hash", None)
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def entry_hash(entry: dict) -> str:
    return hashlib.sha256(canonical_entry_bytes(entry)).hexdigest()


def verify(document: dict) -> None:
    integrity = document.get("integrity") or {}
    if integrity.get("mode") != "sha256_hash_chain":
        raise ValueError("audit journal integrity mode must be sha256_hash_chain")
    previous = integrity.get("genesis_hash")
    if not isinstance(previous, str) or len(previous) != 64:
        raise ValueError("audit journal genesis_hash must be a SHA-256 hex digest")
    seen_ids: set[str] = set()
    for index, row in enumerate(document.get("entries") or [], start=1):
        row_id = str(row.get("id") or "")
        if not row_id or row_id in seen_ids:
            raise ValueError(f"audit entry {index}: missing/duplicate id")
        seen_ids.add(row_id)
        if row.get("previous_entry_hash") != previous:
            raise ValueError(f"{row_id}: previous_entry_hash mismatch")
        actual = entry_hash(row)
        if row.get("entry_hash") != actual:
            raise ValueError(f"{row_id}: entry_hash mismatch")
        previous = actual
    if integrity.get("latest_entry_hash") != previous:
        raise ValueError("audit journal latest_entry_hash mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()
    document = json.loads(args.path.read_text(encoding="utf-8"))
    verify(document)
    print(f"audit journal verified: {len(document.get('entries') or [])} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
