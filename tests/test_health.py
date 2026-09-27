import io
import json

from botocore.exceptions import ClientError

from vsn_lead_engine.health import (
    DailyHealthLedgerStore,
    readiness_health_event,
    run_health_event,
)


def client_error(status, code, operation):
    return ClientError(
        {
            "Error":{"Code":str(code),"Message":str(code)},
            "ResponseMetadata":{"HTTPStatusCode":status},
        },
        operation,
    )


class FakeS3:
    def __init__(self):
        self.objects={}

    def get_object(self,Bucket,Key):
        if Key not in self.objects:
            raise client_error(404,"NoSuchKey","GetObject")
        return {"Body":io.BytesIO(self.objects[Key]["body"])}

    def put_object(self,Bucket,Key,Body=b"",ContentType=None,Metadata=None):
        if isinstance(Body,str):
            Body=Body.encode()
        self.objects[Key]={
            "body":bytes(Body or b""),
            "content_type":ContentType,
            "metadata":dict(Metadata or {}),
        }
        return {}


class FakeRegistry:
    def __init__(self):
        self.client=FakeS3()
        self.bucket="bucket"
        self.prefix="vsn-lead-ledger/v1"


def test_health_ledger_missing_day_is_empty():
    store=DailyHealthLedgerStore(FakeRegistry())
    payload=store.load("2026-09-28")
    assert payload["events"]==[]
    assert payload["summary"]["event_count"]==0
    assert payload["summary"]["quota_completed_at"]==""


def test_health_ledger_appends_and_deduplicates_event_id():
    registry=FakeRegistry()
    store=DailyHealthLedgerStore(registry)
    event={
        "event_id":"run:native:123:1",
        "timestamp":"2026-09-28T08:00:00+05:00",
        "kind":"run",
        "origin":"native-schedule",
        "status":"ok",
        "accepted":100,
        "discovered":400,
        "counts":{"A":100},
        "shortfalls":{"A":900},
        "quota_complete":False,
    }
    first=store.append("2026-09-28",event)
    second=store.append("2026-09-28",event)

    assert first["status"]=="appended"
    assert second["status"]=="duplicate"
    assert second["events"]==1
    loaded=store.load("2026-09-28")
    assert loaded["summary"]["native_runs"]==1


def test_health_ledger_summary_tracks_recovery_incident_and_completion():
    registry=FakeRegistry()
    store=DailyHealthLedgerStore(registry)
    events=[
        {
            "event_id":"ready:1",
            "timestamp":"2026-09-28T07:50:00+05:00",
            "kind":"readiness",
            "origin":"prestart",
            "status":"recovered",
            "quota_complete":False,
        },
        {
            "event_id":"native:1",
            "timestamp":"2026-09-28T08:00:00+05:00",
            "kind":"run",
            "origin":"native-schedule",
            "status":"ok",
            "quota_complete":False,
        },
        {
            "event_id":"incident:1",
            "timestamp":"2026-09-28T09:00:00+05:00",
            "kind":"incident",
            "origin":"native-schedule",
            "status":"failed",
            "error_type":"TimeoutError",
            "message":"source timeout",
            "quota_complete":False,
        },
        {
            "event_id":"recovery:1",
            "timestamp":"2026-09-28T09:20:00+05:00",
            "kind":"run",
            "origin":"recovery-push",
            "status":"complete",
            "quota_complete":True,
        },
    ]
    for event in events:
        store.append("2026-09-28",event)

    summary=store.load("2026-09-28")["summary"]
    assert summary["latest_readiness"]=="recovered"
    assert summary["native_runs"]==1
    assert summary["recovery_runs"]==1
    assert summary["incidents"]==1
    assert summary["quota_completed_at"]=="2026-09-28T09:20:00+05:00"


