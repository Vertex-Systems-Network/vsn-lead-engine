from __future__ import annotations
import argparse,json,sys
from .config import load_config
from .engine import run_once

def main() -> int:
    parser=argparse.ArgumentParser(prog="vsn-lead-engine")
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("validate")
    run_parser=sub.add_parser("run")
    run_parser.add_argument("--dry-run",action="store_true")
    args=parser.parse_args()
    config=load_config()
    if args.command=="validate":
        print(json.dumps({"status":"valid","mode":config["runtime"]["mode"],"enabled":config["runtime"]["enabled"],"categories":len(config["categories"]),"daily_target_total":len(config["categories"])*int(config["runtime"]["daily_target_per_category"])},indent=2))
        return 0
    print(json.dumps(run_once(config,dry_run=args.dry_run),indent=2,default=str))
    return 0

if __name__=="__main__":
    sys.exit(main())
