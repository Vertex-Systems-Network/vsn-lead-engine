from pathlib import Path
import io
import json

import pytest
from botocore.exceptions import ClientError

from vsn_lead_engine.models import Lead
from vsn_lead_engine.registry import (
    R2RegistryIndex,
    audit_sheet_registry,
    backfill_sheet_registry,
    build_registry_index,
    fingerprint_token,
    lead_registry_payload,
    sheet_registry_payloads,
)


def client_error(status, code, operation):
    return ClientError(
        {
            "Error": {"Code": str(code), "Message": str(code)},
            "ResponseMetadata": {"HTTPStatusCode": status},
        },
        operation,
    )


class FakePaginator:
    def __init__(self, client):
        self.client=client

    def paginate(self, Bucket, Prefix):
        contents=[
            {"Key":key,"Size":len(value["body"])}
            for key,value in sorted(self.client.objects.items())
            if key.startswith(Prefix)
        ]
        yield {"Contents":contents}


class FakeS3:
    def __init__(self):
        self.objects={}
        self.closed=False

    def head_bucket(self, Bucket):
        return {}

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise client_error(404,"NoSuchKey","HeadObject")
        return {"Metadata":dict(self.objects[Key]["metadata"])}

    def put_object(self, Bucket, Key, Body=b"", ContentType=None, Metadata=None, IfNoneMatch=None):
        if IfNoneMatch=="*" and Key in self.objects:
            raise client_error(412,"PreconditionFailed","PutObject")
        if hasattr(Body,"read"):
            Body=Body.read()
        if isinstance(Body,str):
            Body=Body.encode()
        self.objects[Key]={
            "body":bytes(Body or b""),
            "metadata":dict(Metadata or {}),
            "content_type":ContentType,
        }
        return {"ETag":'"fake"'}

    def delete_object(self, Bucket, Key):
        self.objects.pop(Key,None)
        return {}

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise client_error(404,"NoSuchKey","GetObject")
        return {"Body":io.BytesIO(self.objects[Key]["body"])}

    def get_paginator(self, name):
        assert name=="list_objects_v2"
        return FakePaginator(self)

    def close(self):
        self.closed=True


def config():
    return {
        "registry":{
            "mode":"r2",
            "prefix":"vsn-lead-ledger/v1",
            "max_workers":8,
            "retry_attempts":2,
        }
    }


def set_r2_env(monkeypatch):
    monkeypatch.setenv("R2_ACCOUNT_ID","acct")
    monkeypatch.setenv("R2_ACCESS_KEY_ID","access")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY","secret")
    monkeypatch.setenv("R2_BUCKET","vsn-lead-engine")


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


def test_sheets_mode_needs_no_r2_client():
    assert build_registry_index({"registry":{"mode":"sheets"}}) is None


def test_r2_client_requires_all_server_secrets(monkeypatch):
    for key in ["R2_ACCOUNT_ID","R2_ACCESS_KEY_ID","R2_SECRET_ACCESS_KEY","R2_BUCKET"]:
        monkeypatch.delenv(key,raising=False)
    with pytest.raises(RuntimeError):
        R2RegistryIndex(config(),client=FakeS3())


def test_compact_token_is_deterministic_and_type_separated():
    first=fingerprint_token("d","Example.COM")
    second=fingerprint_token("d","example.com")
    assert first==second
    assert first!=fingerprint_token("u","example.com")
    assert len(first)==26


def test_unique_key_is_transaction_identity_not_redundant_permanent_object():
    payload=lead_registry_payload(make_lead(),{"id":"sheet123"})
    assert payload["unique_token"].startswith("u:")
    assert all(not token.startswith("u:") for token in payload["fingerprints"])
    assert 3 <= len(payload["fingerprints"]) <= 5


def test_import_then_collision_is_exact(monkeypatch):
    set_r2_env(monkeypatch)
    fake=FakeS3()
    index=R2RegistryIndex(config(),client=fake)
    lead=make_lead()
    payload=lead_registry_payload(lead,{"id":"sheet123"})

    result=index.import_rows([payload])
    assert result["imported"]==1
    assert index.collision_keys([lead])=={payload["unique_token"]}

    other=make_lead(
        business_name="Different Systems",
        phone="+1 647 555 0102",
        city="Ottawa",
        region="Ontario",
        source_id="overture:different",
        website="https://different.example",
    )
    assert index.collision_keys([other])==set()


def test_reservation_uses_pending_batch_and_activation_keeps_fingerprints(monkeypatch):
    set_r2_env(monkeypatch)
    fake=FakeS3()
    index=R2RegistryIndex(config(),client=fake)
    lead=make_lead()
    payload=lead_registry_payload(lead,{"id":"sheet123"})

    reserved=index.reserve_pending([lead],{"id":"sheet123"})
    assert reserved=={payload["unique_token"]}
    assert any("/pending/" in key for key in fake.objects)
    fingerprint_keys=[key for key in fake.objects if "/fp/" in key]
    assert fingerprint_keys

    index.activate(reserved)
    assert not any("/pending/" in key for key in fake.objects)
    assert all(key in fake.objects for key in fingerprint_keys)