def test_health_ledger_allowlist_drops_raw_lead_fields():
    registry=FakeRegistry()
    store=DailyHealthLedgerStore(registry)
    store.append(
        "2026-09-28",
        {
            "event_id":"safe:1",
            "timestamp":"2026-09-28T08:00:00+05:00",
            "kind":"run",
            "origin":"native-schedule",
            "status":"ok",
            "business_name":"Secret Business",
            "phone":"+12025550199",
            "email":"secret@example.com",
            "website":"https://secret.example",
            "raw_leads":[{"phone":"+12025550199"}],
            "quota_complete":False,
        },
    )

    key=store.key("2026-09-28")
    raw=registry.client.objects[key]["body"].decode("utf-8")
    assert "Secret Business" not in raw
    assert "+12025550199" not in raw
    assert "secret@example.com" not in raw
    assert "secret.example" not in raw


def test_health_ledger_caps_old_events():
    registry=FakeRegistry()
    store=DailyHealthLedgerStore(registry,max_events=16)
    for index in range(20):
        store.append(
            "2026-09-28",
            {
                "event_id":f"event:{index}",
                "timestamp":f"2026-09-28T{index:02d}:00:00+05:00",
                "kind":"run",
                "origin":"native-schedule",
                "status":"ok",
                "quota_complete":False,
            },
        )
    loaded=store.load("2026-09-28")
    assert len(loaded["events"])==16
    assert loaded["events"][0]["event_id"]=="event:4"


def test_run_health_event_builds_shortfalls_and_schedule():
    event=run_health_event(
        {
            "status":"ok",
            "accepted":50,
            "discovered":200,
            "cycles_executed":2,
            "counts":{"A":1000,"B":750},
            "schedule":{
                "slot":"2026-09-28T08:00",
                "start_delay_minutes":17,
            },
            "adaptive_yield_state":{
                "loaded":True,
                "saved":True,
            },
            "adaptive_yield_history":{
                "loaded":True,
                "saved":False,
            },
            "adaptive_cooldown_routes_deferred":3,
        },
        origin="native-schedule",
        timestamp="2026-09-28T08:17:00+05:00",
    )
    assert event["shortfalls"]=={"B":250}
    assert event["quota_complete"] is False
    assert event["schedule_delay_minutes"]==17
    assert event["adaptive_state_loaded"] is True
    assert event["adaptive_history_loaded"] is True
    assert event["adaptive_history_saved"] is False
    assert event["adaptive_cooldown_routes_deferred"]==3


def test_readiness_health_event_keeps_failure_reason_not_workbook_identity():
    event=readiness_health_event(
        {
            "status":"recovered",
            "attempts_used":2,
            "attempts_configured":3,
            "workbook":{
                "id":"sensitive-sheet-id",
                "name":"daily workbook",
                "created":True,
            },
            "counts":{"A":0},
            "quota_complete":False,
            "failures":[
                {
                    "attempt":1,
                    "error_type":"TimeoutError",
                    "message":"temporary Google timeout",
                }
            ],
        },
        timestamp="2026-09-28T07:51:00+05:00",
    )
    encoded=json.dumps(event)
    assert event["workbook_created"] is True
    assert event["failures"][0]["error_type"]=="TimeoutError"
    assert "sensitive-sheet-id" not in encoded
    assert "daily workbook" not in encoded


def test_health_cli_contract_is_available():
    from pathlib import Path
    from vsn_lead_engine import cli as cli_module

    source=Path(cli_module.__file__).read_text(encoding="utf-8")
    assert 'sub.add_parser("health-show")' in source
    assert 'sub.add_parser("health-incident")' in source
    assert '"--record-health"' in source


def test_health_workflow_contract_records_readiness_and_blocked_runs():
    from pathlib import Path

    readiness=Path(".github/workflows/daily-workbook-readiness.yml").read_text(
        encoding="utf-8"
    )
    lead=Path(".github/workflows/lead-engine.yml").read_text(encoding="utf-8")

    assert "--record-health" in readiness
    assert "R2_ACCOUNT_ID" in readiness
    assert "VSN_RUN_ORIGIN: recovery-push" in lead
    assert "health-incident" in lead
    assert "MissingGoogleCredential" in lead
