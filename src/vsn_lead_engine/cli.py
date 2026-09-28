from __future__ import annotations
import argparse,json,os,sys
from datetime import datetime
from zoneinfo import ZoneInfo
from .config import load_config
from .engine import check_workbook_readiness, recover_workbook_readiness, run_until_quota
from .health import (
    DailyHealthLedgerStore,
    health_event_id,
    incident_health_event,
    readiness_health_event,
    run_health_event,
)
from .registry import audit_sheet_registry, backfill_sheet_registry, build_registry_index, live_smoke_test
from .schedule import scheduled_run_window
from .sheets import GoogleSheetsStore
from .taxonomy_audit import audit_motorbike_taxonomy
from .watchdog import supervise_process

def _registry_index(config: dict):
    index=build_registry_index(config)
    if index is None:
        raise RuntimeError("Registry maintenance requires registry.mode dual or r2.")
    return index

def _health_append(config: dict, run_date: str, event: dict) -> dict:
    index=None
    try:
        index=_registry_index(config)
        store=DailyHealthLedgerStore(
            index,
            max_events=int(config["runtime"].get("health_ledger_max_events",96)),
        )
        meta=store.append(run_date,event)
        return {
            "recorded":meta.get("status") in {"appended","duplicate"},
            **meta,
        }
    except Exception as exc:
        return {
            "recorded":False,
            "error":f"{type(exc).__name__}: {exc}",
        }
    finally:
        if index is not None:
            close=getattr(index,"close",None)
            if callable(close):
                close()


def _run_date(config: dict) -> str:
    return datetime.now(
        ZoneInfo(config["runtime"]["timezone"])
    ).date().isoformat()


def _run_with_incident_capture(
    config: dict,
    *,
    origin: str,
    schedule: dict | None = None,
) -> tuple[int,dict]:
    try:
        result=run_until_quota(
            config,
            dry_run=False,
            origin=origin,
            schedule=schedule,
        )
        if (
            bool(config["runtime"].get("health_ledger_enabled",True))
            and "health_ledger" not in result
        ):
            run_date=result.get("run_date") or _run_date(config)
            result["health_ledger"]=_health_append(
                config,
                run_date,
                run_health_event(result,origin=origin),
            )
        return 0,result
    except Exception as exc:
        run_date=_run_date(config)
        health=_health_append(
            config,
            run_date,
            incident_health_event(
                origin=origin,
                error=exc,
                run_date=run_date,
            ),
        )
        return 2,{
            "status":"incident",
            "run_date":run_date,
            "origin":origin,
            "error_type":type(exc).__name__,
            "message":str(exc),
            "health_ledger":health,
        }

