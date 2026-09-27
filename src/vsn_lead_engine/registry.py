from __future__ import annotations

import hashlib
import os
import re
from collections import defaultdict
from typing import Iterable

import requests

from .dedupe import fingerprints
from .models import Lead
from .normalize import normalize_domain, normalize_name, normalize_phone


BLOCKING_STATUSES = {"active", "pendingdaily"}
TOKEN_DIGEST_BYTES = 12  # 96-bit BLAKE2 digest; compact with negligible collision risk.


def registry_mode(config: dict) -> str:
    return str(config.get("registry", {}).get("mode", "sheets")).strip().lower()


def supabase_registry_enabled(config: dict) -> bool:
    return registry_mode(config) in {"dual", "supabase"}


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
    values = [
        ("u", unique_key),
        ("p", google_place_id),
        ("s", source_id),
        ("d", normalized_domain),
        ("n", phone_name_key),
        ("l", business_location_key),
    ]
    return sorted(
        token for kind, value in values
        if (token := fingerprint_token(kind, value))
    )


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


def country_code(country: str) -> str:
    normalized = str(country or "").strip().lower()
    if normalized in {"united states", "united states of america", "usa", "us"}:
        return "US"
    if normalized in {"canada", "ca"}:
        return "CA"
    return str(country or "").strip()[:2].upper()


def lead_registry_payload(lead: Lead, workbook: dict) -> dict:
    fp = fingerprints(lead)
    return {
        "first_added": lead.date_added,
        "category": lead.category,
        "country_code": country_code(lead.country),
        "unique_token": fingerprint_token("u", fp.unique),
        "fingerprints": lead_fingerprint_tokens(lead),
        "daily_sheet_id": str(workbook.get("id", "")).strip(),
        "status": "PendingDaily",
    }


def collision_payload(lead: Lead) -> dict:
    fp = fingerprints(lead)
    return {
        "candidate_unique_token": fingerprint_token("u", fp.unique),
        "fingerprints": lead_fingerprint_tokens(lead),
    }


def extract_sheet_id(value: str) -> str:
    match = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", str(value or ""))
    return match.group(1) if match else ""


