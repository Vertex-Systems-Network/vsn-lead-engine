from __future__ import annotations

import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from google.oauth2.credentials import Credentials as UserCredentials
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
DAILY_FINGERPRINT_INDEX = DAILY_COLUMNS.index("Unique Key")

REGISTRY_COLUMNS = [
    "First Added","Field","Region","Country","City","Category","Business Name","Website",
    "Normalized Domain","Phone","Normalized Phone","Business+City Key","Unique Key","Daily Sheet",
    "Daily Sheet URL","Status","State/Province","ZIP/Postal Code","Google Place ID","Primary Source",
    "Verification Sources","Business+City+State Key"
]

OVERVIEW_INCREMENT_METRICS = [
    "Accepted Leads",
    "Duplicate Rejections",
    "Source-Batch Duplicates",
    "Remote Prefilter Duplicates",
    "Missing-Phone Rejections",
    "Free-Source Candidates",
    "Source Phone Candidates",
    "Website-Only Candidates",
    "Shard Attempts",
    "Zero-Result Shards",
    "Source Errors",
    "Enrichment Candidates",
    "Phones Recovered",
    "Official-Site Phone Recoveries",
    "Common-Crawl Phone Recoveries",
    "Common Crawl Attempts",
    "Enrichment Budget Skips",
    "Enrichment Errors",
    "Zero-Progress Cycles",
]

OVERVIEW_LATEST_METRICS = [
    "Last Acceptance Rate %",
    "Last Phone Recovery Rate %",
    "Last Partitions Visited",
]

OVERVIEW_SENTINEL = "VSN Lead Engine — Daily US + Canada Workbook"

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


class PermanentWorkbookReadinessError(RuntimeError):
    """Non-transient workbook readiness blocker; retries cannot repair it."""


class DuplicateDailyWorkbookError(PermanentWorkbookReadinessError):
    """More than one active workbook exists for the same configured date/title."""


def google_auth_mode_from_env() -> str:
    if os.getenv("GOOGLE_OAUTH_USER_JSON","").strip():
        return "user-oauth"
    if os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON","").strip():
        return "service-account"
    return "missing"


