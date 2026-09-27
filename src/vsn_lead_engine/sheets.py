from __future__ import annotations

import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .dedupe import fingerprints
from .models import Lead
from .normalize import business_city_key, business_location_key, normalize_domain, normalize_name, normalize_phone
from .scoring import pitch, score_lead

DAILY_COLUMNS = [
    "Date Added","Country","Category","Business Name","Phone","Email","Website","Website Status",
    "Instagram","Facebook","LinkedIn","X/Twitter","TikTok","Google Maps URL","Street Address","City",
    "State/Province","ZIP/Postal Code","Latitude","Longitude","Nearby / Landmark / Neighborhood","Rating",
    "Reviews","Contact Person","Lead Score","Pitch","Outreach Status","Unique Key","Notes"
]

REGISTRY_COLUMNS = [
    "First Added","Field","Region","Country","City","Category","Business Name","Website",
    "Normalized Domain","Phone","Normalized Phone","Business+City Key","Unique Key","Daily Sheet",
    "Daily Sheet URL","Status","State/Province","ZIP/Postal Code","Google Place ID","Primary Source",
    "Verification Sources","Business+City+State Key"
]

OVERVIEW_INCREMENT_METRICS = [
    "Duplicate Rejections",
    "Missing-Phone Rejections",
    "Free-Source Candidates",
    "Shard Attempts",
    "Zero-Result Shards",
    "Source Errors",
]


def count_current_rows(date_rows, status_rows, today: str) -> int:
    """Count today's usable leads, excluding rows quarantined for review."""
    total = 0
    max_rows = max(len(date_rows), len(status_rows))
    for index in range(max_rows):
        date_value = date_rows[index][0] if index < len(date_rows) and date_rows[index] else ""
        status_value = status_rows[index][0] if index < len(status_rows) and status_rows[index] else ""
        if str(date_value).strip() == today and str(status_value).strip().lower() != "needs review":
            total += 1
    return total


def count_current_countries(date_country_rows, status_rows, today: str) -> dict[str, int]:
    """Count today's usable leads by country."""
    counts: dict[str, int] = {}
    max_rows = max(len(date_country_rows), len(status_rows))
    for index in range(max_rows):
        row = date_country_rows[index] if index < len(date_country_rows) else []
        date_value = row[0] if len(row) > 0 else ""
        country_value = row[1] if len(row) > 1 else ""
        status_value = status_rows[index][0] if index < len(status_rows) and status_rows[index] else ""
        if str(date_value).strip() != today:
            continue
        if str(status_value).strip().lower() == "needs review":
            continue
        country = str(country_value).strip()
        if country:
            counts[country] = counts.get(country, 0) + 1
    return counts


def registry_status_blocks_dedupe(status: str) -> bool:
    """Return whether a Registry row should block future discovery."""
    normalized = re.sub(r"[^a-z0-9]+", "", str(status or "").lower())
    if normalized in {"needsreview", "rejected", "invalid", "quarantined"}:
        return False
    return True


def daily_workbook_title(prefix: str, date_value: str) -> str:
    return f"{prefix}{date_value}"


