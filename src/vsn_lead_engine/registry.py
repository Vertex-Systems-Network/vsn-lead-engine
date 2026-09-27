from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Iterable

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from .dedupe import fingerprints
from .models import Lead
from .normalize import normalize_domain, normalize_name, normalize_phone


TOKEN_DIGEST_BYTES = 12  # 96-bit BLAKE2. R2 object keys never contain raw lead PII.


def registry_mode(config: dict) -> str:
    return str(config.get("registry", {}).get("mode", "sheets")).strip().lower()


def r2_registry_enabled(config: dict) -> bool:
    return registry_mode(config) in {"dual", "r2"}


def fingerprint_token(kind: str, value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return ""
    digest = hashlib.blake2b(
        f"{kind}\0{normalized}".encode("utf-8"),
        digest_size=TOKEN_DIGEST_BYTES,
    ).hexdigest()
    return f"{kind}:{digest}"


def fingerprint_tokens_from_values(
    *,
    unique_key: str,
    google_place_id: str = "",
    source_id: str = "",
    normalized_domain: str = "",
    phone_name_key: str = "",
    business_location_key: str = "",
) -> list[str]:
    # Unique Key is derived from place/domain/phone-name/biz-location, so storing
    # another permanent object for it would duplicate one of these dimensions.
    values = [
        ("p", google_place_id),
        ("s", source_id),
        ("d", normalized_domain),
        ("n", phone_name_key),
        ("l", business_location_key),
    ]
    tokens = sorted(
        token for kind, value in values
        if (token := fingerprint_token(kind, value))
    )
    # Defensive fallback for malformed legacy rows lacking all normal dimensions.
    if not tokens and unique_key:
        tokens.append(fingerprint_token("u", unique_key))
    return tokens


def lead_fingerprint_tokens(lead: Lead) -> list[str]:
    fp = fingerprints(lead)
    return fingerprint_tokens_from_values(
        unique_key=fp.unique,
        google_place_id=fp.place_id,
        source_id=fp.source_id,
        normalized_domain=fp.domain,
        phone_name_key=fp.phone_name,
        business_location_key=fp.business_location,
    )


def lead_registry_payload(lead: Lead, workbook: dict) -> dict:
    fp = fingerprints(lead)
    return {
        "unique_token": fingerprint_token("u", fp.unique),
        "fingerprints": lead_fingerprint_tokens(lead),
        "daily_sheet_id": str(workbook.get("id", "")).strip(),
        "category": lead.category,
    }


def extract_sheet_id(value: str) -> str:
    match = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", str(value or ""))
    return match.group(1) if match else ""


class R2RegistryIndex:
    """Exact permanent dedupe ledger backed by private Cloudflare R2 objects."""

    def __init__(self, config: dict, client=None):
        settings = config.get("registry", {})
        self.prefix = str(settings.get("prefix", "vsn-lead-ledger/v1")).strip("/")
        self.max_workers = max(4, int(settings.get("max_workers", 32)))
        self.retry_attempts = max(1, int(settings.get("retry_attempts", 4)))
        self._batch_by_token: dict[str, str] = {}

        account_env = str(settings.get("account_id_env", "R2_ACCOUNT_ID"))
        access_env = str(settings.get("access_key_id_env", "R2_ACCESS_KEY_ID"))
        secret_env = str(settings.get("secret_access_key_env", "R2_SECRET_ACCESS_KEY"))
        bucket_env = str(settings.get("bucket_env", "R2_BUCKET"))

        account_id = os.getenv(account_env, "").strip()
        access_key = os.getenv(access_env, "").strip()
        secret_key = os.getenv(secret_env, "").strip()
        self.bucket = os.getenv(bucket_env, "").strip()

        if not all([account_id, access_key, secret_key, self.bucket]):
            raise RuntimeError(
                "R2 Registry requires GitHub secrets "
                f"{account_env}, {access_env}, {secret_env}, and {bucket_env}."
            )

        self.client = client or boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="auto",
            config=Config(
                retries={"max_attempts": self.retry_attempts, "mode": "standard"},
                max_pool_connections=max(64, self.max_workers * 2),
                connect_timeout=10,
                read_timeout=30,
            ),
        )

    def close(self):
        close = getattr(self.client, "close", None)
        if callable(close):
            close()

    def verify(self) -> dict:
        self.client.head_bucket(Bucket=self.bucket)
        return {"status": "ready", "bucket": self.bucket, "prefix": self.prefix}

    @staticmethod
    def _error_status(exc: ClientError) -> int:
        return int(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0) or 0)

    @staticmethod
    def _error_code(exc: ClientError) -> str:
        return str(exc.response.get("Error", {}).get("Code", ""))

    @classmethod
    def _is_missing(cls, exc: ClientError) -> bool:
        return cls._error_status(exc) == 404 or cls._error_code(exc) in {
            "404", "NoSuchKey", "NotFound"
        }

    @classmethod
    def _is_precondition(cls, exc: ClientError) -> bool:
        return cls._error_status(exc) == 412 or cls._error_code(exc) in {
            "412", "PreconditionFailed"
        }

    def _fingerprint_key(self, token: str) -> str:
        kind, digest = token.split(":", 1)
        return f"{self.prefix}/fp/{kind}/{digest[:2]}/{digest}"

    def _pending_key(self, batch_id: str) -> str:
        return f"{self.prefix}/pending/{batch_id}.json"

    def _token_exists(self, token: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._fingerprint_key(token))
            return True
        except ClientError as exc:
            if self._is_missing(exc):
                return False
            raise

    def collision_keys(self, leads: Iterable[Lead]) -> set[str]:
        token_to_candidates: dict[str, set[str]] = {}
        for lead in leads:
            fp = fingerprints(lead)
            unique_token = fingerprint_token("u", fp.unique)
            if not unique_token:
                continue
            for token in lead_fingerprint_tokens(lead):
                token_to_candidates.setdefault(token, set()).add(unique_token)

        existing_tokens: set[str] = set()
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {pool.submit(self._token_exists, token): token for token in token_to_candidates}
            for future in as_completed(futures):
                token = futures[future]
                if future.result():
                    existing_tokens.add(token)

        collisions: set[str] = set()
        for token in existing_tokens:
            collisions.update(token_to_candidates[token])
        return collisions

    def _put_if_absent(
        self,
        *,
        key: str,
        owner: str,
        body: bytes = b"",
        content_type: str = "application/octet-stream",
    ) -> bool:
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body,
                ContentType=content_type,
                Metadata={"owner": owner},
                IfNoneMatch="*",
            )
            return True
        except ClientError as exc:
            if self._is_precondition(exc):
                return False
            raise

    def _owner_matches(self, key: str, owner: str) -> bool:
        try:
            response = self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if self._is_missing(exc):
                return False
            raise
        metadata = response.get("Metadata", {}) or {}
        return str(metadata.get("owner", "")).strip().lower() == owner.lower()

    def _delete_owned(self, key: str, owner: str):
        if self._owner_matches(key, owner):
            self.client.delete_object(Bucket=self.bucket, Key=key)

    def _reserve_row(self, row: dict) -> str:
        unique_token = row["unique_token"]
        created: list[str] = []
        try:
            for token in row["fingerprints"]:
                key = self._fingerprint_key(token)
                made = self._put_if_absent(key=key, owner=unique_token)
                if made:
                    created.append(token)
                    continue
                if self._owner_matches(key, unique_token):
                    continue
                for made_token in created:
                    self._delete_owned(self._fingerprint_key(made_token), unique_token)
                return ""
            return unique_token
        except Exception:
            for made_token in created:
                self._delete_owned(self._fingerprint_key(made_token), unique_token)
            raise

    def reserve_pending(self, leads: Iterable[Lead], workbook: dict) -> set[str]:
        rows = [lead_registry_payload(lead, workbook) for lead in leads]
        if not rows:
            return set()

        batch_id = uuid.uuid4().hex
        marker_key = self._pending_key(batch_id)
        initial = {
            "batch_id": batch_id,
            "daily_sheet_id": str(workbook.get("id", "")).strip(),
            "category": rows[0]["category"],
            "rows": rows,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.client.put_object(
            Bucket=self.bucket,
            Key=marker_key,
            Body=json.dumps(initial, separators=(",", ":")).encode("utf-8"),
            ContentType="application/json",
        )

        reserved: set[str] = set()
        try:
            with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
                futures = [pool.submit(self._reserve_row, row) for row in rows]
                for future in as_completed(futures):
                    token = future.result()
                    if token:
                        reserved.add(token)

            reserved_rows = [row for row in rows if row["unique_token"] in reserved]
            if not reserved_rows:
                self.client.delete_object(Bucket=self.bucket, Key=marker_key)
                return set()

            marker = {**initial, "rows": reserved_rows, "state": "reserved"}
            self.client.put_object(
                Bucket=self.bucket,
                Key=marker_key,
                Body=json.dumps(marker, separators=(",", ":")).encode("utf-8"),
                ContentType="application/json",
            )
            for token in reserved:
                self._batch_by_token[token] = batch_id
            return reserved
        except Exception:
            for row in rows:
                for token in row["fingerprints"]:
                    self._delete_owned(self._fingerprint_key(token), row["unique_token"])
            self.client.delete_object(Bucket=self.bucket, Key=marker_key)
            raise

    def _get_pending_batch(self, batch_id: str) -> dict | None:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self._pending_key(batch_id))
        except ClientError as exc:
            if self._is_missing(exc):
                return None
            raise
        return json.loads(response["Body"].read().decode("utf-8"))

    def _rollback_batch(self, batch: dict):
        for row in batch.get("rows", []) or []:
            owner = str(row.get("unique_token", "")).strip().lower()
            for token in row.get("fingerprints", []) or []:
                self._delete_owned(self._fingerprint_key(token), owner)
        batch_id = str(batch.get("batch_id", "")).strip()
        if batch_id:
            self.client.delete_object(Bucket=self.bucket, Key=self._pending_key(batch_id))

    def activate(self, unique_tokens: Iterable[str]) -> int:
        tokens = {str(token).strip().lower() for token in unique_tokens if str(token).strip()}
        batches = {self._batch_by_token.get(token, "") for token in tokens}
        for batch_id in {item for item in batches if item}:
            self.client.delete_object(Bucket=self.bucket, Key=self._pending_key(batch_id))
        for token in tokens:
            self._batch_by_token.pop(token, None)
        return len(tokens)

    def mark_retryable(self, unique_tokens: Iterable[str]) -> int:
        tokens = {str(token).strip().lower() for token in unique_tokens if str(token).strip()}
        batch_ids = {self._batch_by_token.get(token, "") for token in tokens}
        changed = 0
        for batch_id in {item for item in batch_ids if item}:
            batch = self._get_pending_batch(batch_id)
            if batch is not None:
                self._rollback_batch(batch)
                changed += len(batch.get("rows", []) or [])
        for token in tokens:
            self._batch_by_token.pop(token, None)
        return changed

    def shadow_active(self, leads: Iterable[Lead], workbook: dict) -> dict[str, int]:
        leads = list(leads)
        reserved = self.reserve_pending(leads, workbook)
        activated = self.activate(reserved) if reserved else 0
        return {
            "requested": len(leads),
            "reserved": len(reserved),
            "activated": activated,
            "conflicts": len(leads) - len(reserved),
        }

    def pending_rows(self) -> list[dict]:
        prefix = f"{self.prefix}/pending/"
        paginator = self.client.get_paginator("list_objects_v2")
        batches: list[dict] = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for item in page.get("Contents", []) or []:
                response = self.client.get_object(Bucket=self.bucket, Key=item["Key"])
                batches.append(json.loads(response["Body"].read().decode("utf-8")))
        return batches

    def reconcile_pending(self, sheets_store) -> dict[str, int]:
        batches = self.pending_rows()
        if not batches:
            return {"batches": 0, "checked": 0, "activated": 0, "rolled_back": 0, "unresolved": 0}

        checked = activated = rolled_back = unresolved = 0
        for batch in batches:
            sheet_id = str(batch.get("daily_sheet_id", "")).strip()
            category = str(batch.get("category", "")).strip()
            rows = batch.get("rows", []) or []
            checked += len(rows)
            if not sheet_id or not category:
                self._rollback_batch(batch)
                rolled_back += len(rows)
                continue

            escaped = category.replace("'", "''")
            try:
                values = sheets_store.sheets.spreadsheets().values().get(
                    spreadsheetId=sheet_id,
                    range=f"'{escaped}'!AB2:AB",
                ).execute(num_retries=sheets_store.api_retries).get("values", [])
            except Exception:
                unresolved += len(rows)
                continue

            present = {
                fingerprint_token("u", str(item[0]).strip())
                for item in values
                if item and str(item[0]).strip()
            }
            keep = []
            rollback = []
            for row in rows:
                if row.get("unique_token", "") in present:
                    keep.append(row)
                else:
                    rollback.append(row)

            for row in rollback:
                owner = row.get("unique_token", "")
                for token in row.get("fingerprints", []) or []:
                    self._delete_owned(self._fingerprint_key(token), owner)
            activated += len(keep)
            rolled_back += len(rollback)
            self.client.delete_object(Bucket=self.bucket, Key=self._pending_key(batch["batch_id"]))

        return {
            "batches": len(batches),
            "checked": checked,
            "activated": activated,
            "rolled_back": rolled_back,
            "unresolved": unresolved,
        }

    def _import_row(self, payload: dict) -> str:
        owner = payload["unique_token"]
        created: list[str] = []
        try:
            for token in payload["fingerprints"]:
                key = self._fingerprint_key(token)
                made = self._put_if_absent(key=key, owner=owner)
                if made:
                    created.append(token)
                    continue
                if self._owner_matches(key, owner):
                    continue
                for made_token in created:
                    self._delete_owned(self._fingerprint_key(made_token), owner)
                return "collision"
            return "imported" if created else "existing"
        except Exception:
            for made_token in created:
                self._delete_owned(self._fingerprint_key(made_token), owner)
            raise

    def import_rows(self, rows: list[dict]) -> dict[str, int]:
        counts = {"imported": 0, "existing": 0, "collision": 0, "skipped": 0}
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = [pool.submit(self._import_row, row) for row in rows]
            for future in as_completed(futures):
                counts[future.result()] += 1
        return counts

    def audit_rows(self, rows: list[dict]) -> dict[str, int]:
        tokens = {token for row in rows for token in row.get("fingerprints", [])}
        found = 0
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = [pool.submit(self._token_exists, token) for token in tokens]
            for future in as_completed(futures):
                if future.result():
                    found += 1
        return {
            "blocking_rows": len(rows),
            "expected_fingerprints": len(tokens),
            "found_fingerprints": found,
            "missing_fingerprints": len(tokens) - found,
        }

    def stats(self) -> dict:
        stats = {"fingerprint_objects": 0, "pending_transactions": 0, "bytes": 0}
        paginator = self.client.get_paginator("list_objects_v2")
        for name, prefix in [
            ("fingerprint_objects", f"{self.prefix}/fp/"),
            ("pending_transactions", f"{self.prefix}/pending/"),
        ]:
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                contents = page.get("Contents", []) or []
                stats[name] += len(contents)
                stats["bytes"] += sum(int(item.get("Size", 0) or 0) for item in contents)
        return stats


