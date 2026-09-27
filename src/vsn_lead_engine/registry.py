from __future__ import annotations

import os
import re
from collections import defaultdict
from typing import Iterable

import requests

from .dedupe import fingerprints
from .models import Lead
from .normalize import normalize_domain, normalize_name, normalize_phone


BLOCKING_STATUSES = {"active", "pendingdaily"}


def registry_mode(config: dict) -> str:
    return str(config.get("registry", {}).get("mode", "sheets")).strip().lower()


def supabase_registry_enabled(config: dict) -> bool:
    return registry_mode(config) in {"dual", "supabase"}


def _nullable(value: str) -> str | None:
    value = str(value or "").strip()
    return value or None


def lead_registry_payload(lead: Lead, workbook: dict) -> dict:
    fp = fingerprints(lead)
    normalized_phone = normalize_phone(lead.phone, lead.country)
    return {
        "first_added": lead.date_added,
        "category": lead.category,
        "country": lead.country,
        "city": lead.city,
        "business_name": lead.business_name,
        "website": lead.website,
        "normalized_domain": _nullable(normalize_domain(lead.website)),
        "phone": lead.phone,
        "normalized_phone": normalized_phone,
        "phone_name_key": _nullable(fp.phone_name),
        "business_location_key": _nullable(fp.business_location),
        "unique_key": fp.unique,
        "daily_sheet": workbook.get("name", ""),
        "daily_sheet_url": workbook.get(
            "webViewLink",
            f'https://docs.google.com/spreadsheets/d/{workbook.get("id", "")}/edit',
        ),
        "status": "PendingDaily",
        "region": lead.region,
        "postal_code": lead.postal_code,
        "google_place_id": _nullable(fp.place_id),
        "source": lead.source,
        "source_id": _nullable(fp.source_id),
        "verification_sources": f"{lead.source}; Source ID: {lead.source_id}",
    }


def collision_payload(lead: Lead) -> dict:
    fp = fingerprints(lead)
    return {
        "candidate_unique_key": fp.unique,
        "google_place_id": _nullable(fp.place_id),
        "source_id": _nullable(fp.source_id),
        "normalized_domain": _nullable(fp.domain),
        "phone_name_key": _nullable(fp.phone_name),
        "business_location_key": _nullable(fp.business_location),
    }


def extract_sheet_id(value: str) -> str:
    match = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", str(value or ""))
    return match.group(1) if match else ""