class SupabaseRegistryIndex:
    """Private service-role client for the compact scalable Registry backend."""

    def __init__(self, config: dict, session=None):
        settings = config.get("registry", {})
        url_env = str(settings.get("supabase_url_env", "SUPABASE_URL"))
        key_env = str(
            settings.get(
                "supabase_service_role_key_env",
                "SUPABASE_SERVICE_ROLE_KEY",
            )
        )
        self.url = os.getenv(url_env, "").strip().rstrip("/")
        self.key = os.getenv(key_env, "").strip()
        if not self.url or not self.key:
            raise RuntimeError(
                f"Supabase Registry requires GitHub secrets {url_env} and {key_env}."
            )
        self.timeout = float(settings.get("request_timeout_seconds", 30))
        self.batch_size = max(1, int(settings.get("batch_size", 500)))
        self.session = session or requests.Session()
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }

    def close(self):
        close = getattr(self.session, "close", None)
        if callable(close):
            close()

    def _rpc(self, function: str, payload: dict):
        response = self.session.post(
            f"{self.url}/rest/v1/rpc/{function}",
            headers=self.headers,
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        if not response.content:
            return None
        return response.json()

    @staticmethod
    def _chunks(items: list, size: int):
        for start in range(0, len(items), size):
            yield items[start:start + size]

    def collision_keys(self, leads: Iterable[Lead]) -> set[str]:
        rows = [collision_payload(lead) for lead in leads]
        result: set[str] = set()
        for chunk in self._chunks(rows, self.batch_size):
            data = self._rpc("vsn_lead_registry_collisions", {"p_rows": chunk}) or []
            for row in data:
                token = str(row.get("candidate_unique_token", "")).strip().lower()
                if token:
                    result.add(token)
        return result

    def reserve_pending(self, leads: Iterable[Lead], workbook: dict) -> set[str]:
        rows = [lead_registry_payload(lead, workbook) for lead in leads]
        inserted: set[str] = set()
        for chunk in self._chunks(rows, self.batch_size):
            data = self._rpc("vsn_lead_registry_reserve", {"p_rows": chunk}) or []
            for row in data:
                token = str(row.get("unique_token", "")).strip().lower()
                if token:
                    inserted.add(token)
        return inserted

    def activate(self, unique_tokens: Iterable[str]) -> int:
        tokens = sorted({
            str(token).strip().lower()
            for token in unique_tokens
            if str(token).strip()
        })
        changed = 0
        for chunk in self._chunks(tokens, self.batch_size):
            result = self._rpc("vsn_lead_registry_activate", {"p_tokens": chunk})
            changed += int(result or 0)
        return changed

    def mark_retryable(self, unique_tokens: Iterable[str]) -> int:
        tokens = sorted({
            str(token).strip().lower()
            for token in unique_tokens
            if str(token).strip()
        })
        changed = 0
        for chunk in self._chunks(tokens, self.batch_size):
            result = self._rpc("vsn_lead_registry_mark_retryable", {"p_tokens": chunk})
            changed += int(result or 0)
        return changed

    def shadow_active(self, leads: Iterable[Lead], workbook: dict) -> dict[str, int]:
        leads = list(leads)
        inserted = self.reserve_pending(leads, workbook)
        activated = self.activate(inserted) if inserted else 0
        return {"inserted": len(inserted), "activated": activated}

    def import_rows(self, rows: list[dict]) -> int:
        inserted = 0
        for chunk in self._chunks(rows, self.batch_size):
            data = self._rpc("vsn_lead_registry_import", {"p_rows": chunk}) or []
            inserted += len(data)
        return inserted

    def pending_rows(self) -> list[dict]:
        data = self._rpc("vsn_lead_registry_pending", {}) or []
        return [row for row in data if isinstance(row, dict)]

    def stats(self) -> dict:
        data = self._rpc("vsn_lead_registry_stats", {}) or {}
        if isinstance(data, list):
            return data[0] if data else {}
        return data if isinstance(data, dict) else {}

    def capacity_report(self, *, daily_leads: int, database_budget_mb: int) -> dict:
        stats = self.stats()
        total_rows = int(stats.get("total_rows", 0) or 0)
        relation_bytes = int(stats.get("total_bytes", 0) or 0)
        database_bytes = int(stats.get("database_bytes", 0) or 0)
        budget_bytes = int(database_budget_mb) * 1024 * 1024
        bytes_per_row = relation_bytes / total_rows if total_rows else 0.0
        projected_daily_bytes = bytes_per_row * int(daily_leads)
        remaining_bytes = max(0, budget_bytes - database_bytes)
        days = (
            remaining_bytes / projected_daily_bytes
            if projected_daily_bytes > 0 else None
        )
        return {
            **stats,
            "database_budget_mb": int(database_budget_mb),
            "bytes_per_registry_row": round(bytes_per_row, 2),
            "projected_daily_registry_bytes": round(projected_daily_bytes, 2),
            "estimated_headroom_days": round(days, 1) if days is not None else None,
        }

    def reconcile_pending(self, sheets_store) -> dict[str, int]:
        pending = self.pending_rows()
        if not pending:
            return {"checked": 0, "activated": 0, "retryable": 0, "unresolved": 0}

        grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
        direct_retry: list[dict] = []
        for row in pending:
            sheet_id = str(row.get("daily_sheet_id", "")).strip()
            category = str(row.get("category", "")).strip()
            unique_token = str(row.get("unique_token", "")).strip().lower()
            if not sheet_id or not category or not unique_token:
                direct_retry.append(row)
                continue
            grouped[(sheet_id, category)].append(row)

        activate_tokens: set[str] = set()
        retryable_tokens: set[str] = {
            str(row.get("unique_token", "")).strip().lower()
            for row in direct_retry
            if str(row.get("unique_token", "")).strip()
        }
        unresolved = 0

        for (spreadsheet_id, category), rows in grouped.items():
            escaped = category.replace("'", "''")
            try:
                values = sheets_store.sheets.spreadsheets().values().get(
                    spreadsheetId=spreadsheet_id,
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
            for row in rows:
                token = str(row.get("unique_token", "")).strip().lower()
                if token in present:
                    activate_tokens.add(token)
                else:
                    retryable_tokens.add(token)

        activated = self.activate(activate_tokens) if activate_tokens else 0
        retryable = self.mark_retryable(retryable_tokens) if retryable_tokens else 0
        return {
            "checked": len(pending),
            "activated": activated,
            "retryable": retryable,
            "unresolved": unresolved,
        }


def build_registry_index(config: dict, session=None):
    if not supabase_registry_enabled(config):
        return None
    return SupabaseRegistryIndex(config, session=session)


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

        raw_status = cell(row, "Status")
        normalized_status = re.sub(r"[^a-z0-9]+", "", raw_status.lower())
        # Only blocking rows belong in the permanent compact dedupe index.
        if normalized_status not in {"", "active", "pendingdaily"}:
            continue
        status = "PendingDaily" if normalized_status == "pendingdaily" else "Active"

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
        daily_sheet_id = extract_sheet_id(cell(row, "Daily Sheet URL"))

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
            "first_added": cell(row, "First Added"),
            "category": cell(row, "Category") or cell(row, "Field"),
            "country_code": country_code(country),
            "unique_token": fingerprint_token("u", raw_unique),
            "fingerprints": tokens,
            "daily_sheet_id": daily_sheet_id,
            "status": status,
        })
    return result


def backfill_sheet_registry(
    sheets_store,
    registry_index: SupabaseRegistryIndex,
    *,
    dry_run: bool=False,
) -> dict:
    rows = sheets_store._registry_rows()
    payloads = sheet_registry_payloads(rows)
    source_rows = max(0, len(rows) - 1)
    skipped_nonblocking = source_rows - len(payloads)
    status_counts: dict[str, int] = {}
    for row in payloads:
        status = row["status"]
        status_counts[status] = status_counts.get(status, 0) + 1
    if dry_run:
        return {
            "status": "dry-run",
            "source_rows": source_rows,
            "rows": len(payloads),
            "skipped_nonblocking": skipped_nonblocking,
            "status_counts": status_counts,
        }
    inserted = registry_index.import_rows(payloads)
    return {
        "status": "ok",
        "source_rows": source_rows,
        "rows": len(payloads),
        "inserted": inserted,
        "skipped_nonblocking": skipped_nonblocking,
        "status_counts": status_counts,
    }
