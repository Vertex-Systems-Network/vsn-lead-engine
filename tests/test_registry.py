from pathlib import Path

import pytest

from vsn_lead_engine.models import Lead
from vsn_lead_engine.registry import (
    SupabaseRegistryIndex,
    backfill_sheet_registry,
    build_registry_index,
    collision_payload,
    fingerprint_token,
    lead_registry_payload,
    sheet_registry_payloads,
)


class FakeResponse:
    def __init__(self, data):
        self._data=data
        self.content=b"x"

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


class FakeSession:
    def __init__(self, responses):
        self.responses=list(responses)
        self.calls=[]
        self.closed=False

    def post(self, url, headers, json, timeout):
        self.calls.append({
            "url":url,
            "headers":headers,
            "json":json,
            "timeout":timeout,
        })
        return FakeResponse(self.responses.pop(0))

    def close(self):
        self.closed=True


def make_lead(**changes):
    data=dict(
        country="Canada",
        category="IT & Software",
        business_name="Example Systems",
        phone="+1 416 555 0123",
        city="Toronto",
        region="Ontario",
        source="Overture Maps Places",
        source_id="overture:abc123",
        website="https://www.example.com",
    )
    data.update(changes)
    return Lead(**data)


def test_sheets_mode_builds_no_supabase_client_without_secrets():
    assert build_registry_index({"registry":{"mode":"sheets"}}) is None


def test_supabase_client_requires_server_secrets(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL",raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY",raising=False)
    with pytest.raises(RuntimeError):
        SupabaseRegistryIndex({
            "registry":{
                "mode":"dual",
                "supabase_url_env":"SUPABASE_URL",
                "supabase_service_role_key_env":"SUPABASE_SERVICE_ROLE_KEY",
            }
        })


def test_fingerprint_token_is_compact_deterministic_and_type_separated():
    first=fingerprint_token("d","Example.COM")
    second=fingerprint_token("d","example.com")
    other_kind=fingerprint_token("u","example.com")
    assert first==second
    assert first.startswith("d:")
    assert len(first)==26
    assert first!=other_kind


def test_payload_contains_only_compact_dedupe_metadata():
    lead=make_lead()
    workbook={
        "id":"sheet123",
        "name":"US + Canada Business Leads — 2026-09-27",
        "webViewLink":"https://docs.google.com/spreadsheets/d/sheet123/edit",
    }
    collision=collision_payload(lead)
    registry=lead_registry_payload(lead,workbook)
    assert collision["candidate_unique_token"].startswith("u:")
    assert len(collision["fingerprints"])>=4
    assert registry["status"]=="PendingDaily"
    assert registry["daily_sheet_id"]=="sheet123"
    assert registry["country_code"]=="CA"
    assert "phone" not in registry
    assert "business_name" not in registry
    assert "website" not in registry


