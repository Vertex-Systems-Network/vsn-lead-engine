from __future__ import annotations
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from .dedupe import fingerprints,is_duplicate
from .normalize import normalize_phone
from .sheets import GoogleSheetsStore
from .sources import OverpassSource

def run_once(config: dict,dry_run: bool=False) -> dict:
    runtime=config["runtime"]
    if not runtime.get("enabled") and not dry_run:
        return {"status":"disabled","message":"Lead collection is disabled pending explicit user consent."}

    source_cfg=config["sources"]["overpass"]
    source=OverpassSource(
        timeout_seconds=int(source_cfg["timeout_seconds"]),
        min_interval_seconds=int(source_cfg["min_request_interval_seconds"])
    )

    if dry_run:
        counts={c:0 for c in config["categories"]}
        existing={k:set() for k in ["place_id","source_id","domain","phone_name","business_location","unique"]}
        workbook=None
    else:
        store=GoogleSheetsStore(config)
        workbook=store.ensure_lead_workbook()
        counts=store.category_counts(workbook["id"])
        existing=store.registry_fingerprints()

    target=int(runtime["daily_target_per_category"])
    pending=[c for c in config["categories"] if counts.get(c,0)<target]
    if not pending:
        return {"status":"complete","counts":counts}

    category=min(pending,key=lambda c:(counts.get(c,0)/target,counts.get(c,0),c))
    geography=config["geographies"][counts.get(category,0)%len(config["geographies"])]
    candidates=source.search(category,geography)

    accepted=[]
    rejections=defaultdict(int)
    local={k:set(v) for k,v in existing.items()}
    today=datetime.now(ZoneInfo(runtime["timezone"])).date().isoformat()

    for lead in candidates:
        phone=normalize_phone(lead.phone,lead.country)
        if not phone:
            rejections["missing_or_invalid_phone"]+=1
            continue
        lead.phone=phone
        lead.date_added=today
        fp=fingerprints(lead)
        if is_duplicate(fp,local):
            rejections["duplicate"]+=1
            continue
        accepted.append(lead)
        if fp.place_id: local["place_id"].add(fp.place_id)
        if fp.source_id: local["source_id"].add(fp.source_id)
        if fp.domain: local["domain"].add(fp.domain)
        if fp.phone_name: local["phone_name"].add(fp.phone_name)
        local["business_location"].add(fp.business_location)
        local["unique"].add(fp.unique)
        if len(accepted)>=int(runtime["batch_accept_limit"]):
            break

    result={
        "category":category,
        "geography":geography,
        "discovered":len(candidates),
        "accepted":len(accepted),
        "rejections":dict(rejections)
    }
    if dry_run:
        return {"status":"dry-run",**result}

    store.commit_leads(workbook,accepted)

    counts=store.category_counts(workbook["id"])
    store.update_overview(
        workbook["id"],
        counts,
        {
            "Free-Source Candidates":len(candidates),
            "Duplicate Rejections":int(rejections.get("duplicate",0)),
            "Missing-Phone Rejections":int(rejections.get("missing_or_invalid_phone",0)),
        }
    )
    return {"status":"ok",**result,"lead_workbook":workbook,"counts":counts}
