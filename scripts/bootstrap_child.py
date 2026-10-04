#!/usr/bin/env python3
"""Canonical ANPOS child bootstrap entrypoint.

Runs the normal child initializer and then strips vendor-only commercial runtime
(including the `commercial-service` path), source-management, export-test, and
operator launch/legal/App assets from customer/child repositories. The strip list
is machine-readable and shared with vendor repository export policy.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR_BOUNDARY_PATH = ROOT / "config" / "licensing" / "vendor-source-boundary.json"


class VendorBoundaryError(RuntimeError):
    pass


def load_vendor_only_paths() -> tuple[str, ...]:
    try:
        data = json.loads(VENDOR_BOUNDARY_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        raise VendorBoundaryError(f"unable to read vendor source boundary: {exc}") from exc
    if data.get("activation_scope") != "canonical_vendor_source_management_only":
        raise VendorBoundaryError("vendor source boundary activation_scope is invalid")
    raw = data.get("vendor_only_paths")
    if not isinstance(raw, list) or not raw:
        raise VendorBoundaryError("vendor source boundary must contain non-empty vendor_only_paths")
    paths: list[str] = []
    seen: set[str] = set()
    for value in raw:
        if not isinstance(value, str) or not value or value.startswith("/"):
            raise VendorBoundaryError("vendor-only path must be a non-empty repository-relative string")
        candidate = Path(value)
        if ".." in candidate.parts or candidate == Path("."):
            raise VendorBoundaryError(f"unsafe vendor-only path: {value!r}")
        normalized = candidate.as_posix()
        if normalized in seen:
            raise VendorBoundaryError(f"duplicate vendor-only path: {normalized}")
        seen.add(normalized)
        paths.append(normalized)
    return tuple(paths)


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--apply", action="store_true")
    known, passthrough = parser.parse_known_args()

    try:
        vendor_only_paths = load_vendor_only_paths()
    except VendorBoundaryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    command = [sys.executable, str(ROOT / "scripts" / "bootstrap_instance.py")]
    if known.apply:
        command.append("--apply")
    command.extend(passthrough)

    result = subprocess.run(command, cwd=ROOT)
    if result.returncode != 0:
        return result.returncode

    if not known.apply:
        print("NOTE: canonical child bootstrap will remove vendor-only paths on --apply:")
        for relative in vendor_only_paths:
            print(f"- {relative}")
        return 0

    removed: list[str] = []
    for relative in vendor_only_paths:
        target = ROOT / relative
        try:
            target.relative_to(ROOT)
        except ValueError:
            print(f"ERROR: vendor-only target escaped repository root: {relative}", file=sys.stderr)
            return 2
        if target.is_dir():
            shutil.rmtree(target)
            removed.append(relative)
        elif target.exists():
            target.unlink()
            removed.append(relative)

    print("Vendor-only source removed from child repository:" if removed else "No vendor-only source present in child repository.")
    for relative in removed:
        print(f"- {relative}")
    print("NEXT: commit the generated child initialization changes, including vendor-only removals, before project development.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
