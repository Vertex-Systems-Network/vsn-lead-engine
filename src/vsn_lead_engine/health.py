from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from botocore.exceptions import ClientError


HEALTH_VERSION = 1


def _clean_text(value: Any, limit: int = 320) -> str:
    text_value=" ".join(str(value or "").split())
    return text_value[:limit]


def _safe_counts(raw: Any) -> dict[str,int]:
    if not isinstance(raw,dict):
        return {}
    result={}
    for key,value in raw.items():
        try:
            result[_clean_text(key,120)]=max(0,int(value or 0))
        except (TypeError,ValueError):
            continue
    return result


def health_event_id(kind: str, origin: str) -> str:
    github_run=os.getenv("GITHUB_RUN_ID","").strip()
    github_attempt=os.getenv("GITHUB_RUN_ATTEMPT","").strip()
    if github_run:
        return f"{_clean_text(kind,40)}:{_clean_text(origin,60)}:{github_run}:{github_attempt or '1'}"
    return f"{_clean_text(kind,40)}:{_clean_text(origin,60)}:{uuid.uuid4().hex}"


def run_health_event(
    result: dict,
    *,
    origin: str,
    timestamp: str | None = None,
) -> dict:
    counts=_safe_counts(result.get("counts",{}))
    target=1000
    shortfalls={
        category:max(0,target-count)
        for category,count in counts.items()
        if count < target
    }
    event={
        "event_id":health_event_id("run",origin),
        "timestamp":timestamp or datetime.now(timezone.utc).isoformat(),
        "kind":"run",
        "origin":_clean_text(origin,60),
        "status":_clean_text(result.get("status","unknown"),80),
        "accepted":max(0,int(result.get("accepted",0) or 0)),
        "discovered":max(0,int(result.get("discovered",0) or 0)),
        "cycles":max(0,int(result.get("cycles_executed",0) or 0)),
        "categories_attempted":max(
            0,int(result.get("categories_attempted",0) or 0)
        ),
        "source_batch_duplicates":max(
            0,int(result.get("source_batch_duplicates",0) or 0)
        ),
        "remote_prefilter_duplicates":max(
            0,int(result.get("remote_prefilter_duplicates",0) or 0)
        ),
        "source_errors":max(0,int(result.get("source_errors",0) or 0)),
        "zero_result_shards":max(
            0,int(result.get("zero_result_shards",0) or 0)
        ),
        "adaptive_cooldown_routes_deferred":max(
            0,int(result.get("adaptive_cooldown_routes_deferred",0) or 0)
        ),
        "counts":counts,
        "shortfalls":shortfalls,
        "quota_complete":bool(
            result.get("status")=="complete"
            or (counts and not shortfalls)
        ),
    }
    schedule=result.get("schedule") or {}
    if isinstance(schedule,dict):
        event["schedule_slot"]=_clean_text(schedule.get("slot",""),80)
        event["schedule_delay_minutes"]=max(
            0,int(schedule.get("start_delay_minutes",0) or 0)
        )
    state=result.get("adaptive_yield_state") or {}
    if isinstance(state,dict):
        event["adaptive_state_loaded"]=bool(state.get("loaded",False))
        event["adaptive_state_saved"]=bool(state.get("saved",False))
        if state.get("load_error"):
            event["adaptive_state_load_error"]=_clean_text(state["load_error"])
        if state.get("save_error"):
            event["adaptive_state_save_error"]=_clean_text(state["save_error"])
    history=result.get("adaptive_yield_history") or {}
    if isinstance(history,dict):
        event["adaptive_history_loaded"]=bool(history.get("loaded",False))
        event["adaptive_history_saved"]=bool(history.get("saved",False))
        if history.get("load_error"):
            event["adaptive_history_load_error"]=_clean_text(history["load_error"])
        if history.get("save_error"):
            event["adaptive_history_save_error"]=_clean_text(history["save_error"])
    cache=result.get("registry_read_cache") or {}
    if isinstance(cache,dict):
        event["registry_cache_enabled"]=bool(cache.get("enabled",False))
        event["registry_cache_entries"]=max(
            0,int(cache.get("entries",0) or 0)
        )
        event["registry_cache_hits"]=max(
            0,int(cache.get("hits",0) or 0)
        )
        event["registry_cache_misses"]=max(
            0,int(cache.get("misses",0) or 0)
        )
    return event