def build_registry_index(config: dict, client=None):
    if not r2_registry_enabled(config):
        return None

    layout = str(
        config.get("registry", {}).get("layout", "objects-v1")
    ).strip().lower()
    if layout == "packed-v2":
        from .packed_registry import PackedR2RegistryIndex

        return PackedR2RegistryIndex(config, client=client)
    return R2RegistryIndex(config, client=client)


def sheet_registry_payloads(rows: list[list]) -> list[dict]:
    if not rows:
        return []
    header = rows[0]
    index = {str(name).strip(): position for position, name in enumerate(header)}

    def cell(row, name):
        position = index.get(name)
        return str(row[position]).strip() if position is not None and position < len(row) else ""

    result = []
    for row in rows[1:]:
        raw_unique = cell(row, "Unique Key").lower()
        if not raw_unique:
            continue
        normalized_status = re.sub(r"[^a-z0-9]+", "", cell(row, "Status").lower())
        if normalized_status not in {"", "active", "pendingdaily"}:
            continue

        country = cell(row, "Country")
        name = cell(row, "Business Name")
        normalized_phone = normalize_phone(cell(row, "Phone"), country)
        phone_name_key = (
            f"{normalized_phone}|{normalize_name(name)}"
            if normalized_phone and name else ""
        )
        verification = cell(row, "Verification Sources")
        source_match = re.search(r"Source ID:\s*([^;|]+)", verification, re.I)
        source_id = source_match.group(1).strip().lower() if source_match else ""

        tokens = fingerprint_tokens_from_values(
            unique_key=raw_unique,
            google_place_id=cell(row, "Google Place ID").lower(),
            source_id=source_id,
            normalized_domain=(
                cell(row, "Normalized Domain")
                or normalize_domain(cell(row, "Website"))
            ),
            phone_name_key=phone_name_key,
            business_location_key=cell(row, "Business+City+State Key"),
        )
        result.append({
            "unique_token": fingerprint_token("u", raw_unique),
            "fingerprints": tokens,
            "daily_sheet_id": extract_sheet_id(cell(row, "Daily Sheet URL")),
            "category": cell(row, "Category") or cell(row, "Field"),
        })
    return result


