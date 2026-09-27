import os
from pathlib import Path

import pytest

from vsn_lead_engine.models import Lead
from vsn_lead_engine.registry import (
    SupabaseRegistryIndex,
    backfill_sheet_registry,
    build_registry_index,
    collision_payload,
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


def test_payload_contains_all_dedupe_keys():
    lead=make_lead()
    workbook={
        "id":"sheet123",
        "name":"US + Canada Business Leads — 2026-09-27",
        "webViewLink":"https://docs.google.com/spreadsheets/d/sheet123/edit",
    }
    collision=collision_payload(lead)
    registry=lead_registry_payload(lead,workbook)
    assert collision["candidate_unique_key"]=="domain:example.com"
    assert collision["source_id"]=="overture:abc123"
    assert collision["normalized_domain"]=="example.com"
    assert registry["status"]=="PendingDaily"
    assert registry["daily_sheet"]==workbook["name"]


def test_collision_rpc_batches_and_returns_candidate_keys(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL","https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY","secret")
    session=FakeSession([
        [{"candidate_unique_key":"domain:one.example"}],
        [{"candidate_unique_key":"domain:three.example"}],
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
    assert keys=={"domain:one.example","domain:three.example"}
    assert len(session.calls)==2
    assert session.calls[0]["url"].endswith("/rest/v1/rpc/vsn_lead_registry_collisions")


def test_shadow_active_reserves_then_activates(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL","https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY","secret")
    session=FakeSession([
        [{"unique_key":"domain:example.com"}],
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


def test_sheet_registry_payloads_preserve_quarantine_as_nonblocking():
    rows=[
        [
            "First Added","Field","Region","Country","City","Category","Business Name",
            "Website","Normalized Domain","Phone","Normalized Phone","Business+City Key",
            "Unique Key","Daily Sheet","Daily Sheet URL","Status","State/Province",
            "ZIP/Postal Code","Google Place ID","Primary Source","Verification Sources",
            "Business+City+State Key"
        ],
        [
            "2026-09-27","Cars","North America","United States","Phoenix","Cars",
            "Example","https://example.com","example.com","+1 202-555-0123",
            "+12025550123","example|phoenix","domain:example.com","Daily",
            "https://docs.google.com/spreadsheets/d/sheet/edit","Needs Review","Arizona",
            "85001","","Overture Maps Places","Overture Maps Places; Source ID: overture:x",
            "example|phoenix|arizona"
        ],
    ]
    payloads=sheet_registry_payloads(rows)
    assert len(payloads)==1
    assert payloads[0]["status"]=="NeedsReview"
    assert payloads[0]["source_id"]=="overture:x"


def test_backfill_dry_run_does_not_write():
    class Store:
        def _registry_rows(self):
            return [
                ["First Added","Unique Key","Status"],
                ["2026-09-27","domain:example.com","Active"],
            ]

    class Index:
        def import_rows(self, rows):
            raise AssertionError("dry run must not write")

    result=backfill_sheet_registry(Store(),Index(),dry_run=True)
    assert result["status"]=="dry-run"
    assert result["rows"]==1


def test_schema_blueprint_is_private_service_role_only():
    sql=Path("db/supabase_registry_schema.sql").read_text(encoding="utf-8").lower()
    assert "enable row level security" in sql
    assert "security invoker" in sql
    assert "revoke all on table public.vsn_lead_registry from public, anon, authenticated" in sql
    assert "grant select, insert, update on table public.vsn_lead_registry to service_role" in sql
    assert "status in ('active','pendingdaily')" in sql
