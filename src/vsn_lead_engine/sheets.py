from __future__ import annotations

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build

from .dedupe import fingerprints
from .models import Lead
from .normalize import normalize_domain, normalize_name, normalize_phone
from .scoring import pitch, score_lead

DAILY_COLUMNS = [
    "Date Added","Country","Category","Business Name","Phone","Email","Website","Website Status",
    "Instagram","Facebook","LinkedIn","X/Twitter","TikTok","Google Maps URL","Street Address","City",
    "State/Province","ZIP/Postal Code","Latitude","Longitude","Nearby / Landmark / Neighborhood","Rating",
    "Reviews","Contact Person","Lead Score","Pitch","Outreach Status","Unique Key","Notes"
]

REGISTRY_COLUMNS = [
    "First Added","Field","Country","City","State/Province","ZIP/Postal Code","Business Name","Website",
    "Normalized Domain","Phone","Normalized Phone","Business+City+State/Province Key","Unique Key",
    "Daily Sheet","Daily Sheet URL","Status","Source ID","Primary Source"
]


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

    def _daily_title(self) -> str:
        today = datetime.now(ZoneInfo(self.config["runtime"]["timezone"])).date().isoformat()
        return f'{self.config["drive"]["daily_title_prefix"]} — {today}'

    def _find_daily(self):
        folder = self.config["drive"]["folder_id"]
        title = self._daily_title().replace("'", "\\'")
        query = (
            f"'{folder}' in parents and trashed=false and "
            "mimeType='application/vnd.google-apps.spreadsheet' and "
            f"name='{title}'"
        )
        files = self.drive.files().list(q=query, fields="files(id,name,webViewLink)", pageSize=10).execute().get("files", [])
        if len(files) > 1:
            raise RuntimeError(f"Duplicate dated spreadsheets found for {self._daily_title()}.")
        return files[0] if files else None

    def ensure_daily_sheet(self):
        existing = self._find_daily()
        if existing:
            self._ensure_tabs(existing["id"])
            return existing
        created = self.sheets.spreadsheets().create(
            body={"properties":{"title":self._daily_title()}},
            fields="spreadsheetId"
        ).execute()
        sid = created["spreadsheetId"]
        folder = self.config["drive"]["folder_id"]
        parents = self.drive.files().get(fileId=sid, fields="parents").execute().get("parents", [])
        self.drive.files().update(
            fileId=sid,
            addParents=folder,
            removeParents=",".join(parents) if parents else None,
            fields="id"
        ).execute()
        self._ensure_tabs(sid)
        return {"id":sid, "name":self._daily_title(), "webViewLink":f"https://docs.google.com/spreadsheets/d/{sid}/edit"}

    def _ensure_tabs(self, spreadsheet_id: str):
        metadata = self.sheets.spreadsheets().get(spreadsheetId=spreadsheet_id, fields="sheets.properties").execute()
        existing = {s["properties"]["title"] for s in metadata.get("sheets", [])}
        wanted = ["Overview", *self.config["categories"]]
        requests = [{"addSheet":{"properties":{"title":name}}} for name in wanted if name not in existing]
        if requests:
            self.sheets.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests":requests}).execute()
        for name in wanted:
            header = ["Metric","Value"] if name == "Overview" else DAILY_COLUMNS
            row = self.sheets.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id, range=f"'{name}'!1:1"
            ).execute().get("values", [])
            if not row:
                self.sheets.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=f"'{name}'!A1",
                    valueInputOption="RAW",
                    body={"values":[header]}
                ).execute()

    def category_counts(self, spreadsheet_id: str) -> dict[str,int]:
        counts = {}
        for category in self.config["categories"]:
            rows = self.sheets.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=f"'{category}'!A:A"
            ).execute().get("values", [])
            counts[category] = max(0, len(rows) - 1)
        return counts

    def _registry_rows(self):
        sid = self.config["drive"]["master_registry_spreadsheet_id"]
        tab = self.config["drive"]["master_registry_tab"]
        return self.sheets.spreadsheets().values().get(
            spreadsheetId=sid, range=f"'{tab}'!A:R"
        ).execute().get("values", [])

    def registry_fingerprints(self):
        rows = self._registry_rows()
        if not rows:
            sid = self.config["drive"]["master_registry_spreadsheet_id"]
            tab = self.config["drive"]["master_registry_tab"]
            self.sheets.spreadsheets().values().update(
                spreadsheetId=sid,
                range=f"'{tab}'!A1",
                valueInputOption="RAW",
                body={"values":[REGISTRY_COLUMNS]}
            ).execute()
            return {k:set() for k in ["source_id","domain","phone_name","business_location","unique"]}
        header = rows[0]
        index = {name:i for i,name in enumerate(header)}
        result = {k:set() for k in ["source_id","domain","phone_name","business_location","unique"]}
        def cell(row, name):
            i = index.get(name)
            return str(row[i]).strip() if i is not None and i < len(row) else ""
        for row in rows[1:]:
            source_id = cell(row, "Source ID").lower()
            domain = cell(row, "Normalized Domain").lower()
            phone = cell(row, "Normalized Phone")
            name = normalize_name(cell(row, "Business Name"))
            bizloc = cell(row, "Business+City+State/Province Key").lower()
            unique = cell(row, "Unique Key").lower()
            if source_id: result["source_id"].add(source_id)
            if domain: result["domain"].add(domain)
            if phone and name: result["phone_name"].add(f"{phone}|{name}")
            if bizloc: result["business_location"].add(bizloc)
            if unique: result["unique"].add(unique)
        return result

    def commit_lead(self, daily: dict, lead: Lead):
        fp = fingerprints(lead)
        registry_id = self.config["drive"]["master_registry_spreadsheet_id"]
        registry_tab = self.config["drive"]["master_registry_tab"]
        registry_row = [
            lead.date_added, lead.category, lead.country, lead.city, lead.region, lead.postal_code,
            lead.business_name, lead.website, normalize_domain(lead.website), lead.phone,
            normalize_phone(lead.phone, lead.country), fp.business_location, fp.unique,
            daily["name"], daily.get("webViewLink", f'https://docs.google.com/spreadsheets/d/{daily["id"]}/edit'),
            "PendingDaily", lead.source_id, lead.source
        ]
        self.sheets.spreadsheets().values().append(
            spreadsheetId=registry_id,
            range=f"'{registry_tab}'!A:R",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values":[registry_row]}
        ).execute()

        score = score_lead(lead)
        daily_row = [
            lead.date_added, lead.country, lead.category, lead.business_name, lead.phone, lead.email,
            lead.website, lead.website_status, "", "", "", "", "", "", lead.street_address, lead.city,
            lead.region, lead.postal_code, lead.latitude if lead.latitude is not None else "",
            lead.longitude if lead.longitude is not None else "", "", lead.rating if lead.rating is not None else "",
            lead.reviews if lead.reviews is not None else "", lead.contact_person, score, pitch(lead), "New",
            fp.unique, f"{lead.notes}; Primary source: {lead.source}; Source ID: {lead.source_id}"
        ]
        self.sheets.spreadsheets().values().append(
            spreadsheetId=daily["id"],
            range=f"'{lead.category}'!A:AC",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values":[daily_row]}
        ).execute()

        rows = self._registry_rows()
        if not rows:
            return
        header = rows[0]
        key_col = header.index("Unique Key")
        status_col = header.index("Status")
        def column_letter(index_zero_based: int) -> str:
            n = index_zero_based + 1
            out = ""
            while n:
                n, rem = divmod(n - 1, 26)
                out = chr(65 + rem) + out
            return out
        status_letter = column_letter(status_col)
        for row_number, row in enumerate(rows[1:], start=2):
            if key_col < len(row) and str(row[key_col]).strip().lower() == fp.unique.lower():
                self.sheets.spreadsheets().values().update(
                    spreadsheetId=registry_id,
                    range=f"'{registry_tab}'!{status_letter}{row_number}",
                    valueInputOption="RAW",
                    body={"values":[["Active"]]}
                ).execute()
                break