def escape_drive_query_value(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


class GoogleSheetsStore:
    def __init__(self, config: dict):
        raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        if not raw:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is required for real writes.")
        creds = service_account.Credentials.from_service_account_info(
            json.loads(raw),
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ],
        )
        self.sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
        self.drive = build("drive", "v3", credentials=creds, cache_discovery=False)
        self.config = config

    def _today(self) -> str:
        return datetime.now(ZoneInfo(self.config["runtime"]["timezone"])).date().isoformat()

    def _daily_title(self, date_value: str | None = None) -> str:
        prefix = self.config["drive"].get(
            "daily_title_prefix", "US + Canada Business Leads — "
        )
        return daily_workbook_title(prefix, date_value or self._today())

    def _find_daily_workbook(self, title: str) -> dict | None:
        folder_id = self.config["drive"]["folder_id"]
        escaped_title = escape_drive_query_value(title)
        escaped_folder = escape_drive_query_value(folder_id)
        query = (
            f"name = '{escaped_title}' and "
            f"'{escaped_folder}' in parents and "
            "trashed = false and "
            "mimeType = 'application/vnd.google-apps.spreadsheet'"
        )
        response = self.drive.files().list(
            q=query,
            spaces="drive",
            fields="files(id,name,webViewLink,createdTime)",
            orderBy="createdTime asc",
            pageSize=10,
        ).execute()
        files = response.get("files", [])
        if not files:
            return None
        # Concurrency is serialized by GitHub Actions. If an old accidental
        # duplicate exists, keep one deterministic canonical file.
        return files[0]

    def _create_daily_workbook(self, title: str) -> dict:
        template_id = self.config["drive"]["daily_template_spreadsheet_id"]
        folder_id = self.config["drive"]["folder_id"]
        try:
            created = self.drive.files().copy(
                fileId=template_id,
                body={"name": title, "parents": [folder_id]},
                fields="id,name,webViewLink,createdTime",
            ).execute()
        except HttpError as exc:
            status = getattr(exc.resp, "status", None)
            if status in {403, 429}:
                raise RuntimeError(
                    "Today's lead workbook is missing and the Google service account "
                    "could not create it in this My Drive folder. A user-owned daily "
                    "workbook precreator must create the dated file first."
                ) from exc
            raise

        self._initialize_new_daily_workbook(created["id"])
        return created

    def _initialize_new_daily_workbook(self, spreadsheet_id: str):
        date_value = self._today()
        metadata = self.sheets.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            fields="properties(title,timeZone),sheets.properties",
        ).execute()
        self._ensure_tabs(spreadsheet_id, metadata)

        # A copied template must start clean. Preserve header rows and tab
        # formatting while removing any old lead rows.
        for category in self.config["categories"]:
            self.sheets.spreadsheets().values().clear(
                spreadsheetId=spreadsheet_id,
                range=f"'{category}'!A2:AC",
                body={},
            ).execute()
            self.sheets.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"'{category}'!A1:AC1",
                valueInputOption="RAW",
                body={"values": [DAILY_COLUMNS]},
            ).execute()

        self.sheets.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range="'Overview'!A:B",
            body={},
        ).execute()
        self.sheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range="'Overview'!A1",
            valueInputOption="USER_ENTERED",
            body={"values": self._overview_seed(date_value)},
        ).execute()

    def ensure_lead_workbook(self):
        date_value = self._today()
        title = self._daily_title(date_value)
        file = self._find_daily_workbook(title)
        created = False
        if file is None:
            file = self._create_daily_workbook(title)
            created = True

        sid = file["id"]
        metadata = self.sheets.spreadsheets().get(
            spreadsheetId=sid,
            fields="properties(title,timeZone),sheets.properties",
        ).execute()
        self._ensure_tabs(sid, metadata)
        self._ensure_overview_metrics(sid)
        self._refresh_overview_formulas(sid, date_value)
        self.set_overview_metrics(
            sid,
            {
                "Notes": (
                    f"Daily workbook for {date_value}. Events append to this file only; "
                    "Master Registry remains cross-day dedupe source."
                )
            },
        )
        return {
            "id": sid,
            "name": metadata.get("properties", {}).get("title", title),
            "webViewLink": file.get(
                "webViewLink", f"https://docs.google.com/spreadsheets/d/{sid}/edit"
            ),
            "date": date_value,
            "created": created,
        }

    def _overview_seed(self, date_value: str | None = None):
        date_value = date_value or self._today()
        categories = self.config["categories"]
        target = int(self.config["runtime"]["daily_target_per_category"])
        rows = [
            ["VSN Lead Engine — Daily US + Canada Workbook",""],
            ["Metric","Value"],
            ["Tracking Date",date_value],
            ["Countries","United States + Canada"],
            ["Daily Target / Category",target],
            ["Total Daily Target",target * len(categories)],
        ]
        for category in categories:
            rows.append([
                f"Actual — {category}",
                f'=COUNTIFS(\'{category}\'!A:A,$B$3,\'{category}\'!AA:AA,"<>Needs Review")',
            ])
        for category in categories:
            rows.append([
                f"Shortfall — {category}",
                f'=MAX($B$5-COUNTIFS(\'{category}\'!A:A,$B$3,\'{category}\'!AA:AA,"<>Needs Review"),0)',
            ])
        rows.extend([
            ["Total Actual Today","=SUM(B7:B18)"],
            ["Total Shortfall Today","=MAX(B6-B31,0)"],
            ["Status",'=IF(B31>=B6,"Complete","In Progress")'],
            ["Duplicate Rejections",0],
            ["Missing-Phone Rejections",0],
            ["Free-Source Candidates",0],
            ["Shard Attempts",0],
            ["Zero-Result Shards",0],
            ["Source Errors",0],
            ["United States Leads Today",0],
            ["Canada Leads Today",0],
            ["Primary Free Source","Overture Maps Places"],
            ["Notes",f"Daily workbook for {date_value}."],
        ])
        return rows

    def _ensure_tabs(self, spreadsheet_id: str, metadata: dict | None = None):
        if metadata is None:
            metadata = self.sheets.spreadsheets().get(
                spreadsheetId=spreadsheet_id, fields="sheets.properties"
            ).execute()
        props = [s["properties"] for s in metadata.get("sheets", [])]
        existing = {p["title"] for p in props}
        wanted = ["Overview", *self.config["categories"]]
        requests = [
            {"addSheet":{"properties":{"title":name}}}
            for name in wanted if name not in existing
        ]
        if requests:
            self.sheets.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id, body={"requests":requests}
            ).execute()

        for name in wanted:
            row = self.sheets.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id, range=f"'{name}'!1:1"
            ).execute().get("values", [])
            if row:
                continue
            values = self._overview_seed() if name == "Overview" else [DAILY_COLUMNS]
            self.sheets.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"'{name}'!A1",
                valueInputOption="USER_ENTERED",
                body={"values":values}
            ).execute()

    def _ensure_overview_metrics(self, spreadsheet_id: str):
        rows=self.sheets.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range="'Overview'!A1:B100",
        ).execute().get("values",[])
        existing={str(row[0]).strip() for row in rows if row}
        missing=[[metric,0] for metric in OVERVIEW_INCREMENT_METRICS if metric not in existing]
        for metric in ["United States Leads Today","Canada Leads Today"]:
            if metric not in existing:
                missing.append([metric,0])
        if "Primary Free Source" not in existing:
            missing.append(["Primary Free Source","Overture Maps Places"])
        if "Notes" not in existing:
            missing.append(["Notes",f"Daily workbook for {self._today()}."])
        if missing:
            self.sheets.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range="'Overview'!A:B",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values":missing},
            ).execute()

    def _refresh_overview_formulas(self, spreadsheet_id: str, date_value: str | None = None):
        date_value = date_value or self._today()
        categories = self.config["categories"]
        target = int(self.config["runtime"]["daily_target_per_category"])
        data = [
            {"range":"'Overview'!A1","values":[["VSN Lead Engine — Daily US + Canada Workbook"]]},
            {"range":"'Overview'!B3","values":[[date_value]]},
        ]
        actual_start = 7
        shortfall_start = actual_start + len(categories)

        for offset, category in enumerate(categories):
            escaped = category.replace("'", "''")
            actual_row = actual_start + offset
            shortfall_row = shortfall_start + offset
            formula = (
                f'=COUNTIFS(\'{escaped}\'!A:A,$B$3,'
                f'\'{escaped}\'!AA:AA,"<>Needs Review")'
            )
            data.append({"range":f"'Overview'!B{actual_row}","values":[[formula]]})
            data.append({
                "range":f"'Overview'!B{shortfall_row}",
                "values":[[f"=MAX($B$5-B{actual_row},0)"]],
            })

        total_actual_row = shortfall_start + len(categories)
        total_shortfall_row = total_actual_row + 1
        data.extend([
            {
                "range":f"'Overview'!B{total_actual_row}",
                "values":[[f"=SUM(B{actual_start}:B{actual_start+len(categories)-1})"]],
            },
            {
                "range":f"'Overview'!B{total_shortfall_row}",
                "values":[[f"=MAX({target*len(categories)}-B{total_actual_row},0)"]],
            },
        ])
        self.sheets.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"valueInputOption":"USER_ENTERED","data":data},
        ).execute()

    def category_counts(self, spreadsheet_id: str) -> dict[str,int]:
        today = self._today()
        ranges = []
        for category in self.config["categories"]:
            ranges.extend([f"'{category}'!A2:A", f"'{category}'!AA2:AA"])

        response = self.sheets.spreadsheets().values().batchGet(
            spreadsheetId=spreadsheet_id,
            ranges=ranges,
            valueRenderOption="UNFORMATTED_VALUE",
        ).execute()
        value_ranges = response.get("valueRanges", [])
        counts = {}
        for index, category in enumerate(self.config["categories"]):
            date_index = index * 2
            status_index = date_index + 1
            date_rows = value_ranges[date_index].get("values", []) if date_index < len(value_ranges) else []
            status_rows = value_ranges[status_index].get("values", []) if status_index < len(value_ranges) else []
            counts[category] = count_current_rows(date_rows, status_rows, today)
        return counts

    def daily_country_counts(self, spreadsheet_id: str) -> dict[str, int]:
        today = self._today()
        ranges = []
        for category in self.config["categories"]:
            ranges.extend([f"'{category}'!A2:B", f"'{category}'!AA2:AA"])

        response = self.sheets.spreadsheets().values().batchGet(
            spreadsheetId=spreadsheet_id,
            ranges=ranges,
            valueRenderOption="UNFORMATTED_VALUE",
        ).execute()
        value_ranges = response.get("valueRanges", [])
        result: dict[str, int] = {}

        for index, _category in enumerate(self.config["categories"]):
            date_country_index = index * 2
            status_index = date_country_index + 1
            date_country_rows = (
                value_ranges[date_country_index].get("values", [])
                if date_country_index < len(value_ranges)
                else []
            )
            status_rows = (
                value_ranges[status_index].get("values", [])
                if status_index < len(value_ranges)
                else []
            )
            counts = count_current_countries(date_country_rows, status_rows, today)
            for country, count in counts.items():
                result[country] = result.get(country, 0) + count

        for country in ["United States", "Canada"]:
            result.setdefault(country, 0)
        return result

    def _registry_rows(self):
        sid = self.config["drive"]["master_registry_spreadsheet_id"]
        tab = self.config["drive"]["master_registry_tab"]
        return self.sheets.spreadsheets().values().get(
            spreadsheetId=sid, range=f"'{tab}'!A:V"
        ).execute().get("values", [])

    def registry_fingerprints(self):
        rows = self._registry_rows()
        sid = self.config["drive"]["master_registry_spreadsheet_id"]
        tab = self.config["drive"]["master_registry_tab"]
        if not rows:
            self.sheets.spreadsheets().values().update(
                spreadsheetId=sid,
                range=f"'{tab}'!A1",
                valueInputOption="RAW",
                body={"values":[REGISTRY_COLUMNS]}
            ).execute()
            return {k:set() for k in ["place_id","source_id","domain","phone_name","business_location","unique"]}

        header = rows[0]
        required = {"Country","City","Business Name","Website","Phone","Unique Key","Status","State/Province"}
        missing = required.difference(header)
        if missing:
            raise RuntimeError(f"Master Registry schema missing required columns: {sorted(missing)}")

        index = {name:i for i,name in enumerate(header)}
        result = {k:set() for k in ["place_id","source_id","domain","phone_name","business_location","unique"]}

        def cell(row, name):
            i = index.get(name)
            return str(row[i]).strip() if i is not None and i < len(row) else ""

        for row in rows[1:]:
            status = cell(row,"Status")
            if not registry_status_blocks_dedupe(status):
                continue

            country = cell(row,"Country")
            name = cell(row,"Business Name")
            city = cell(row,"City")
            region = cell(row,"State/Province")
            raw_phone = cell(row,"Phone")
            phone = normalize_phone(raw_phone,country)
            domain = normalize_domain(cell(row,"Website") or cell(row,"Normalized Domain"))
            place_id = cell(row,"Google Place ID").lower()
            bizloc = cell(row,"Business+City+State Key").lower() or business_location_key(name,city,region)
            unique = cell(row,"Unique Key").lower()
            verification = cell(row,"Verification Sources")
            source_match = re.search(r"Source ID:\s*([^;|]+)",verification,re.I)
            source_id = source_match.group(1).strip().lower() if source_match else ""

            if place_id: result["place_id"].add(place_id)
            if source_id: result["source_id"].add(source_id)
            if domain: result["domain"].add(domain)
            if phone and name: result["phone_name"].add(f"{phone}|{normalize_name(name)}")
            if bizloc: result["business_location"].add(bizloc)
            if unique: result["unique"].add(unique)

        return result

    @staticmethod
    def _column_letter(index_zero_based: int) -> str:
        n = index_zero_based + 1
        out = ""
        while n:
            n, rem = divmod(n - 1,26)
            out = chr(65 + rem) + out
        return out

    def commit_leads(self, workbook: dict, leads: list[Lead]):
        if not leads:
            return
        category = leads[0].category
        if any(lead.category != category for lead in leads):
            raise ValueError("A commit batch must contain a single category.")

        registry_id = self.config["drive"]["master_registry_spreadsheet_id"]
        registry_tab = self.config["drive"]["master_registry_tab"]
        registry_rows = []
        daily_rows = []

        for lead in leads:
            fp = fingerprints(lead)
            normalized_phone = normalize_phone(lead.phone, lead.country)
            registry_rows.append([
                lead.date_added,
                lead.category,
                "North America",
                lead.country,
                lead.city,
                lead.category,
                lead.business_name,
                lead.website,
                normalize_domain(lead.website),
                lead.phone,
                normalized_phone,
                business_city_key(lead.business_name,lead.city),
                fp.unique,
                workbook["name"],
                workbook.get("webViewLink",f'https://docs.google.com/spreadsheets/d/{workbook["id"]}/edit'),
                "PendingDaily",
                lead.region,
                lead.postal_code,
                lead.google_place_id,
                lead.source,
                f"{lead.source}; Source ID: {lead.source_id}",
                fp.business_location,
            ])

            score = score_lead(lead)
            daily_rows.append([
                lead.date_added,lead.country,lead.category,lead.business_name,lead.phone,lead.email,
                lead.website,lead.website_status,lead.instagram,lead.facebook,lead.linkedin,lead.twitter,
                lead.tiktok,lead.google_maps_url,lead.street_address,lead.city,
                lead.region,lead.postal_code,lead.latitude if lead.latitude is not None else "",
                lead.longitude if lead.longitude is not None else "","",
                lead.rating if lead.rating is not None else "",
                lead.reviews if lead.reviews is not None else "",
                lead.contact_person,score,pitch(lead),"New",fp.unique,
                f"{lead.notes}; Primary source: {lead.source}; Source ID: {lead.source_id}"
            ])

        registry_append = self.sheets.spreadsheets().values().append(
            spreadsheetId=registry_id,
            range=f"'{registry_tab}'!A:V",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values":registry_rows}
        ).execute()

        updated_range = registry_append.get("updates", {}).get("updatedRange", "")
        match = re.search(r"!A(\d+):V(\d+)$", updated_range)
        if not match:
            raise RuntimeError(f"Could not resolve appended registry rows from: {updated_range}")
        start_row, end_row = int(match.group(1)), int(match.group(2))

        self.sheets.spreadsheets().values().append(
            spreadsheetId=workbook["id"],
            range=f"'{category}'!A:AC",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values":daily_rows}
        ).execute()

        status_letter = self._column_letter(REGISTRY_COLUMNS.index("Status"))
        self.sheets.spreadsheets().values().update(
            spreadsheetId=registry_id,
            range=f"'{registry_tab}'!{status_letter}{start_row}:{status_letter}{end_row}",
            valueInputOption="RAW",
            body={"values":[["Active"] for _ in leads]}
        ).execute()

    def set_overview_metrics(self, workbook_id: str, values: dict[str, int | str]):
        rows = self.sheets.spreadsheets().values().get(
            spreadsheetId=workbook_id,
            range="'Overview'!A1:B100"
        ).execute().get("values", [])
        metric_rows = {
            str(row[0]).strip(): row_number
            for row_number, row in enumerate(rows, start=1)
            if row and str(row[0]).strip()
        }
        data = []
        for metric, value in values.items():
            row_number = metric_rows.get(metric)
            if row_number is None:
                continue
            data.append({
                "range":f"'Overview'!B{row_number}",
                "values":[[value]],
            })
        if data:
            self.sheets.spreadsheets().values().batchUpdate(
                spreadsheetId=workbook_id,
                body={"valueInputOption":"RAW","data":data},
            ).execute()

    def update_overview(self, workbook_id: str, counts: dict[str,int], increments: dict[str,int]):
        rows = self.sheets.spreadsheets().values().get(
            spreadsheetId=workbook_id,
            range="'Overview'!A1:B100"
        ).execute().get("values", [])
        metric_rows = {}
        current = {}
        for row_number,row in enumerate(rows,start=1):
            if not row:
                continue
            metric = str(row[0]).strip()
            if metric:
                metric_rows[metric] = row_number
                current[metric] = row[1] if len(row)>1 else 0

        data = []
        for metric,amount in increments.items():
            row_number = metric_rows.get(metric)
            if row_number is None:
                continue
            try:
                base = int(float(current.get(metric,0) or 0))
            except (TypeError,ValueError):
                base = 0
            data.append({
                "range":f"'Overview'!B{row_number}",
                "values":[[base + int(amount)]]
            })
        if data:
            self.sheets.spreadsheets().values().batchUpdate(
                spreadsheetId=workbook_id,
                body={"valueInputOption":"RAW","data":data}
            ).execute()
