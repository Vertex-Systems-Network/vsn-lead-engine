from __future__ import annotations
import argparse,json,sys
from .config import load_config
from .engine import check_workbook_readiness, recover_workbook_readiness, run_until_quota
from .registry import audit_sheet_registry, backfill_sheet_registry, build_registry_index, live_smoke_test
from .sheets import GoogleSheetsStore

def _registry_index(config: dict):
    index=build_registry_index(config)
    if index is None:
        raise RuntimeError("Registry maintenance requires registry.mode dual or r2.")
    return index

def main() -> int:
    parser=argparse.ArgumentParser(prog="vsn-lead-engine")
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("validate")
    sub.add_parser("workbook-ready")
    recovery_parser=sub.add_parser("workbook-ready-recover")
    recovery_parser.add_argument("--attempts",type=int,default=None)
    recovery_parser.add_argument("--delay-seconds",type=float,default=None)
    run_parser=sub.add_parser("run")
    run_parser.add_argument("--dry-run",action="store_true")
    backfill_parser=sub.add_parser("registry-backfill")
    backfill_parser.add_argument("--dry-run",action="store_true")
    sub.add_parser("registry-stats")
    sub.add_parser("registry-check")
    sub.add_parser("registry-audit")
    sub.add_parser("registry-migrate")
    sub.add_parser("registry-smoke")
    args=parser.parse_args()
    config=load_config()
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
    print(json.dumps(run_until_quota(config,dry_run=args.dry_run),indent=2,default=str))
    return 0

if __name__=="__main__":
    sys.exit(main())
