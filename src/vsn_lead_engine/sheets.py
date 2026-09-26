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
        files = self.drive.files().list(
            q=query, fields="files(id,name,webViewLink)", pageSize=10
        ).execute().get("files", [])
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
        return {
            "id":sid,
            "name":self._daily_title(),
            "webViewLink":f"https://docs.google.com/spreadsheets/d/{sid}/edit"
        }

    def _overview_seed(self):
        categories = self.config["categories"]
        target = int(self.config["runtime"]["daily_target_per_category"])
        rows = [
            ["Metric","Value"],
            ["Countries","United States + Canada"],
            ["Daily Target per Category",target],
            ["Total Daily Target",target * len(categories)],
        ]
        actual_start = len(rows) + 1
        for category in categories:
            rows.append([
                f"Actual Leads — {category}",
                f"=MAX(COUNTA('{category}'!A:A)-1,0)"
            ])
        shortfall_start = len(rows) + 1
        for category in categories:
            rows.append([
                f"Shortfall — {category}",
                f"=MAX({target}-(COUNTA('{category}'!A:A)-1),0)"
            ])
        actual_end = actual_start + len(categories) - 1
        rows.extend([
            ["Total Actual Leads",f"=SUM(B{actual_start}:B{actual_end})"],
            ["Total Shortfall",f"=MAX({target * len(categories)}-B{len(rows)+1},0)"],
        ])
        score_ranges = [f"'{c}'!Y2:Y" for c in categories]
        sum_expr = "+".join(f"SUM({r})" for r in score_ranges)
        count_expr = "+".join(f"COUNT({r})" for r in score_ranges)
        high_expr = "+".join(f'COUNTIF({r},">=75")' for r in score_ranges)
        medium_expr = "+".join(f'COUNTIFS({r},">=50",{r},"<75")' for r in score_ranges)
        low_expr = "+".join(f'COUNTIFS({r},">0",{r},"<50")' for r in score_ranges)
        rows.extend([
            ["Avg Score",f"=IFERROR(({sum_expr})/({count_expr}),0)"],
            ["High",f"={high_expr}"],
            ["Medium",f"={medium_expr}"],
            ["Low",f"={low_expr}"],
            ["Duplicate Rejections",0],
            ["Missing-Phone Rejections",0],
            ["Google Maps/Places Candidates",0],
            ["Directory Candidates",0],
            ["Cross-Source Matches",0],
            ["Free-Source Candidates",0],
            ["Source / Tool Limitation Notes","FREE mode: no paid Google Places calls; throughput depends on compliant public-source coverage and rate limits."],
        ])
        return rows

    def _ensure_tabs(self, spreadsheet_id: str):
        metadata = self.sheets.spreadsheets().get(
            spreadsheetId=spreadsheet_id, fields="sheets.properties"
        ).execute()
        props = [s["properties"] for s in metadata.get("sheets", [])]
        existing = {p["title"] for p in props}
        wanted = ["Overview", *self.config["categories"]]
        requests = [{"addSheet":{"properties":{"title":name}}} for name in wanted if name not in existing]
        if requests:
            self.sheets.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id, body={"requests":requests}
            ).execute()

        metadata = self.sheets.spreadsheets().get(
            spreadsheetId=spreadsheet_id, fields="sheets.properties"
        ).execute()
        props = [s["properties"] for s in metadata.get("sheets", [])]
        if len(props) > 1:
            for p in props:
                if p["title"] == "Sheet1" and p["title"] not in wanted:
                    self.sheets.spreadsheets().batchUpdate(
                        spreadsheetId=spreadsheet_id,
                        body={"requests":[{"deleteSheet":{"sheetId":p["sheetId"]}}]}
                    ).execute()
                    break

        for name in wanted:
            row = self.sheets.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id, range=f"'{name}'!1:1"
            ).execute().get("values", [])
            if row:
                continue
            if name == "Overview":
                values = self._overview_seed()
            else:
                values = [DAILY_COLUMNS]
            self.sheets.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"'{name}'!A1",
                valueInputOption="USER_ENTERED",
                body={"values":values}
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

    def commit_lead(self, daily: dict, lead: Lead):
        fp = fingerprints(lead)
        registry_id = self.config["drive"]["master_registry_spreadsheet_id"]
        registry_tab = self.config["drive"]["master_registry_tab"]
        normalized_phone = normalize_phone(lead.phone, lead.country)
        registry_row = [
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
            daily["name"],
            daily.get("webViewLink",f'https://docs.google.com/spreadsheets/d/{daily["id"]}/edit'),
            "PendingDaily",
            lead.region,
            lead.postal_code,
            lead.google_place_id,
            lead.source,
            f"{lead.source}; Source ID: {lead.source_id}",
            fp.business_location,
        ]
        self.sheets.spreadsheets().values().append(
            spreadsheetId=registry_id,
            range=f"'{registry_tab}'!A:V",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values":[registry_row]}
        ).execute()

        score = score_lead(lead)
        daily_row = [
            lead.date_added,lead.country,lead.category,lead.business_name,lead.phone,lead.email,
            lead.website,lead.website_status,"","","","","","",lead.street_address,lead.city,
            lead.region,lead.postal_code,lead.latitude if lead.latitude is not None else "",
            lead.longitude if lead.longitude is not None else "","",
            lead.rating if lead.rating is not None else "",
            lead.reviews if lead.reviews is not None else "",
            lead.contact_person,score,pitch(lead),"New",fp.unique,
            f"{lead.notes}; Primary source: {lead.source}; Source ID: {lead.source_id}"
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
                n, rem = divmod(n - 1,26)
                out = chr(65 + rem) + out
            return out

        status_letter = column_letter(status_col)
        for row_number,row in enumerate(rows[1:],start=2):
            if key_col < len(row) and str(row[key_col]).strip().lower() == fp.unique.lower():
                self.sheets.spreadsheets().values().update(
                    spreadsheetId=registry_id,
                    range=f"'{registry_tab}'!{status_letter}{row_number}",
                    valueInputOption="RAW",
                    body={"values":[["Active"]]}
                ).execute()
                break

    def update_overview(self, daily_id: str, counts: dict[str,int], increments: dict[str,int]):
        rows = self.sheets.spreadsheets().values().get(
            spreadsheetId=daily_id,
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
                spreadsheetId=daily_id,
                body={"valueInputOption":"RAW","data":data}
            ).execute()
