import json

import pytest

import vsn_lead_engine.engine as engine
from vsn_lead_engine.sheets import (
    GoogleSheetsStore,
    PermanentWorkbookReadinessError,
)


class _Exec:
    def __init__(self,payload):
        self.payload=payload

    def execute(self,**_kwargs):
        return self.payload


class _Files:
    def __init__(self,folder):
        self.folder=folder
        self.create_calls=[]
        self.update_calls=[]

    def get(self,**_kwargs):
        return _Exec(self.folder)

    def create(self,**kwargs):
        self.create_calls.append(kwargs)
        return _Exec({
            "id":"probe-123",
            "name":kwargs["body"]["name"],
            "parents":kwargs["body"]["parents"],
        })

    def update(self,**kwargs):
        self.update_calls.append(kwargs)
        return _Exec({"id":kwargs["fileId"],"trashed":True})


class _Drive:
    def __init__(self,folder):
        self._files=_Files(folder)

    def files(self):
        return self._files


def _store(auth_mode,folder):
    store=object.__new__(GoogleSheetsStore)
    store.google_auth_mode=auth_mode
    store.api_retries=0
    store.config={
        "drive":{"folder_id":"folder-123"},
        "runtime":{"timezone":"Asia/Karachi"},
    }
    store.drive=_Drive(folder)
    return store


def test_service_account_my_drive_creation_is_fail_fast_blocked():
    store=_store(
        "service-account",
        {
            "id":"folder-123",
            "name":"Global Business Leads",
            "driveId":None,
            "capabilities":{"canAddChildren":True},
        },
    )

    result=store.drive_creation_capability(probe_create=True)

    assert result["status"]=="blocked"
    assert result["permanent"] is True
    assert result["storage"]=="my-drive"
    assert result["probe_performed"] is False
    assert store.drive._files.create_calls==[]


def test_user_oauth_probe_creates_then_trashes_probe_file():
    store=_store(
        "user-oauth",
        {
            "id":"folder-123",
            "name":"Global Business Leads",
            "driveId":None,
            "capabilities":{"canAddChildren":True},
        },
    )

    result=store.drive_creation_capability(probe_create=True)

    assert result["status"]=="capable"
    assert result["auth_mode"]=="user-oauth"
    assert result["probe_performed"] is True
    assert result["probe_cleaned"] is True
    assert len(store.drive._files.create_calls)==1
    assert store.drive._files.update_calls[0]["body"]=={"trashed":True}


def test_service_account_shared_drive_can_pass_metadata_gate():
    store=_store(
        "service-account",
        {
            "id":"folder-123",
            "name":"Shared Leads",
            "driveId":"shared-drive-1",
            "capabilities":{"canAddChildren":True},
        },
    )

    result=store.drive_creation_capability()

    assert result["status"]=="capable"
    assert result["storage"]=="shared-drive"
    assert result["probe_performed"] is False


def test_readiness_retry_stops_after_permanent_drive_blocker():
    sleeps=[]
    calls=[]

    def check_fn(_config,*,run_date):
        calls.append(run_date)
        raise PermanentWorkbookReadinessError("My Drive ownership blocker")

    result=engine.recover_workbook_readiness(
        {
            "runtime":{
                "timezone":"Asia/Karachi",
                "workbook_readiness_attempts":3,
                "workbook_readiness_retry_delay_seconds":60,
            }
        },
        run_date="2026-09-30",
        attempts=3,
        delay_seconds=60,
        sleep_fn=lambda seconds:sleeps.append(seconds),
        check_fn=check_fn,
    )

    assert result["status"]=="incident"
    assert result["attempts_used"]==1
    assert result["attempts_configured"]==3
    assert result["failures"][0]["permanent"] is True
    assert calls==["2026-09-30"]
    assert sleeps==[]