def test_collision_rpc_batches_and_returns_candidate_tokens(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL","https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY","secret")
    one=fingerprint_token("u","domain:one.example")
    three=fingerprint_token("u","domain:three.example")
    session=FakeSession([
        [{"candidate_unique_token":one}],
        [{"candidate_unique_token":three}],
    ])
    index=SupabaseRegistryIndex({
        "registry":{"mode":"supabase","batch_size":2}
    },session=session)
    leads=[
        make_lead(website="https://one.example"),
        make_lead(website="https://two.example",source_id="overture:2"),
        make_lead(website="https://three.example",source_id="overture:3"),
    ]
    keys=index.collision_keys(leads)
    assert keys=={one,three}
    assert len(session.calls)==2
    assert session.calls[0]["url"].endswith("/rest/v1/rpc/vsn_lead_registry_collisions")


def test_shadow_active_reserves_then_activates(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL","https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY","secret")
    token=fingerprint_token("u","domain:example.com")
    session=FakeSession([
        [{"unique_token":token}],
        1,
    ])
    index=SupabaseRegistryIndex({"registry":{"mode":"dual"}},session=session)
    result=index.shadow_active(
        [make_lead()],
        {"id":"sheet","name":"Daily","webViewLink":"https://docs.google.com/spreadsheets/d/sheet/edit"},
    )
    assert result=={"inserted":1,"activated":1}
    assert session.calls[0]["url"].endswith("/vsn_lead_registry_reserve")
    assert session.calls[1]["url"].endswith("/vsn_lead_registry_activate")


def test_sheet_registry_payloads_skip_nonblocking_rows_and_hash_values():
    rows=[
        [
            "First Added","Field","Region","Country","City","Category","Business Name",
            "Website","Normalized Domain","Phone","Normalized Phone","Business+City Key",
            "Unique Key","Daily Sheet","Daily Sheet URL","Status","State/Province",
            "ZIP/Postal Code","Google Place ID","Primary Source","Verification Sources",
            "Business+City+State Key"
        ],
        [
            "2026-09-27","IT & Software","North America","Canada","Toronto","IT & Software",
            "Example","https://example.com","example.com","+1 416-555-0123",
            "+14165550123","example|toronto","domain:example.com","Daily",
            "https://docs.google.com/spreadsheets/d/sheet/edit","Active","Ontario",
            "M5V","","Overture Maps Places","Overture Maps Places; Source ID: overture:x",
            "example|toronto|ontario"
        ],
        [
            "2026-09-27","Cars","North America","United States","Phoenix","Cars",
            "Wrong Category","https://wrong.example","wrong.example","+1 202-555-0123",
            "+12025550123","wrong|phoenix","domain:wrong.example","Daily",
            "https://docs.google.com/spreadsheets/d/sheet/edit","NeedsReview","Arizona",
            "85001","","Overture Maps Places","Overture Maps Places; Source ID: overture:y",
            "wrong|phoenix|arizona"
        ],
    ]
    payloads=sheet_registry_payloads(rows)
    assert len(payloads)==1
    payload=payloads[0]
    assert payload["status"]=="Active"
    assert payload["country_code"]=="CA"
    assert payload["daily_sheet_id"]=="sheet"
    assert payload["unique_token"]==fingerprint_token("u","domain:example.com")
    assert all(len(token)==26 for token in payload["fingerprints"])
    assert "example.com" not in repr(payload)


def test_backfill_dry_run_reports_skipped_nonblocking():
    class Store:
        def _registry_rows(self):
            return [
                ["First Added","Unique Key","Status"],
                ["2026-09-27","domain:example.com","Active"],
                ["2026-09-27","domain:wrong.example","NeedsReview"],
            ]

    class Index:
        def import_rows(self, rows):
            raise AssertionError("dry run must not write")

    result=backfill_sheet_registry(Store(),Index(),dry_run=True)
    assert result["status"]=="dry-run"
    assert result["source_rows"]==2
    assert result["rows"]==1
    assert result["skipped_nonblocking"]==1


def test_capacity_report_uses_actual_relation_bytes(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL","https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY","secret")
    session=FakeSession([{
        "total_rows":1000,
        "blocking_rows":1000,
        "pending_rows":0,
        "table_bytes":100000,
        "index_bytes":100000,
        "total_bytes":200000,
        "database_bytes":60*1024*1024,
    }])
    index=SupabaseRegistryIndex({"registry":{"mode":"supabase"}},session=session)
    report=index.capacity_report(daily_leads=12000,database_budget_mb=500)
    assert report["bytes_per_registry_row"]==200
    assert report["projected_daily_registry_bytes"]==2400000
    assert report["estimated_headroom_days"]>100


def test_schema_blueprint_is_compact_private_and_concurrency_safe():
    sql=Path("db/supabase_registry_schema.sql").read_text(encoding="utf-8").lower()
    assert "enable row level security" in sql
    assert "security invoker" in sql
    assert "revoke all on table public.vsn_lead_registry from public, anon, authenticated" in sql
    assert "grant select, insert, update on table public.vsn_lead_registry to service_role" in sql
    assert "using gin (fingerprints)" in sql
    assert "pg_advisory_xact_lock" in sql
    assert "business_name" not in sql
    assert "normalized_phone" not in sql
    assert "website text" not in sql