def readiness_health_event(
    result: dict,
    *,
    timestamp: str | None = None,
) -> dict:
    failures=[]
    for item in result.get("failures",[]) or []:
        if not isinstance(item,dict):
            continue
        failures.append({
            "attempt":max(0,int(item.get("attempt",0) or 0)),
            "error_type":_clean_text(item.get("error_type",""),100),
            "message":_clean_text(item.get("message","")),
        })

    counts=_safe_counts(result.get("counts",{}))
    return {
        "event_id":health_event_id("readiness","prestart"),
        "timestamp":timestamp or datetime.now(timezone.utc).isoformat(),
        "kind":"readiness",
        "origin":"prestart",
        "status":_clean_text(result.get("status","unknown"),80),
        "attempts_used":max(0,int(result.get("attempts_used",0) or 0)),
        "attempts_configured":max(
            0,int(result.get("attempts_configured",0) or 0)
        ),
        "workbook_created":bool((result.get("workbook") or {}).get("created",False)),
        "counts":counts,
        "quota_complete":bool(result.get("quota_complete",False)),
        "failures":failures,
    }


def incident_health_event(
    *,
    origin: str,
    error: Exception,
    run_date: str,
    timestamp: str | None = None,
) -> dict:
    return {
        "event_id":health_event_id("incident",origin),
        "timestamp":timestamp or datetime.now(timezone.utc).isoformat(),
        "kind":"incident",
        "origin":_clean_text(origin,60),
        "status":"failed",
        "run_date":run_date,
        "error_type":type(error).__name__,
        "message":_clean_text(error),
        "quota_complete":False,
    }