def google_credentials_from_env():
    """Return Google credentials and auth mode, preferring user OAuth for My Drive."""
    user_raw=os.getenv("GOOGLE_OAUTH_USER_JSON","").strip()
    if user_raw:
        try:
            info=json.loads(user_raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("GOOGLE_OAUTH_USER_JSON must contain valid JSON.") from exc
        if not isinstance(info,dict):
            raise RuntimeError("GOOGLE_OAUTH_USER_JSON must contain a JSON object.")
        if str(info.get("type","authorized_user")).strip()!="authorized_user":
            raise RuntimeError(
                "GOOGLE_OAUTH_USER_JSON must be Google authorized-user credentials."
            )
        try:
            credentials=UserCredentials.from_authorized_user_info(
                info,
                scopes=GOOGLE_SCOPES,
            )
        except (TypeError,ValueError) as exc:
            raise RuntimeError(
                "GOOGLE_OAUTH_USER_JSON is not valid authorized-user credential data."
            ) from exc
        return credentials,"user-oauth"

    raw=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON","").strip()
    if not raw:
        raise RuntimeError(
            "Google credentials are required. Configure GOOGLE_OAUTH_USER_JSON "
            "for My Drive ownership-safe writes or GOOGLE_SERVICE_ACCOUNT_JSON "
            "for existing-file access."
        )
    try:
        info=json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON must contain valid JSON.") from exc
    try:
        credentials=service_account.Credentials.from_service_account_info(
            info,
            scopes=GOOGLE_SCOPES,
        )
    except (TypeError,ValueError) as exc:
        raise RuntimeError(
            "GOOGLE_SERVICE_ACCOUNT_JSON is not valid service-account credential data."
        ) from exc
    return credentials,"service-account"


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
    if normalized in {"needsreview", "rejected", "invalid", "quarantined", "retryable", "writefailed"}:
        return False
    return True


def daily_workbook_title(prefix: str, date_value: str) -> str:
    return f"{prefix}{date_value}"


def escape_drive_query_value(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def extract_spreadsheet_id(value: str) -> str:
    match = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", str(value or ""))
    return match.group(1) if match else ""


def overview_schema_is_current(rows: list[list], run_date: str) -> bool:
    """Return whether a dated workbook already uses the current Overview schema."""
    if not rows:
        return False
    first = str(rows[0][0]).strip() if rows[0] else ""
    if first != OVERVIEW_SENTINEL:
        return False
    tracking = ""
    for row in rows[:10]:
        if row and str(row[0]).strip() == "Tracking Date":
            tracking = str(row[1]).strip() if len(row) > 1 else ""
            break
    return tracking == str(run_date).strip()


def category_tabs_are_blank(value_ranges: list[dict]) -> bool:
    """Treat a precreated template as blank only when every category has no data rows."""
    for item in value_ranges or []:
        values = item.get("values", []) or []
        if any(any(str(cell).strip() for cell in row) for row in values):
            return False
    return True


def pending_recovery_status(unique_key: str, present_keys: set[str]) -> str:
    key = str(unique_key or "").strip().lower()
    return "Active" if key and key in present_keys else "Retryable"


class GoogleSheetsStore:
    def __init__(self, config: dict, run_date: str | None = None):
        creds,auth_mode=google_credentials_from_env()
        self.google_auth_mode=auth_mode
        self.sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
        self.drive = build("drive", "v3", credentials=creds, cache_discovery=False)
        self.config = config
        self.run_date = run_date or datetime.now(
            ZoneInfo(self.config["runtime"]["timezone"])
        ).date().isoformat()
        self.api_retries = int(self.config["runtime"].get("google_api_retries", 5))

    def _today(self) -> str:
        return self.run_date

    def _daily_title(self, date_value: str | None = None) -> str:
        prefix = self.config["drive"].get(
            "daily_title_prefix", "US + Canada Business Leads — "
        )
        return daily_workbook_title(prefix, date_value or self._today())

    def drive_creation_capability(self, *, probe_create: bool = False) -> dict:
        """Return whether current credentials can autonomously create in target folder."""
        folder_id=self.config["drive"]["folder_id"]
        folder=self.drive.files().get(
            fileId=folder_id,
            fields="id,name,driveId,capabilities(canAddChildren)",
            supportsAllDrives=True,
        ).execute(num_retries=self.api_retries)
        drive_id=str(folder.get("driveId") or "").strip()
        storage="shared-drive" if drive_id else "my-drive"
        can_add=(folder.get("capabilities") or {}).get("canAddChildren")
        result={
            "status":"capable",
            "auth_mode":self.google_auth_mode,
            "storage":storage,
            "folder_id":folder_id,
            "can_add_children":can_add,
            "probe_performed":False,
            "probe_cleaned":False,
        }

        if can_add is False:
            return {
                **result,
                "status":"blocked",
                "permanent":True,
                "reason":"Authenticated principal cannot add children to the target folder.",
            }

        if self.google_auth_mode=="service-account" and storage=="my-drive":
            return {
                **result,
                "status":"blocked",
                "permanent":True,
                "reason":(
                    "Service-account credentials cannot autonomously own a new "
                    "file in this user-owned My Drive folder. Configure "
                    "GOOGLE_OAUTH_USER_JSON or precreate the dated workbook."
                ),
            }

        if not probe_create:
            return result

        probe_name=(
            "VSN Lead Engine — Google Drive Creation Probe — "
            + datetime.now(ZoneInfo(self.config["runtime"]["timezone"])).strftime(
                "%Y%m%dT%H%M%S"
            )
        )
        created=None
        try:
            created=self.drive.files().create(
                body={
                    "name":probe_name,
                    "mimeType":"application/vnd.google-apps.spreadsheet",
                    "parents":[folder_id],
                },
                fields="id,name,driveId,parents",
                supportsAllDrives=True,
            ).execute(num_retries=self.api_retries)
            result["probe_performed"]=True
            result["probe_file_id"]=created.get("id","")
            result["probe_file_name"]=created.get("name",probe_name)
        except HttpError as exc:
            return {
                **result,
                "status":"blocked",
                "probe_performed":True,
                "permanent":getattr(exc.resp,"status",None)==403,
                "error_type":type(exc).__name__,
                "reason":f"Drive creation probe failed with HTTP {getattr(exc.resp,'status',None)}.",
            }

        try:
            self.drive.files().update(
                fileId=created["id"],
                body={"trashed":True},
                fields="id,trashed",
                supportsAllDrives=True,
            ).execute(num_retries=self.api_retries)
            result["probe_cleaned"]=True
        except HttpError as exc:
            raise RuntimeError(
                "Drive creation probe succeeded but cleanup failed; remove the "
                f"probe file manually: {created.get('id','unknown')}."
            ) from exc

        return result

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
        ).execute(num_retries=self.api_retries)
        files = response.get("files", [])
        if not files:
            return None
        if len(files) > 1:
            raise DuplicateDailyWorkbookError(
                "Found "
                f"{len(files)} active daily workbooks named {title!r} in the "
                "configured lead folder. Refusing to choose one silently; "
                "archive/trash duplicates before production continues."
            )
        return files[0]

    def _create_daily_workbook(self, title: str) -> dict:
        template_id = self.config["drive"]["daily_template_spreadsheet_id"]
        folder_id = self.config["drive"]["folder_id"]
        try:
            created = self.drive.files().copy(
                fileId=template_id,
                body={"name": title, "parents": [folder_id]},
                fields="id,name,webViewLink,createdTime",
            ).execute(num_retries=self.api_retries)
        except HttpError as exc:
            status = getattr(exc.resp, "status", None)
            if status in {403, 429}:
                auth_mode=getattr(self,"google_auth_mode","unknown")
                if status==403 and auth_mode=="service-account":
                    raise RuntimeError(
                        "Target dated lead workbook is missing and service-account auth "
                        "cannot create the user-owned My Drive copy. Configure "
                        "GOOGLE_OAUTH_USER_JSON or precreate the user-owned dated "
                        "workbook."
                    ) from exc
                raise RuntimeError(
                    "Target dated lead workbook is missing and Google "
                    f"{auth_mode} credentials could not create it in the target "
                    "folder. Check OAuth scopes/ownership or Drive quota/rate limits."
                ) from exc
            raise

        self._initialize_new_daily_workbook(created["id"])
        return created

    def _ensure_spreadsheet_timezone(
        self,
        spreadsheet_id: str,
        metadata: dict | None = None,
    ):
        metadata = metadata or self.sheets.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            fields="properties(timeZone)",
        ).execute(num_retries=self.api_retries)
        desired_timezone=str(
            self.config["runtime"].get("timezone","Asia/Karachi")
        ).strip()
        current_timezone=str(
            metadata.get("properties",{}).get("timeZone","")
        ).strip()
        if desired_timezone and current_timezone != desired_timezone:
            self.sheets.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={
                    "requests":[
                        {
                            "updateSpreadsheetProperties":{
                                "properties":{"timeZone":desired_timezone},
                                "fields":"timeZone",
                            }
                        }
                    ]
                },
            ).execute(num_retries=self.api_retries)

    def _initialize_new_daily_workbook(self, spreadsheet_id: str):
        date_value = self._today()
        metadata = self.sheets.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            fields="properties(title,timeZone),sheets.properties",
        ).execute(num_retries=self.api_retries)
        self._ensure_tabs(spreadsheet_id, metadata)
        self._ensure_spreadsheet_timezone(spreadsheet_id, metadata)

        # A copied template must start clean. Preserve header rows and tab
        # formatting while removing any old lead rows.
        for category in self.config["categories"]:
            self.sheets.spreadsheets().values().clear(
                spreadsheetId=spreadsheet_id,
                range=f"'{category}'!A2:AC",
                body={},
            ).execute(num_retries=self.api_retries)
            self.sheets.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"'{category}'!A1:AC1",
                valueInputOption="RAW",
                body={"values": [DAILY_COLUMNS]},
            ).execute(num_retries=self.api_retries)

        self.sheets.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range="'Overview'!A:B",
            body={},
        ).execute(num_retries=self.api_retries)
        self.sheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range="'Overview'!A1",
            valueInputOption="USER_ENTERED",
            body={"values": self._overview_seed(date_value)},
        ).execute(num_retries=self.api_retries)

    def _precreated_workbook_state(self, spreadsheet_id: str) -> str:
        overview = self.sheets.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range="'Overview'!A1:B10",
        ).execute(num_retries=self.api_retries).get("values",[])
        if overview_schema_is_current(overview,self._today()):
            return "current"

        response=self.sheets.spreadsheets().values().batchGet(
            spreadsheetId=spreadsheet_id,
            ranges=[
                f"'{category}'!A2:AC"
                for category in self.config["categories"]
            ],
            valueRenderOption="UNFORMATTED_VALUE",
        ).execute(num_retries=self.api_retries)
        return (
            "blank-stale"
            if category_tabs_are_blank(response.get("valueRanges",[]))
            else "populated-stale"
        )

    def _upgrade_overview_only(self, spreadsheet_id: str):
        """Upgrade stale Overview without touching populated category rows."""
        existing=self.sheets.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range="'Overview'!A1:B100",
        ).execute(num_retries=self.api_retries).get("values",[])
        preserve_names=set(OVERVIEW_INCREMENT_METRICS) | set(
            OVERVIEW_LATEST_METRICS
        ) | {
            "United States Leads Today",
            "Canada Leads Today",
        }
        preserved={
            str(row[0]).strip():row[1]
            for row in existing
            if (
                row
                and len(row)>1
                and str(row[0]).strip() in preserve_names
            )
        }

        self.sheets.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range="'Overview'!A:B",
            body={},
        ).execute(num_retries=self.api_retries)
        self.sheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range="'Overview'!A1",
            valueInputOption="USER_ENTERED",
            body={"values":self._overview_seed(self._today())},
        ).execute(num_retries=self.api_retries)
        if preserved:
            self.set_overview_metrics(spreadsheet_id,preserved)

    def ensure_lead_workbook(self):
        date_value = self._today()
        title = self._daily_title(date_value)
        file = self._find_daily_workbook(title)
        created = False
        initialized = False
        if file is None:
            capability=self.drive_creation_capability()
            if capability.get("status")!="capable":
                raise PermanentWorkbookReadinessError(
                    str(capability.get("reason") or "Google Drive creation is blocked.")
                )
            file = self._create_daily_workbook(title)
            created = True
            initialized = True
            verified=self._find_daily_workbook(title)
            if verified is None or verified.get("id") != file.get("id"):
                raise PermanentWorkbookReadinessError(
                    "Daily workbook creation could not be verified as the sole "
                    "active canonical file."
                )
            file=verified

        sid = file["id"]
        metadata = self.sheets.spreadsheets().get(
            spreadsheetId=sid,
            fields="properties(title,timeZone),sheets.properties",
        ).execute(num_retries=self.api_retries)
        self._ensure_tabs(sid, metadata)

        bootstrap_precreated=bool(
            self.config["runtime"].get(
                "precreated_workbook_bootstrap_enabled",
                True,
            )
        )
        if not created and bootstrap_precreated:
            precreated_state=self._precreated_workbook_state(sid)
            if precreated_state=="blank-stale":
                self._initialize_new_daily_workbook(sid)
                initialized = True
            elif precreated_state=="populated-stale":
                self._upgrade_overview_only(sid)
                self._ensure_spreadsheet_timezone(sid,metadata)
                initialized = True

            if initialized:
                metadata = self.sheets.spreadsheets().get(
                    spreadsheetId=sid,
                    fields="properties(title,timeZone),sheets.properties",
                ).execute(num_retries=self.api_retries)

        self._ensure_spreadsheet_timezone(sid,metadata)
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
            "initialized": initialized,
        }

    def _overview_seed(self, date_value: str | None = None):
        date_value = date_value or self._today()
        categories = self.config["categories"]
        target = int(self.config["runtime"]["daily_target_per_category"])
        rows = [
            [OVERVIEW_SENTINEL,""],
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
            ["Accepted Leads",0],
            ["Duplicate Rejections",0],
            ["Source-Batch Duplicates",0],
            ["Remote Prefilter Duplicates",0],
            ["Missing-Phone Rejections",0],
            ["Free-Source Candidates",0],
            ["Source Phone Candidates",0],
            ["Website-Only Candidates",0],
            ["Shard Attempts",0],
            ["Zero-Result Shards",0],
            ["Source Errors",0],
            ["Enrichment Candidates",0],
            ["Phones Recovered",0],
            ["Official-Site Phone Recoveries",0],
            ["Common-Crawl Phone Recoveries",0],
            ["Common Crawl Attempts",0],
            ["Enrichment Budget Skips",0],
            ["Enrichment Errors",0],
            ["Zero-Progress Cycles",0],
            ["Last Acceptance Rate %",0],
            ["Last Phone Recovery Rate %",0],
            ["Last Partitions Visited",0],
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
            ).execute(num_retries=self.api_retries)
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
            ).execute(num_retries=self.api_retries)

        for name in wanted:
            row = self.sheets.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id, range=f"'{name}'!1:1"
            ).execute(num_retries=self.api_retries).get("values", [])
            if row:
                continue
            values = self._overview_seed() if name == "Overview" else [DAILY_COLUMNS]
            self.sheets.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"'{name}'!A1",
                valueInputOption="USER_ENTERED",
                body={"values":values}
            ).execute(num_retries=self.api_retries)

    def _ensure_overview_metrics(self, spreadsheet_id: str):
        rows=self.sheets.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range="'Overview'!A1:B100",
        ).execute(num_retries=self.api_retries).get("values",[])
        existing={str(row[0]).strip() for row in rows if row}
        missing=[[metric,0] for metric in OVERVIEW_INCREMENT_METRICS if metric not in existing]
        missing.extend(
            [metric,0]
            for metric in OVERVIEW_LATEST_METRICS
            if metric not in existing
        )
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
            ).execute(num_retries=self.api_retries)

    def _refresh_overview_formulas(self, spreadsheet_id: str, date_value: str | None = None):
        date_value = date_value or self._today()
        categories = self.config["categories"]
        target = int(self.config["runtime"]["daily_target_per_category"])
        data = [
            {"range":"'Overview'!A1","values":[[OVERVIEW_SENTINEL]]},
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
        ).execute(num_retries=self.api_retries)

    def daily_state_snapshot(self, spreadsheet_id: str) -> dict:
        """Read category and country totals in one Sheets batch request."""
        today=self._today()
        ranges=[]
        for category in self.config["categories"]:
            ranges.extend([f"'{category}'!A2:B",f"'{category}'!AA2:AA"])

        response=self.sheets.spreadsheets().values().batchGet(
            spreadsheetId=spreadsheet_id,
            ranges=ranges,
            valueRenderOption="UNFORMATTED_VALUE",
        ).execute(num_retries=self.api_retries)
        value_ranges=response.get("valueRanges",[])
        category_counts={}
        country_counts: dict[str,int] = {}

        for index,category in enumerate(self.config["categories"]):
            date_country_index=index*2
            status_index=date_country_index+1
            date_country_rows=(
                value_ranges[date_country_index].get("values",[])
                if date_country_index < len(value_ranges)
                else []
            )
            status_rows=(
                value_ranges[status_index].get("values",[])
                if status_index < len(value_ranges)
                else []
            )
            date_rows=[
                [row[0] if row else ""]
                for row in date_country_rows
            ]
            category_counts[category]=count_current_rows(
                date_rows,
                status_rows,
                today,
            )
            per_country=count_current_countries(
                date_country_rows,
                status_rows,
                today,
            )
            for country,count in per_country.items():
                country_counts[country]=country_counts.get(country,0)+count

        for country in ["United States","Canada"]:
            country_counts.setdefault(country,0)

        return {
            "category_counts":category_counts,
            "country_counts":country_counts,
        }

    def category_counts(self, spreadsheet_id: str) -> dict[str,int]:
        today = self._today()
        ranges = []
        for category in self.config["categories"]:
            ranges.extend([f"'{category}'!A2:A", f"'{category}'!AA2:AA"])

        response = self.sheets.spreadsheets().values().batchGet(
            spreadsheetId=spreadsheet_id,
            ranges=ranges,
            valueRenderOption="UNFORMATTED_VALUE",
        ).execute(num_retries=self.api_retries)
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
        ).execute(num_retries=self.api_retries)
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
        ).execute(num_retries=self.api_retries).get("values", [])

    def reconcile_pending_registry(self) -> dict[str, int]:
        """Repair stale Registry PendingDaily rows before dedupe is built.

        If the referenced daily workbook contains the Unique Key, promote the
        row to Active. If the daily write never landed (or the referenced file
        is permanently unavailable), mark it Retryable so it cannot poison
        cross-day dedupe forever.
        """
        rows = self._registry_rows()
        if not rows:
            return {"checked": 0, "activated": 0, "retryable": 0, "unresolved": 0}

        header = rows[0]
        required = {"Status", "Unique Key", "Category", "Daily Sheet URL"}
        missing = required.difference(header)
        if missing:
            raise RuntimeError(
                f"Master Registry schema missing recovery columns: {sorted(missing)}"
            )

        index = {name: i for i, name in enumerate(header)}
        status_col = self._column_letter(index["Status"])
        pending = []

        def cell(row, name):
            i = index[name]
            return str(row[i]).strip() if i < len(row) else ""

        for row_number, row in enumerate(rows[1:], start=2):
            normalized = re.sub(r"[^a-z0-9]+", "", cell(row, "Status").lower())
            if normalized != "pendingdaily":
                continue
            pending.append({
                "row": row_number,
                "unique": cell(row, "Unique Key"),
                "category": cell(row, "Category"),
                "sheet_id": extract_spreadsheet_id(cell(row, "Daily Sheet URL")),
            })

        if not pending:
            return {"checked": 0, "activated": 0, "retryable": 0, "unresolved": 0}

        grouped: dict[tuple[str, str], list[dict]] = {}
        direct_retry = []
        for item in pending:
            if not item["sheet_id"] or not item["category"] or not item["unique"]:
                direct_retry.append(item)
                continue
            grouped.setdefault((item["sheet_id"], item["category"]), []).append(item)

        updates = []
        activated = 0
        retryable = 0
        unresolved = 0

        for item in direct_retry:
            updates.append({
                "range": f"'{self.config['drive']['master_registry_tab']}'!{status_col}{item['row']}",
                "values": [["Retryable"]],
            })
            retryable += 1

        for (spreadsheet_id, category), items in grouped.items():
            escaped_category = category.replace("'", "''")
            try:
                values = self.sheets.spreadsheets().values().get(
                    spreadsheetId=spreadsheet_id,
                    range=f"'{escaped_category}'!AB2:AB",
                ).execute(num_retries=self.api_retries).get("values", [])
            except HttpError as exc:
                status = getattr(exc.resp, "status", None)
                if status not in {403, 404}:
                    unresolved += len(items)
                    continue
                values = []

            present = {
                str(row[0]).strip().lower()
                for row in values
                if row and str(row[0]).strip()
            }
            for item in items:
                new_status = pending_recovery_status(item["unique"], present)
                updates.append({
                    "range": f"'{self.config['drive']['master_registry_tab']}'!{status_col}{item['row']}",
                    "values": [[new_status]],
                })
                if new_status == "Active":
                    activated += 1
                else:
                    retryable += 1

        if updates:
            self.sheets.spreadsheets().values().batchUpdate(
                spreadsheetId=self.config["drive"]["master_registry_spreadsheet_id"],
                body={"valueInputOption": "RAW", "data": updates},
            ).execute(num_retries=self.api_retries)

        return {
            "checked": len(pending),
            "activated": activated,
            "retryable": retryable,
            "unresolved": unresolved,
        }

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
            ).execute(num_retries=self.api_retries)
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

    def _daily_rows(self, leads: list[Lead]) -> list[list]:
        rows = []
        for lead in leads:
            fp = fingerprints(lead)
            score = score_lead(lead)
            rows.append([
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
        return rows

    def append_daily_leads(self, workbook: dict, leads: list[Lead]):
        if not leads:
            return
        category = leads[0].category
        if any(lead.category != category for lead in leads):
            raise ValueError("A daily append batch must contain a single category.")
        # Appends are not idempotent: a retry after a timed-out but applied
        # append would duplicate rows, so skip fingerprints already on the tab.
        key_letter = self._column_letter(DAILY_FINGERPRINT_INDEX)
        existing = self.sheets.spreadsheets().values().get(
            spreadsheetId=workbook["id"],
            range=f"'{category}'!{key_letter}:{key_letter}"
        ).execute(num_retries=self.api_retries).get("values", [])
        written = {str(row[0]).strip() for row in existing if row and str(row[0]).strip()}
        rows = [row for row in self._daily_rows(leads) if row[DAILY_FINGERPRINT_INDEX] not in written]
        if not rows:
            return
        self.sheets.spreadsheets().values().append(
            spreadsheetId=workbook["id"],
            range=f"'{category}'!A:AC",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values":rows}
        ).execute(num_retries=self.api_retries)

    def commit_leads(self, workbook: dict, leads: list[Lead]):
        """Commit using the legacy Google Sheet Registry authority."""
        if not leads:
            return
        category = leads[0].category
        if any(lead.category != category for lead in leads):
            raise ValueError("A commit batch must contain a single category.")

        registry_id = self.config["drive"]["master_registry_spreadsheet_id"]
        registry_tab = self.config["drive"]["master_registry_tab"]
        registry_rows = []

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

        registry_append = self.sheets.spreadsheets().values().append(
            spreadsheetId=registry_id,
            range=f"'{registry_tab}'!A:V",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values":registry_rows}
        ).execute(num_retries=self.api_retries)

        updated_range = registry_append.get("updates", {}).get("updatedRange", "")
        match = re.search(r"!A(\d+):V(\d+)$", updated_range)
        if not match:
            raise RuntimeError(f"Could not resolve appended registry rows from: {updated_range}")
        start_row, end_row = int(match.group(1)), int(match.group(2))

        self.append_daily_leads(workbook, leads)

        status_letter = self._column_letter(REGISTRY_COLUMNS.index("Status"))
        self.sheets.spreadsheets().values().update(
            spreadsheetId=registry_id,
            range=f"'{registry_tab}'!{status_letter}{start_row}:{status_letter}{end_row}",
            valueInputOption="RAW",
            body={"values":[["Active"] for _ in leads]}
        ).execute(num_retries=self.api_retries)

    def set_overview_metrics(self, workbook_id: str, values: dict[str, int | str]):
        rows = self.sheets.spreadsheets().values().get(
            spreadsheetId=workbook_id,
            range="'Overview'!A1:B100"
        ).execute(num_retries=self.api_retries).get("values", [])
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
            ).execute(num_retries=self.api_retries)

    def update_overview(self, workbook_id: str, counts: dict[str,int], increments: dict[str,int]):
        rows = self.sheets.spreadsheets().values().get(
            spreadsheetId=workbook_id,
            range="'Overview'!A1:B100"
        ).execute(num_retries=self.api_retries).get("values", [])
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
            ).execute(num_retries=self.api_retries)
