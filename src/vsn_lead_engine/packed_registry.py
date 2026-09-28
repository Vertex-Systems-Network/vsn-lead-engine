from __future__ import annotations

import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Iterable

from botocore.exceptions import ClientError

from .dedupe import fingerprints
from .models import Lead
from .registry import (
    TOKEN_DIGEST_BYTES,
    R2RegistryIndex,
    fingerprint_token,
    lead_fingerprint_tokens,
    lead_registry_payload,
)


class PackedR2RegistryIndex(R2RegistryIndex):
    """Exact R2 dedupe ledger with compact sharded immutable-token packs.

    Permanent v2 fingerprints are stored as fixed-width 96-bit binary digests
    inside a small number of shard objects instead of one R2 object per token.
    Legacy v1 objects remain readable indefinitely, so cutover is zero-loss.
    """

    LAYOUT = "packed-v2"

    def __init__(self, config: dict, client=None):
        super().__init__(config, client=client)
        settings = config.get("registry", {})
        self.pack_shard_chars = max(1, min(2, int(settings.get("pack_shard_chars", 1))))
        self.lock_stale_seconds = max(30, int(settings.get("lock_stale_seconds", 180)))
        self.read_cache_enabled = bool(settings.get("read_cache_enabled", True))
        self.pack_commit_workers = max(
            1,
            min(
                self.max_workers,
                int(settings.get("pack_commit_workers", 16)),
            ),
        )
        self.pending_read_cache_enabled = bool(
            settings.get("pending_read_cache_enabled", True)
        )
        self.read_cache_max_entries = max(
            16,
            min(1024, int(settings.get("read_cache_max_entries", 128))),
        )
        self._pack_cache: dict[str,set[str]] = {}
        self._legacy_cache: dict[str,bool] = {}
        self._pending_cache: set[str] | None = None
        self._pack_cache_lock = threading.Lock()
        self._pack_cache_hits = 0
        self._pack_cache_misses = 0
        self._legacy_cache_hits = 0
        self._legacy_cache_misses = 0
        self._pending_cache_hits = 0
        self._pending_cache_misses = 0
        self.legacy_read_cache_max_entries = max(
            64,
            min(20000, int(settings.get("legacy_read_cache_max_entries", 4096))),
        )

    def verify(self) -> dict:
        result = super().verify()
        return {
            **result,
            "layout": self.LAYOUT,
            "pack_shard_chars": self.pack_shard_chars,
            "pack_commit_workers": self.pack_commit_workers,
            "read_cache_enabled": self.read_cache_enabled,
            "pending_read_cache_enabled": self.pending_read_cache_enabled,
            "read_cache_max_entries": self.read_cache_max_entries,
            "legacy_read_cache_max_entries": self.legacy_read_cache_max_entries,
        }

    def _pack_key(self, token: str) -> str:
        kind, digest = token.split(":", 1)
        shard = digest[: self.pack_shard_chars]
        return f"{self.prefix}/packs/v2/{kind}/{shard}.bin"

    def _lock_key(self) -> str:
        return f"{self.prefix}/locks/packed-v2.lock"

    def _decode_pack(self, body: bytes) -> set[str]:
        if not body:
            return set()
        if len(body) % TOKEN_DIGEST_BYTES:
            raise RuntimeError(
                f"Packed Registry object has invalid byte length {len(body)}; "
                f"expected a multiple of {TOKEN_DIGEST_BYTES}."
            )
        return {
            body[offset : offset + TOKEN_DIGEST_BYTES].hex()
            for offset in range(0, len(body), TOKEN_DIGEST_BYTES)
        }

    @staticmethod
    def _encode_pack(digests: Iterable[str]) -> bytes:
        return b"".join(bytes.fromhex(digest) for digest in sorted(set(digests)))

    def _read_pack(self, key: str, *, use_cache: bool = False) -> set[str]:
        if use_cache and self.read_cache_enabled:
            with self._pack_cache_lock:
                cached=self._pack_cache.get(key)
                if cached is not None:
                    self._pack_cache_hits += 1
                    return set(cached)

        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if self._is_missing(exc):
                digests=set()
            else:
                raise
        else:
            digests=self._decode_pack(response["Body"].read())

        if use_cache and self.read_cache_enabled:
            with self._pack_cache_lock:
                self._pack_cache_misses += 1
                self._pack_cache[key]=set(digests)
                while len(self._pack_cache) > self.read_cache_max_entries:
                    oldest=next(iter(self._pack_cache))
                    self._pack_cache.pop(oldest,None)
        return set(digests)

    def _write_pack(self, key: str, digests: set[str]) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=self._encode_pack(digests),
            ContentType="application/octet-stream",
            Metadata={
                "layout": self.LAYOUT,
                "digest-bytes": str(TOKEN_DIGEST_BYTES),
            },
        )
        if self.read_cache_enabled:
            with self._pack_cache_lock:
                self._pack_cache[key]=set(digests)
                while len(self._pack_cache) > self.read_cache_max_entries:
                    oldest=next(iter(self._pack_cache))
                    self._pack_cache.pop(oldest,None)

    def cache_stats(self) -> dict[str,int | bool]:
        with self._pack_cache_lock:
            return {
                "enabled":self.read_cache_enabled,
                "entries":len(self._pack_cache),
                "hits":self._pack_cache_hits,
                "misses":self._pack_cache_misses,
                "legacy_entries":len(self._legacy_cache),
                "legacy_hits":self._legacy_cache_hits,
                "legacy_misses":self._legacy_cache_misses,
                "pending_enabled":self.pending_read_cache_enabled,
                "pending_entries":len(self._pending_cache or set()),
                "pending_hits":self._pending_cache_hits,
                "pending_misses":self._pending_cache_misses,
            }

    def clear_read_cache(self) -> None:
        with self._pack_cache_lock:
            self._pack_cache.clear()
            self._legacy_cache.clear()
            self._pending_cache=None

    def _invalidate_pending_cache(self) -> None:
        with self._pack_cache_lock:
            self._pending_cache=None

    def _packed_hits(
        self,
        tokens: Iterable[str],
        *,
        use_cache: bool = False,
    ) -> set[str]:
        groups: dict[str, list[tuple[str, str]]] = {}
        for token in set(tokens):
            if not token:
                continue
            _kind, digest = token.split(":", 1)
            groups.setdefault(self._pack_key(token), []).append((token, digest))

        hits: set[str] = set()
        if not groups:
            return hits

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(groups))) as pool:
            futures = {
                pool.submit(self._read_pack,key,use_cache=use_cache):key
                for key in groups
            }
            for future in as_completed(futures):
                key = futures[future]
                packed = future.result()
                for token, digest in groups[key]:
                    if digest in packed:
                        hits.add(token)
        return hits

    def _legacy_hits(
        self,
        tokens: Iterable[str],
        *,
        use_cache: bool = False,
    ) -> set[str]:
        requested={token for token in tokens if token}
        if not requested:
            return set()

        hits:set[str]=set()
        uncached=set(requested)
        if use_cache and self.read_cache_enabled:
            with self._pack_cache_lock:
                uncached=set()
                for token in requested:
                    if token in self._legacy_cache:
                        self._legacy_cache_hits += 1
                        if self._legacy_cache[token]:
                            hits.add(token)
                    else:
                        uncached.add(token)

        if uncached:
            resolved:dict[str,bool]={}
            with ThreadPoolExecutor(
                max_workers=min(self.max_workers,len(uncached))
            ) as pool:
                futures={
                    pool.submit(self._token_exists,token):token
                    for token in uncached
                }
                for future in as_completed(futures):
                    token=futures[future]
                    exists=bool(future.result())
                    resolved[token]=exists
                    if exists:
                        hits.add(token)

            if use_cache and self.read_cache_enabled:
                with self._pack_cache_lock:
                    self._legacy_cache_misses += len(resolved)
                    for token,exists in resolved.items():
                        self._legacy_cache[token]=exists
                    while len(self._legacy_cache) > self.legacy_read_cache_max_entries:
                        oldest=next(iter(self._legacy_cache))
                        self._legacy_cache.pop(oldest,None)

        return hits

    def _existing_tokens(
        self,
        tokens: Iterable[str],
        *,
        use_cache: bool = False,
    ) -> set[str]:
        requested = {token for token in tokens if token}
        packed = self._packed_hits(requested,use_cache=use_cache)
        # Historical v1 fingerprints remain authoritative until an explicit
        # compaction migration removes them in a later, independently audited step.
        legacy = self._legacy_hits(
            requested - packed,
            use_cache=use_cache,
        )
        return packed | legacy

    def _pending_tokens(
        self,
        *,
        exclude_batch_ids: set[str] | None = None,
        use_cache: bool = False,
    ) -> set[str]:
        excluded = exclude_batch_ids or set()
        cacheable=(
            use_cache
            and self.read_cache_enabled
            and self.pending_read_cache_enabled
            and not excluded
        )

        if cacheable:
            with self._pack_cache_lock:
                if self._pending_cache is not None:
                    self._pending_cache_hits += 1
                    return set(self._pending_cache)

        tokens: set[str] = set()
        for batch in self.pending_rows():
            if str(batch.get("batch_id", "")) in excluded:
                continue
            for row in batch.get("rows", []) or []:
                tokens.update(row.get("fingerprints", []) or [])

        if cacheable:
            with self._pack_cache_lock:
                self._pending_cache_misses += 1
                self._pending_cache=set(tokens)
        return tokens

    def collision_keys(self, leads: Iterable[Lead]) -> set[str]:
        token_to_candidates: dict[str, set[str]] = {}
        for lead in leads:
            fp = fingerprints(lead)
            unique_token = fingerprint_token("u", fp.unique)
            if not unique_token:
                continue
            for token in lead_fingerprint_tokens(lead):
                token_to_candidates.setdefault(token, set()).add(unique_token)

        candidate_tokens = set(token_to_candidates)
        blocked = self._existing_tokens(candidate_tokens,use_cache=True)
        blocked.update(
            candidate_tokens & self._pending_tokens(use_cache=True)
        )

        collisions: set[str] = set()
        for token in blocked:
            collisions.update(token_to_candidates.get(token, set()))
        return collisions

    def _lock_info(self) -> tuple[str, datetime | None]:
        key = self._lock_key()
        try:
            head = self.client.head_object(Bucket=self.bucket, Key=key)
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if self._is_missing(exc):
                return "", None
            raise

        owner = str((head.get("Metadata", {}) or {}).get("owner", "")).strip()
        created_at = None
        try:
            payload = json.loads(response["Body"].read().decode("utf-8"))
            raw_created = str(payload.get("created_at", "")).strip()
            if raw_created:
                created_at = datetime.fromisoformat(raw_created.replace("Z", "+00:00"))
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError, json.JSONDecodeError):
            created_at = None
        return owner, created_at

    def _acquire_lock(self) -> str:
        owner = uuid.uuid4().hex
        key = self._lock_key()

        for _attempt in range(2):
            payload = {
                "owner": owner,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "layout": self.LAYOUT,
            }
            if self._put_if_absent(
                key=key,
                owner=owner,
                body=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
                content_type="application/json",
            ):
                return owner

            existing_owner, created_at = self._lock_info()
            if created_at is None:
                raise RuntimeError("Packed Registry lock is busy and has no safe expiry evidence.")

            age = (datetime.now(timezone.utc) - created_at.astimezone(timezone.utc)).total_seconds()
            if age <= self.lock_stale_seconds:
                raise RuntimeError(
                    f"Packed Registry lock is busy (age={int(age)}s, "
                    f"stale_after={self.lock_stale_seconds}s)."
                )

            # A stale lock is safe to reap only when the owner observed by HEAD
            # still owns the exact lock object at delete time.
            if existing_owner:
                self._delete_owned(key, existing_owner)

        raise RuntimeError("Unable to acquire Packed Registry lock after stale-lock recovery.")

    def _release_lock(self, owner: str) -> None:
        if owner:
            self._delete_owned(self._lock_key(), owner)

    def import_rows(self, rows: list[dict]) -> dict[str,int]:
        result=super().import_rows(rows)
        # import_rows mutates historical objects-v1; discard any advisory
        # positive/negative cache so subsequent checks observe the new state.
        with self._pack_cache_lock:
            self._legacy_cache.clear()
        return result

    def reserve_pending(self, leads: Iterable[Lead], workbook: dict) -> set[str]:
        rows = [lead_registry_payload(lead, workbook) for lead in leads]
        if not rows:
            return set()

        lock_owner = self._acquire_lock()
        try:
            all_tokens = {
                token
                for row in rows
                for token in row.get("fingerprints", []) or []
            }
            blocked = self._existing_tokens(all_tokens)
            blocked.update(self._pending_tokens())

            accepted_rows: list[dict] = []
            seen = set(blocked)
            for row in rows:
                row_tokens = set(row.get("fingerprints", []) or [])
                if not row_tokens or row_tokens & seen:
                    continue
                accepted_rows.append(row)
                seen.update(row_tokens)

            if not accepted_rows:
                return set()

            batch_id = uuid.uuid4().hex
            marker = {
                "batch_id": batch_id,
                "layout": self.LAYOUT,
                "daily_sheet_id": str(workbook.get("id", "")).strip(),
                "category": accepted_rows[0]["category"],
                "rows": accepted_rows,
                "state": "reserved",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self.client.put_object(
                Bucket=self.bucket,
                Key=self._pending_key(batch_id),
                Body=json.dumps(marker, separators=(",", ":")).encode("utf-8"),
                ContentType="application/json",
            )
            self._invalidate_pending_cache()

            reserved = {row["unique_token"] for row in accepted_rows}
            for token in reserved:
                self._batch_by_token[token] = batch_id
            return reserved
        finally:
            self._release_lock(lock_owner)

    def _merge_pack_additions(self, key: str, additions: set[str]) -> bool:
        """Merge one already-lock-protected pack shard and report if written."""
        current = self._read_pack(key)
        merged = current | additions
        if merged == current:
            return False
        self._write_pack(key, merged)
        return True

    def _commit_rows_to_packs(self, rows: Iterable[dict]) -> int:
        groups: dict[str, set[str]] = {}
        token_count = 0
        for row in rows:
            for token in row.get("fingerprints", []) or []:
                _kind, digest = token.split(":", 1)
                groups.setdefault(self._pack_key(token), set()).add(digest)
                token_count += 1

        if not groups:
            return token_count

        workers = min(self.pack_commit_workers, len(groups))
        if workers <= 1:
            for key, additions in groups.items():
                self._merge_pack_additions(key, additions)
            return token_count

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(self._merge_pack_additions, key, additions): key
                for key, additions in groups.items()
            }
            for future in as_completed(futures):
                future.result()

        return token_count

    def _find_batches_for_tokens(self, tokens: set[str]) -> dict[str, dict]:
        batch_ids = {self._batch_by_token.get(token, "") for token in tokens}
        found: dict[str, dict] = {}

        for batch_id in {item for item in batch_ids if item}:
            batch = self._get_pending_batch(batch_id)
            if batch is not None:
                found[batch_id] = batch

        unresolved = {
            token
            for token in tokens
            if not self._batch_by_token.get(token, "")
        }
        if unresolved:
            for batch in self.pending_rows():
                batch_id = str(batch.get("batch_id", "")).strip()
                if not batch_id or batch_id in found:
                    continue
                row_tokens = {
                    str(row.get("unique_token", "")).strip().lower()
                    for row in batch.get("rows", []) or []
                }
                if row_tokens & unresolved:
                    found[batch_id] = batch
        return found

    def activate(self, unique_tokens: Iterable[str]) -> int:
        tokens = {
            str(token).strip().lower()
            for token in unique_tokens
            if str(token).strip()
        }
        if not tokens:
            return 0

        lock_owner = self._acquire_lock()
        changed = 0
        try:
            batches = self._find_batches_for_tokens(tokens)
            for batch_id, batch in batches.items():
                rows = batch.get("rows", []) or []
                selected = [
                    row
                    for row in rows
                    if str(row.get("unique_token", "")).strip().lower() in tokens
                ]
                if not selected:
                    continue

                if str(batch.get("layout", "")).strip().lower() == self.LAYOUT:
                    self._commit_rows_to_packs(selected)
                # Legacy pending markers already reserved v1 fingerprint objects;
                # activation only needs to clear their marker.

                selected_ids = {
                    str(row.get("unique_token", "")).strip().lower()
                    for row in selected
                }
                remaining = [
                    row
                    for row in rows
                    if str(row.get("unique_token", "")).strip().lower() not in selected_ids
                ]
                if remaining:
                    updated = {**batch, "rows": remaining}
                    self.client.put_object(
                        Bucket=self.bucket,
                        Key=self._pending_key(batch_id),
                        Body=json.dumps(updated, separators=(",", ":")).encode("utf-8"),
                        ContentType="application/json",
                    )
                else:
                    self.client.delete_object(
                        Bucket=self.bucket,
                        Key=self._pending_key(batch_id),
                    )
                changed += len(selected_ids)

            for token in tokens:
                self._batch_by_token.pop(token, None)
            return changed
        finally:
            self._invalidate_pending_cache()
            self._release_lock(lock_owner)

    def mark_retryable(self, unique_tokens: Iterable[str]) -> int:
        tokens = {
            str(token).strip().lower()
            for token in unique_tokens
            if str(token).strip()
        }
        if not tokens:
            return 0

        lock_owner = self._acquire_lock()
        changed = 0
        try:
            batches = self._find_batches_for_tokens(tokens)
            for batch_id, batch in batches.items():
                rows = batch.get("rows", []) or []
                selected = [
                    row
                    for row in rows
                    if str(row.get("unique_token", "")).strip().lower() in tokens
                ]
                if not selected:
                    continue

                if str(batch.get("layout", "")).strip().lower() != self.LAYOUT:
                    # Legacy v1 reservations created permanent objects before the
                    # Sheet write; failed writes must still roll those back.
                    for row in selected:
                        owner = str(row.get("unique_token", "")).strip().lower()
                        for token in row.get("fingerprints", []) or []:
                            self._delete_owned(self._fingerprint_key(token), owner)

                selected_ids = {
                    str(row.get("unique_token", "")).strip().lower()
                    for row in selected
                }
                remaining = [
                    row
                    for row in rows
                    if str(row.get("unique_token", "")).strip().lower() not in selected_ids
                ]
                if remaining:
                    updated = {**batch, "rows": remaining}
                    self.client.put_object(
                        Bucket=self.bucket,
                        Key=self._pending_key(batch_id),
                        Body=json.dumps(updated, separators=(",", ":")).encode("utf-8"),
                        ContentType="application/json",
                    )
                else:
                    self.client.delete_object(
                        Bucket=self.bucket,
                        Key=self._pending_key(batch_id),
                    )
                changed += len(selected_ids)

            for token in tokens:
                self._batch_by_token.pop(token, None)
            return changed
        finally:
            self._invalidate_pending_cache()
            self._release_lock(lock_owner)

    def reconcile_pending(self, sheets_store) -> dict[str, int]:
        batches = self.pending_rows()
        if not batches:
            self._invalidate_pending_cache()
            return {
                "batches": 0,
                "checked": 0,
                "activated": 0,
                "rolled_back": 0,
                "unresolved": 0,
            }

        checked = activated = rolled_back = unresolved = 0
        for batch in batches:
            sheet_id = str(batch.get("daily_sheet_id", "")).strip()
            category = str(batch.get("category", "")).strip()
            rows = batch.get("rows", []) or []
            checked += len(rows)

            if not sheet_id or not category:
                if str(batch.get("layout", "")).strip().lower() != self.LAYOUT:
                    self._rollback_batch(batch)
                else:
                    self.client.delete_object(
                        Bucket=self.bucket,
                        Key=self._pending_key(batch["batch_id"]),
                    )
                rolled_back += len(rows)
                continue

            escaped = category.replace("'", "''")
            try:
                values = (
                    sheets_store.sheets.spreadsheets()
                    .values()
                    .get(
                        spreadsheetId=sheet_id,
                        range=f"'{escaped}'!AB2:AB",
                    )
                    .execute(num_retries=sheets_store.api_retries)
                    .get("values", [])
                )
            except Exception:
                unresolved += len(rows)
                continue

            present = {
                fingerprint_token("u", str(item[0]).strip())
                for item in values
                if item and str(item[0]).strip()
            }
            keep = [
                row
                for row in rows
                if str(row.get("unique_token", "")).strip().lower() in present
            ]
            rollback = [
                row
                for row in rows
                if str(row.get("unique_token", "")).strip().lower() not in present
            ]

            lock_owner = self._acquire_lock()
            try:
                if str(batch.get("layout", "")).strip().lower() == self.LAYOUT:
                    if keep:
                        self._commit_rows_to_packs(keep)
                else:
                    for row in rollback:
                        owner = str(row.get("unique_token", "")).strip().lower()
                        for token in row.get("fingerprints", []) or []:
                            self._delete_owned(self._fingerprint_key(token), owner)

                self.client.delete_object(
                    Bucket=self.bucket,
                    Key=self._pending_key(batch["batch_id"]),
                )
            finally:
                self._release_lock(lock_owner)

            activated += len(keep)
            rolled_back += len(rollback)

        self._invalidate_pending_cache()
        return {
            "batches": len(batches),
            "checked": checked,
            "activated": activated,
            "rolled_back": rolled_back,
            "unresolved": unresolved,
        }

    def audit_rows(self, rows: list[dict]) -> dict[str, int]:
        tokens = {
            token
            for row in rows
            for token in row.get("fingerprints", []) or []
        }
        found_tokens = self._existing_tokens(tokens)
        return {
            "blocking_rows": len(rows),
            "expected_fingerprints": len(tokens),
            "found_fingerprints": len(found_tokens),
            "missing_fingerprints": len(tokens - found_tokens),
        }

    def stats(self) -> dict:
        stats = super().stats()
        stats.update({"packed_objects": 0, "packed_tokens": 0})
        prefix = f"{self.prefix}/packs/v2/"
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            contents = page.get("Contents", []) or []
            stats["packed_objects"] += len(contents)
            packed_bytes = sum(int(item.get("Size", 0) or 0) for item in contents)
            stats["bytes"] += packed_bytes
            stats["packed_tokens"] += packed_bytes // TOKEN_DIGEST_BYTES
        stats["layout"] = self.LAYOUT
        stats["pack_shard_chars"] = self.pack_shard_chars
        return stats