def backfill_sheet_registry(
    sheets_store,
    registry_index: R2RegistryIndex,
    *,
    dry_run: bool = False,
) -> dict:
    rows = sheets_store._registry_rows()
    payloads = sheet_registry_payloads(rows)
    source_rows = max(0, len(rows) - 1)
    skipped_nonblocking = source_rows - len(payloads)
    if dry_run:
        return {
            "status": "dry-run",
            "source_rows": source_rows,
            "blocking_rows": len(payloads),
            "skipped_nonblocking": skipped_nonblocking,
            "fingerprints": sum(len(row["fingerprints"]) for row in payloads),
        }
    result = registry_index.import_rows(payloads)
    return {
        "status": "ok",
        "source_rows": source_rows,
        "blocking_rows": len(payloads),
        "skipped_nonblocking": skipped_nonblocking,
        **result,
    }


def audit_sheet_registry(sheets_store, registry_index: R2RegistryIndex) -> dict:
    rows = sheet_registry_payloads(sheets_store._registry_rows())
    return registry_index.audit_rows(rows)



def live_smoke_test(config: dict) -> dict:
    """Exercise the real R2 transaction path in an isolated temporary prefix."""
    smoke_id=uuid.uuid4().hex
    smoke_config={
        **config,
        "registry":{
            **config.get("registry",{}),
            "prefix":f"{str(config.get('registry',{}).get('prefix','vsn-lead-ledger/v1')).strip('/')}/smoke/{smoke_id}",
        },
    }
    index=build_registry_index(smoke_config)
    if index is None:
        raise RuntimeError("Registry smoke requires an enabled R2 registry.")
    lead=Lead(
        country="United States",
        category="IT & Software",
        business_name=f"VSN Registry Smoke {smoke_id[:12]}",
        phone="+12025550199",
        city="Smoke City",
        region="Smoke Region",
        source="VSN R2 Smoke",
        source_id=f"smoke:{smoke_id}",
        website=f"https://{smoke_id}.invalid",
    )
    workbook={"id":"smoke-sheet"}
    payload=lead_registry_payload(lead,workbook)
    unique_token=payload["unique_token"]
    before=index.collision_keys([lead])
    reserved=index.reserve_pending([lead],workbook)
    during=index.collision_keys([lead])
    rolled_back=index.mark_retryable(reserved)
    after=index.collision_keys([lead])
    pending=index.pending_rows()
    stats=index.stats()
    index.close()

    ok=(
        before==set()
        and reserved=={unique_token}
        and during=={unique_token}
        and rolled_back==1
        and after==set()
        and not pending
        and int(stats.get("fingerprint_objects",0) or 0)==0
        and int(stats.get("pending_transactions",0) or 0)==0
    )
    return {
        "status":"ok" if ok else "failed",
        "reserved":len(reserved),
        "collision_before":len(before),
        "collision_during":len(during),
        "collision_after":len(after),
        "rolled_back":rolled_back,
        "pending_transactions":len(pending),
        "remaining_fingerprint_objects":int(stats.get("fingerprint_objects",0) or 0),
    }