class DailyHealthLedgerStore:
    """Compact, PII-free operational audit ledger stored in the existing R2 bucket."""

    def __init__(self, registry_index, *, max_events: int = 96):
        if registry_index is None:
            raise ValueError("DailyHealthLedgerStore requires an R2 registry index.")
        self.client=registry_index.client
        self.bucket=registry_index.bucket
        self.prefix=str(registry_index.prefix).strip("/")
        self.max_events=max(16,min(256,int(max_events)))

    def key(self, run_date: str) -> str:
        return f"{self.prefix}/health/v1/{run_date}.json"

    @staticmethod
    def _is_missing(exc: ClientError) -> bool:
        status=int(
            exc.response.get("ResponseMetadata",{}).get("HTTPStatusCode",0) or 0
        )
        code=str(exc.response.get("Error",{}).get("Code",""))
        return status==404 or code in {"404","NoSuchKey","NotFound"}

    def load(self, run_date: str) -> dict:
        key=self.key(run_date)
        try:
            response=self.client.get_object(Bucket=self.bucket,Key=key)
        except ClientError as exc:
            if self._is_missing(exc):
                return {
                    "version":HEALTH_VERSION,
                    "run_date":run_date,
                    "events":[],
                    "summary":self._summary([]),
                }
            raise

        body=response["Body"].read()
        payload=json.loads(body.decode("utf-8"))
        if int(payload.get("version",0) or 0)!=HEALTH_VERSION:
            raise RuntimeError(
                f"Unsupported health ledger version: {payload.get('version')!r}"
            )
        if str(payload.get("run_date","")).strip()!=run_date:
            raise RuntimeError("Health ledger date does not match requested run date.")
        events=payload.get("events",[]) or []
        if not isinstance(events,list):
            raise RuntimeError("Health ledger events must be a list.")
        events=[item for item in events if isinstance(item,dict)]
        return {
            "version":HEALTH_VERSION,
            "run_date":run_date,
            "events":events[-self.max_events:],
            "summary":self._summary(events[-self.max_events:]),
        }

    def append(self, run_date: str, event: dict) -> dict:
        payload=self.load(run_date)
        events=list(payload.get("events",[]))
        event_id=_clean_text(event.get("event_id",""),180)
        if event_id and any(
            _clean_text(item.get("event_id",""),180)==event_id
            for item in events
        ):
            return {
                "status":"duplicate",
                "key":self.key(run_date),
                "events":len(events),
                "summary":self._summary(events),
            }

        clean_event=self._clean_event(event)
        events.append(clean_event)
        events=events[-self.max_events:]
        summary=self._summary(events)
        body=json.dumps(
            {
                "version":HEALTH_VERSION,
                "run_date":run_date,
                "updated_at":datetime.now(timezone.utc).isoformat(),
                "events":events,
                "summary":summary,
            },
            separators=(",",":"),
            sort_keys=True,
        ).encode("utf-8")
        key=self.key(run_date)
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
            Metadata={
                "state":"daily-health-v1",
                "run-date":run_date,
            },
        )
        return {
            "status":"appended",
            "key":key,
            "events":len(events),
            "bytes":len(body),
            "summary":summary,
        }

    @staticmethod
    def _clean_event(event: dict) -> dict:
        # Explicit allow-list prevents future callers from accidentally persisting
        # raw lead objects or arbitrary business contact fields.
        scalar_fields={
            "event_id","timestamp","kind","origin","status","accepted","discovered",
            "cycles","categories_attempted","source_batch_duplicates",
            "remote_prefilter_duplicates",
            "source_errors","zero_result_shards",
            "adaptive_cooldown_routes_deferred","quota_complete",
            "schedule_slot","schedule_delay_minutes",
            "adaptive_state_loaded","adaptive_state_saved",
            "adaptive_state_load_error","adaptive_state_save_error",
            "adaptive_history_loaded","adaptive_history_saved",
            "adaptive_history_load_error","adaptive_history_save_error",
            "registry_cache_enabled","registry_cache_entries",
            "registry_cache_hits","registry_cache_misses",
            "attempts_used","attempts_configured","workbook_created",
            "error_type","message",
        }
        result={}
        for key in scalar_fields:
            if key not in event:
                continue
            value=event[key]
            if isinstance(value,(bool,int,float)) or value is None:
                result[key]=value
            else:
                result[key]=_clean_text(value)
        result["counts"]=_safe_counts(event.get("counts",{}))
        result["shortfalls"]=_safe_counts(event.get("shortfalls",{}))

        failures=[]
        for item in event.get("failures",[]) or []:
            if not isinstance(item,dict):
                continue
            failures.append({
                "attempt":max(0,int(item.get("attempt",0) or 0)),
                "error_type":_clean_text(item.get("error_type",""),100),
                "message":_clean_text(item.get("message","")),
            })
        if failures:
            result["failures"]=failures[:5]
        return result

    @staticmethod
    def _summary(events: list[dict]) -> dict:
        native=sum(
            1 for item in events
            if item.get("kind")=="run" and item.get("origin")=="native-schedule"
        )
        recovery=sum(
            1 for item in events
            if item.get("kind")=="run" and item.get("origin")=="recovery-push"
        )
        manual=sum(
            1 for item in events
            if item.get("kind")=="run" and item.get("origin")=="manual"
        )
        incidents=sum(
            1 for item in events
            if item.get("kind")=="incident" or item.get("status") in {"incident","failed"}
        )
        quota_completed_at=""
        for item in events:
            if item.get("quota_complete"):
                quota_completed_at=_clean_text(item.get("timestamp",""),80)
                break
        latest_readiness=next(
            (
                _clean_text(item.get("status",""),80)
                for item in reversed(events)
                if item.get("kind")=="readiness"
            ),
            "",
        )
        return {
            "event_count":len(events),
            "native_runs":native,
            "recovery_runs":recovery,
            "manual_runs":manual,
            "incidents":incidents,
            "latest_readiness":latest_readiness,
            "quota_completed_at":quota_completed_at,
            "last_event_at":(
                _clean_text(events[-1].get("timestamp",""),80) if events else ""
            ),
        }
