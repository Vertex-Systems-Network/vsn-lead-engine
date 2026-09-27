from __future__ import annotations
import argparse,json,sys
from .config import load_config
from .engine import run_until_quota
from .registry import SupabaseRegistryIndex, backfill_sheet_registry
from .sheets import GoogleSheetsStore

def main() -> int:
    parser=argparse.ArgumentParser(prog="vsn-lead-engine")
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("validate")
    run_parser=sub.add_parser("run")
    run_parser.add_argument("--dry-run",action="store_true")
    backfill_parser=sub.add_parser("registry-backfill")
    backfill_parser.add_argument("--dry-run",action="store_true")
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
    if args.command=="registry-backfill":
        store=GoogleSheetsStore(config)
        index=SupabaseRegistryIndex(config)
        try:
            result=backfill_sheet_registry(store,index,dry_run=args.dry_run)
        finally:
            index.close()
        print(json.dumps(result,indent=2,default=str))
        return 0
    print(json.dumps(run_until_quota(config,dry_run=args.dry_run),indent=2,default=str))
    return 0

if __name__=="__main__":
    sys.exit(main())