class SupabaseRegistryIndex:
    """Private service-role client for the scalable Registry backend."""

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
                key = str(row.get("candidate_unique_key", "")).strip().lower()
                if key:
                    result.add(key)
        return result

    def reserve_pending(self, leads: Iterable[Lead], workbook: dict) -> set[str]:
        rows = [lead_registry_payload(lead, workbook) for lead in leads]
        inserted: set[str] = set()
        for chunk in self._chunks(rows, self.batch_size):
            data = self._rpc("vsn_lead_registry_reserve", {"p_rows": chunk}) or []
            for row in data:
                key = str(row.get("unique_key", "")).strip().lower()
                if key:
                    inserted.add(key)
        return inserted

    def activate(self, unique_keys: Iterable[str]) -> int:
        keys = sorted({str(key).strip().lower() for key in unique_keys if str(key).strip()})
        changed = 0
        for chunk in self._chunks(keys, self.batch_size):
            result = self._rpc("vsn_lead_registry_activate", {"p_keys": chunk})
            changed += int(result or 0)
        return changed

    def mark_retryable(self, unique_keys: Iterable[str]) -> int:
        keys = sorted({str(key).strip().lower() for key in unique_keys if str(key).strip()})
        changed = 0
        for chunk in self._chunks(keys, self.batch_size):
            result = self._rpc("vsn_lead_registry_mark_retryable", {"p_keys": chunk})
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

    def reconcile_pending(self, sheets_store) -> dict[str, int]:
        pending = self.pending_rows()
        if not pending:
            return {"checked": 0, "activated": 0, "retryable": 0, "unresolved": 0}

        grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
        direct_retry: list[dict] = []
        for row in pending:
            sheet_id = extract_sheet_id(row.get("daily_sheet_url", ""))
            category = str(row.get("category", "")).strip()
            unique_key = str(row.get("unique_key", "")).strip().lower()
            if not sheet_id or not category or not unique_key:
                direct_retry.append(row)
                continue
            grouped[(sheet_id, category)].append(row)

        activate_keys: set[str] = set()
        retryable_keys: set[str] = {
            str(row.get("unique_key", "")).strip().lower()
            for row in direct_retry
            if str(row.get("unique_key", "")).strip()
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
                str(item[0]).strip().lower()
                for item in values
                if item and str(item[0]).strip()
            }
            for row in rows:
                key = str(row.get("unique_key", "")).strip().lower()
                if key in present:
                    activate_keys.add(key)
                else:
                    retryable_keys.add(key)

        activated = self.activate(activate_keys) if activate_keys else 0
        retryable = self.mark_retryable(retryable_keys) if retryable_keys else 0
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
    allowed_statuses = {
        "PendingDaily","Active","NeedsReview","Retryable",
        "Rejected","Invalid","Quarantined",
    }
    for row in rows[1:]:
        unique_key = cell(row, "Unique Key").lower()
        if not unique_key:
            continue
        country = cell(row, "Country")
        name = cell(row, "Business Name")
        phone = normalize_phone(cell(row, "Phone"), country)
        raw_status = cell(row, "Status")
        normalized_status = re.sub(r"[^a-z0-9]+", "", raw_status.lower())
        status_map = {
            "pendingdaily":"PendingDaily",
            "active":"Active",
            "needsreview":"NeedsReview",
            "retryable":"Retryable",
            "writefailed":"Retryable",
            "rejected":"Rejected",
            "invalid":"Invalid",
            "quarantined":"Quarantined",
        }
        status = status_map.get(normalized_status, "Active")
        if status not in allowed_statuses:
            status = "Active"
        verification = cell(row, "Verification Sources")
        source_match = re.search(r"Source ID:\s*([^;|]+)", verification, re.I)
        source_id = source_match.group(1).strip().lower() if source_match else ""
        result.append({
            "first_added": cell(row, "First Added"),
            "category": cell(row, "Category") or cell(row, "Field"),
            "country": country,
            "city": cell(row, "City"),
            "business_name": name,
            "website": cell(row, "Website"),
            "normalized_domain": _nullable(
                cell(row, "Normalized Domain") or normalize_domain(cell(row, "Website"))
            ),
            "phone": cell(row, "Phone"),
            "normalized_phone": phone,
            "phone_name_key": _nullable(
                f"{phone}|{normalize_name(name)}" if phone and name else ""
            ),
            "business_location_key": _nullable(cell(row, "Business+City+State Key")),
            "unique_key": unique_key,
            "daily_sheet": cell(row, "Daily Sheet"),
            "daily_sheet_url": cell(row, "Daily Sheet URL"),
            "status": status,
            "region": cell(row, "State/Province"),
            "postal_code": cell(row, "ZIP/Postal Code"),
            "google_place_id": _nullable(cell(row, "Google Place ID").lower()),
            "source": cell(row, "Primary Source"),
            "source_id": _nullable(source_id),
            "verification_sources": verification,
        })
    return result


def backfill_sheet_registry(sheets_store, registry_index: SupabaseRegistryIndex, *, dry_run: bool=False) -> dict:
    payloads = sheet_registry_payloads(sheets_store._registry_rows())
    status_counts: dict[str, int] = {}
    for row in payloads:
        status = row["status"]
        status_counts[status] = status_counts.get(status, 0) + 1
    if dry_run:
        return {
            "status": "dry-run",
            "rows": len(payloads),
            "status_counts": status_counts,
        }
    inserted = registry_index.import_rows(payloads)
    return {
        "status": "ok",
        "rows": len(payloads),
        "inserted": inserted,
        "status_counts": status_counts,
    }