def test_crash_recovery_rolls_back_unwritten_reservation(monkeypatch):
    set_r2_env(monkeypatch)
    fake=FakeS3()
    first=R2RegistryIndex(config(),client=fake)
    lead=make_lead()
    first.reserve_pending([lead],{"id":"sheet123"})

    class ValuesGet:
        def get(self, **kwargs):
            return self
        def execute(self, **kwargs):
            return {"values":[]}

    class FakeSheets:
        def __init__(self):
            self.spreadsheets=lambda: self
            self.values=lambda: ValuesGet()

    class Store:
        sheets=FakeSheets()
        api_retries=0

    recovered=R2RegistryIndex(config(),client=fake)
    result=recovered.reconcile_pending(Store())
    assert result["rolled_back"]==1
    assert not any("/pending/" in key or "/fp/" in key for key in fake.objects)


def test_sheet_backfill_skips_nonblocking_rows_and_never_puts_raw_pii(monkeypatch):
    set_r2_env(monkeypatch)
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
            "Example Systems","https://example.com","example.com","+1 416-555-0123",
            "+14165550123","example systems|toronto","domain:example.com","Daily",
            "https://docs.google.com/spreadsheets/d/sheet123/edit","Active","Ontario",
            "M5V","","Overture Maps Places","Overture Maps Places; Source ID: overture:x",
            "example systems|toronto|ontario"
        ],
        [
            "2026-09-27","Cars","North America","United States","Phoenix","Cars",
            "Wrong Category","https://wrong.example","wrong.example","+1 202-555-0123",
            "+12025550123","wrong category|phoenix","domain:wrong.example","Daily",
            "https://docs.google.com/spreadsheets/d/sheet123/edit","NeedsReview","Arizona",
            "85001","","Overture Maps Places","Overture Maps Places; Source ID: overture:y",
            "wrong category|phoenix|arizona"
        ],
    ]
    payloads=sheet_registry_payloads(rows)
    assert len(payloads)==1
    encoded=json.dumps(payloads)
    assert "example.com" not in encoded
    assert "+14165550123" not in encoded
    assert "Example Systems" not in encoded

    fake=FakeS3()
    index=R2RegistryIndex(config(),client=fake)
    result=index.import_rows(payloads)
    assert result["imported"]==1
    assert all("example.com" not in key for key in fake.objects)


def test_backfill_and_audit_report_exact_parity(monkeypatch):
    set_r2_env(monkeypatch)
    header=[
        "First Added","Field","Region","Country","City","Category","Business Name",
        "Website","Normalized Domain","Phone","Normalized Phone","Business+City Key",
        "Unique Key","Daily Sheet","Daily Sheet URL","Status","State/Province",
        "ZIP/Postal Code","Google Place ID","Primary Source","Verification Sources",
        "Business+City+State Key"
    ]
    row=[
        "2026-09-27","IT & Software","North America","Canada","Toronto","IT & Software",
        "Example","https://example.com","example.com","+1 416-555-0123","+14165550123",
        "example|toronto","domain:example.com","Daily",
        "https://docs.google.com/spreadsheets/d/sheet123/edit","Active","Ontario","M5V","",
        "Overture Maps Places","Overture Maps Places; Source ID: overture:x",
        "example|toronto|ontario"
    ]

    class Store:
        def _registry_rows(self):
            return [header,row]

    fake=FakeS3()
    index=R2RegistryIndex(config(),client=fake)
    backfill=backfill_sheet_registry(Store(),index)
    assert backfill["imported"]==1
    audit=audit_sheet_registry(Store(),index)
    assert audit["missing_fingerprints"]==0
    assert audit["found_fingerprints"]==audit["expected_fingerprints"]


def test_stats_count_only_private_ledger_objects(monkeypatch):
    set_r2_env(monkeypatch)
    fake=FakeS3()
    index=R2RegistryIndex(config(),client=fake)
    index.import_rows([lead_registry_payload(make_lead(),{"id":"sheet"})])
    stats=index.stats()
    assert stats["fingerprint_objects"]>=3
    assert stats["pending_transactions"]==0
    assert stats["bytes"]==0


def test_registry_migration_cli_contract_is_available():
    from vsn_lead_engine import cli as cli_module
    source=Path(cli_module.__file__).read_text(encoding="utf-8")
    assert 'sub.add_parser("registry-migrate")' in source
    assert '"audit-failed"' in source


def test_live_smoke_test_reserves_detects_and_cleans(monkeypatch):
    from vsn_lead_engine import registry as registry_module

    set_r2_env(monkeypatch)
    fake=FakeS3()

    class SmokeIndex(R2RegistryIndex):
        def __init__(self, config):
            super().__init__(config,client=fake)

    monkeypatch.setattr(registry_module,"R2RegistryIndex",SmokeIndex)
    result=registry_module.live_smoke_test(config())
    assert result["status"]=="ok"
    assert result["reserved"]==1
    assert result["collision_before"]==0
    assert result["collision_during"]==1
    assert result["collision_after"]==0
    assert result["rolled_back"]==1
    assert result["pending_transactions"]==0
    assert result["remaining_fingerprint_objects"]==0
