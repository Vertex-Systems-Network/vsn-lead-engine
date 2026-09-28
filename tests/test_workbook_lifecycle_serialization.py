from pathlib import Path

import pytest

from vsn_lead_engine.sheets import (
    DuplicateDailyWorkbookError,
    GoogleSheetsStore,
)


class _Exec:
    def __init__(self,payload):
        self.payload=payload

    def execute(self,**_kwargs):
        return self.payload


class _Files:
    def __init__(self,files):
        self._files=list(files)
        self.list_calls=[]

    def list(self,**kwargs):
        self.list_calls.append(kwargs)
        return _Exec({"files":list(self._files)})


class _Drive:
    def __init__(self,files):
        self._files_api=_Files(files)

    def files(self):
        return self._files_api


def _find_store(files):
    store=object.__new__(GoogleSheetsStore)
    store.api_retries=0
    store.config={"drive":{"folder_id":"folder-123"}}
    store.drive=_Drive(files)
    return store


def test_find_daily_workbook_returns_single_exact_match():
    store=_find_store([
        {
            "id":"sheet-1",
            "name":"US + Canada Business Leads — 2026-09-29",
            "createdTime":"2026-09-28T17:42:00Z",
        }
    ])

    result=store._find_daily_workbook(
        "US + Canada Business Leads — 2026-09-29"
    )

    assert result["id"]=="sheet-1"
    assert len(store.drive._files_api.list_calls)==1


def test_find_daily_workbook_fails_closed_on_duplicate_active_files():
    store=_find_store([
        {
            "id":"sheet-1",
            "name":"US + Canada Business Leads — 2026-09-29",
            "createdTime":"2026-09-28T17:42:00Z",
        },
        {
            "id":"sheet-2",
            "name":"US + Canada Business Leads — 2026-09-29",
            "createdTime":"2026-09-28T17:43:00Z",
        },
    ])

    with pytest.raises(
        DuplicateDailyWorkbookError,
        match="2 active daily workbooks",
    ):
        store._find_daily_workbook(
            "US + Canada Business Leads — 2026-09-29"
        )


def test_create_path_rechecks_single_canonical_workbook_before_sheet_writes():
    store=object.__new__(GoogleSheetsStore)
    store.run_date="2026-09-29"
    store.config={
        "drive":{
            "folder_id":"folder-123",
            "daily_title_prefix":"US + Canada Business Leads — ",
        },
        "runtime":{
            "precreated_workbook_bootstrap_enabled":True,
            "timezone":"Asia/Karachi",
        },
        "categories":["A"],
    }

    calls={"find":0,"create":0}
    def fake_find(_title):
        calls["find"]+=1
        if calls["find"]==1:
            return None
        raise DuplicateDailyWorkbookError("post-create duplicate detected")

    store._find_daily_workbook=fake_find
    store.drive_creation_capability=lambda:{"status":"capable"}
    def fake_create(_title):
        calls["create"]+=1
        return {"id":"new-sheet","name":"daily"}
    store._create_daily_workbook=fake_create

    with pytest.raises(
        DuplicateDailyWorkbookError,
        match="post-create duplicate",
    ):
        store.ensure_lead_workbook()

    assert calls=={"find":2,"create":1}


def test_lead_and_readiness_share_fifo_production_concurrency_queue():
    lead=Path(".github/workflows/lead-engine.yml").read_text(encoding="utf-8")
    readiness=Path(
        ".github/workflows/daily-workbook-readiness.yml"
    ).read_text(encoding="utf-8")

    assert (
        "group: vsn-lead-engine-${{ github.event_name == 'pull_request' "
        "&& github.event.pull_request.number || 'production' }}"
    ) in lead
    assert "group: vsn-lead-engine-production" in readiness
    assert "queue: max" in lead
    assert "queue: max" in readiness
    assert "cancel-in-progress: true" not in lead
    assert "cancel-in-progress: true" not in readiness


def test_pull_request_validation_keeps_separate_concurrency_key():
    lead=Path(".github/workflows/lead-engine.yml").read_text(encoding="utf-8")

    assert "github.event.pull_request.number" in lead
    assert "|| 'production'" in lead
    assert "queue: max" in lead
