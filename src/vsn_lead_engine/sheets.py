from __future__ import annotations

import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build

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


class GoogleSheetsStore:
    def __init__(self, config: dict):
        raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        if not raw:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is required for real writes.")
        creds = service_account.Credentials.from_service_account_info(
            json.loads(raw),
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        self.sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
        self.config = config

    def _today(self) -> str:
        return datetime.now(ZoneInfo(self.config["runtime"]["timezone"])).date().isoformat()

    def ensure_lead_workbook(self):
        sid = self.config["drive"]["lead_workbook_spreadsheet_id"]
        metadata = self.sheets.spreadsheets().get(
            spreadsheetId=sid,
            fields="properties(title,timeZone),sheets.properties"
        ).execute()
        self._ensure_tabs(sid, metadata)
        self._ensure_overview_metrics(sid)
        self._refresh_overview_formulas(sid)
        return {
            "id": sid,
            "name": metadata.get("properties", {}).get(
                "title", self.config["drive"].get("lead_workbook_name", "US + Canada Business Leads — Master")
            ),
            "webViewLink": f"https://docs.google.com/spreadsheets/d/{sid}/edit",
        }

    def _overview_seed(self):
        categories = self.config["categories"]
        target = int(self.config["runtime"]["daily_target_per_category"])
        rows = [
            ["VSN Lead Engine — Permanent US + Canada Workbook",""],
            ["Metric","Value"],
            ["Tracking Date",'=TEXT(TODAY(),"yyyy-mm-dd")'],
            ["Countries","United States + Canada"],
            ["Daily Target / Category",target],
            ["Total Daily Target",target * len(categories)],
        ]
        for category in categories:
            rows.append([
                f"Actual — {category}",
                f'=COUNTIFS(\'{category}\'!A:A,TEXT(TODAY(),"yyyy-mm-dd"),\'{category}\'!AA:AA,"<>Needs Review")'
            ])
        for category in categories:
            rows.append([
                f"Shortfall — {category}",
                f'=MAX($B$5-COUNTIFS(\'{category}\'!A:A,TEXT(TODAY(),"yyyy-mm-dd"),\'{category}\'!AA:AA,"<>Needs Review"),0)'
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
            ["Primary Free Source","Overture Maps Places"],
            ["Notes","Permanent workbook mode. Daily counts use Date Added, so targets reset automatically each day."],
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
        if "Primary Free Source" not in existing:
            missing.append(["Primary Free Source","Overture Maps Places"])
        if missing:
            self.sheets.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range="'Overview'!A:B",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values":missing},
            ).execute()

    def _refresh_overview_formulas(self, spreadsheet_id: str):
        categories = self.config["categories"]
        target = int(self.config["runtime"]["daily_target_per_category"])
        data = []
        actual_start = 7
        shortfall_start = actual_start + len(categories)

        for offset, category in enumerate(categories):
            escaped = category.replace("'", "''")
            actual_row = actual_start + offset
            shortfall_row = shortfall_start + offset
            formula = (
                f'=COUNTIFS(\'{escaped}\'!A:A,TEXT(TODAY(),"yyyy-mm-dd"),'
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