def main() -> int:
    parser=argparse.ArgumentParser(prog="vsn-lead-engine")
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("validate")
    sub.add_parser("workbook-ready")
    recovery_parser=sub.add_parser("workbook-ready-recover")
    recovery_parser.add_argument("--attempts",type=int,default=None)
    recovery_parser.add_argument("--delay-seconds",type=float,default=None)
    recovery_parser.add_argument("--record-health",action="store_true")
    run_parser=sub.add_parser("run")
    run_parser.add_argument("--dry-run",action="store_true")
    run_parser.add_argument("--scheduled",action="store_true")
    supervised_parser=sub.add_parser("supervised-run")
    supervised_parser.add_argument("--scheduled",action="store_true")
    taxonomy_parser=sub.add_parser("taxonomy-audit")
    taxonomy_parser.add_argument("--max-geographies",type=int,default=8)
    taxonomy_parser.add_argument("--rows-per-geography",type=int,default=250)
    backfill_parser=sub.add_parser("registry-backfill")
    backfill_parser.add_argument("--dry-run",action="store_true")
    sub.add_parser("registry-stats")
    sub.add_parser("registry-check")
    sub.add_parser("registry-audit")
    sub.add_parser("registry-migrate")
    sub.add_parser("registry-smoke")
    health_parser=sub.add_parser("health-show")
    health_parser.add_argument("--date",default=None)
    incident_parser=sub.add_parser("health-incident")
    incident_parser.add_argument("--origin",required=True)
    incident_parser.add_argument("--error-type",required=True)
    incident_parser.add_argument("--message",required=True)
    args=parser.parse_args()
    config=load_config()
    if args.command=="supervised-run":
        runtime=config["runtime"]
        scheduled=bool(args.scheduled)
        origin=(
            "native-schedule"
            if scheduled
            else str(os.getenv("VSN_RUN_ORIGIN","manual") or "manual").strip()
        )
        command=[sys.executable,"-m","vsn_lead_engine.cli","run"]
        if scheduled:
            command.append("--scheduled")
        result=supervise_process(
            command,
            timeout_seconds=float(runtime.get("process_watchdog_seconds",1560)),
            kill_grace_seconds=float(
                runtime.get("process_watchdog_kill_grace_seconds",20)
            ),
        )
        result["origin"]=origin
        result["run_date"]=_run_date(config)
        if (
            result.get("status")=="watchdog-timeout"
            and bool(runtime.get("health_ledger_enabled",True))
        ):
            timeout_error=TimeoutError(
                "Lead child process exceeded the process watchdog budget "
                f"of {result.get('timeout_seconds')} seconds."
            )
            result["health_ledger"]=_health_append(
                config,
                result["run_date"],
                incident_health_event(
                    origin=origin,
                    error=timeout_error,
                    run_date=result["run_date"],
                ),
            )
        print(json.dumps(result,indent=2,default=str))
        return int(result.get("exit_code",2) or 0)
    if args.command=="taxonomy-audit":
        result=audit_motorbike_taxonomy(
            config,
            max_geographies=max(1,min(24,args.max_geographies)),
            rows_per_geography=max(25,min(1000,args.rows_per_geography)),
        )
        print(json.dumps(result,indent=2,default=str))
        return 0 if result.get("status")=="ok" else 2
    if args.command=="validate":
        print(json.dumps({
            "status":"valid",
            "mode":config["runtime"]["mode"],
            "enabled":config["runtime"]["enabled"],
            "categories":len(config["categories"]),
            "daily_target_total":len(config["categories"])*int(config["runtime"]["daily_target_per_category"]),
            "registry_mode":config["registry"]["mode"],
        },indent=2))
        return 0
    if args.command=="workbook-ready":
        print(json.dumps(check_workbook_readiness(config),indent=2,default=str))
        return 0
    if args.command=="workbook-ready-recover":
        result=recover_workbook_readiness(
            config,
            attempts=args.attempts,
            delay_seconds=args.delay_seconds,
        )
        if args.record_health:
            result["health_ledger"]=_health_append(
                config,
                result.get("run_date") or _run_date(config),
                readiness_health_event(result),
            )
        print(json.dumps(result,indent=2,default=str))
        return 0 if result["status"] in {"ready","recovered"} else 2
    if args.command=="registry-backfill":
        store=GoogleSheetsStore(config)
        index=_registry_index(config)
        try:
            result=backfill_sheet_registry(store,index,dry_run=args.dry_run)
        finally:
            index.close()
        print(json.dumps(result,indent=2,default=str))
        return 0
    if args.command=="registry-stats":
        index=_registry_index(config)
        try:
            result=index.stats()
        finally:
            index.close()
        print(json.dumps(result,indent=2,default=str))
        return 0
    if args.command=="registry-check":
        index=_registry_index(config)
        try:
            result=index.verify()
        finally:
            index.close()
        print(json.dumps(result,indent=2,default=str))
        return 0
    if args.command=="registry-audit":
        store=GoogleSheetsStore(config)
        index=_registry_index(config)
        try:
            result=audit_sheet_registry(store,index)
        finally:
            index.close()
        print(json.dumps(result,indent=2,default=str))
        return 0
    if args.command=="registry-smoke":
        result=live_smoke_test(config)
        print(json.dumps(result,indent=2,default=str))
        return 0 if result["status"]=="ok" else 2
    if args.command=="registry-migrate":
        store=GoogleSheetsStore(config)
        index=_registry_index(config)
        try:
            check=index.verify()
            dry=backfill_sheet_registry(store,index,dry_run=True)
            backfill=backfill_sheet_registry(store,index,dry_run=False)
            audit=audit_sheet_registry(store,index)
            stats=index.stats()
        finally:
            index.close()
        result={
            "status":"ok" if int(audit.get("missing_fingerprints",0) or 0)==0 else "audit-failed",
            "check":check,
            "dry_run":dry,
            "backfill":backfill,
            "audit":audit,
            "stats":stats,
        }
        print(json.dumps(result,indent=2,default=str))
        return 0 if result["status"]=="ok" else 2
    if args.command=="health-incident":
        run_date=_run_date(config)
        result=_health_append(
            config,
            run_date,
            {
                "event_id":health_event_id("incident",args.origin),
                "timestamp":datetime.now(ZoneInfo(config["runtime"]["timezone"])).isoformat(),
                "kind":"incident",
                "origin":args.origin,
                "status":"failed",
                "error_type":args.error_type,
                "message":args.message,
                "quota_complete":False,
            },
        )
        print(json.dumps(result,indent=2,default=str))
        return 0 if result.get("recorded") else 2
    if args.command=="health-show":
        run_date=args.date or _run_date(config)
        index=_registry_index(config)
        try:
            result=DailyHealthLedgerStore(
                index,
                max_events=int(config["runtime"].get("health_ledger_max_events",96)),
            ).load(run_date)
        finally:
            index.close()
        print(json.dumps(result,indent=2,default=str))
        return 0
    if args.scheduled and not args.dry_run:
        gate=scheduled_run_window(config)
        if not gate["allowed"]:
            result={
                "status":"scheduled-window-skipped",
                "run_date":gate["run_date"],
                "schedule":gate,
            }
            if bool(config["runtime"].get("health_ledger_enabled",True)):
                result["health_ledger"]=_health_append(
                    config,
                    gate["run_date"],
                    run_health_event(result,origin="native-schedule"),
                )
            print(json.dumps(result,indent=2,default=str))
            return 0
        code,result=_run_with_incident_capture(
            config,
            origin="native-schedule",
            schedule=gate,
        )
        print(json.dumps(result,indent=2,default=str))
        return code

    if args.dry_run:
        print(json.dumps(run_until_quota(config,dry_run=True),indent=2,default=str))
        return 0

    origin=str(os.getenv("VSN_RUN_ORIGIN","manual") or "manual").strip()
    code,result=_run_with_incident_capture(
        config,
        origin=origin,
    )
    print(json.dumps(result,indent=2,default=str))
    return code

if __name__=="__main__":
    sys.exit(main())
