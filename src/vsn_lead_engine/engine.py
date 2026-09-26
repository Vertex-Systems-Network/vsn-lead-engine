from __future__ import annotations
from collections import defaultdict
from .dedupe import fingerprints,is_duplicate
from .normalize import normalize_phone
from .sheets import GoogleSheetsStore
from .sources import OverpassSource

def run_once(config: dict,dry_run: bool=False) -> dict:
    runtime=config["runtime"]
    if not runtime.get("enabled") and not dry_run:
        return {"status":"disabled","message":"Lead collection is disabled pending explicit user consent."}
    source_cfg=config["sources"]["overpass"]
    source=OverpassSource(timeout_seconds=int(source_cfg["timeout_seconds"]),min_interval_seconds=int(source_cfg["min_request_interval_seconds"]))
    if dry_run:
        counts={c:0 for c in config["categories"]}
        existing={k:set() for k in ["source_id","domain","phone_name","business_location","unique"]}
        daily=None
    else:
        store=GoogleSheetsStore(config)
        daily=store.ensure_daily_sheet()
        counts=store.category_counts(daily["id"])
        existing=store.registry_fingerprints()
    target=int(runtime["daily_target_per_category"])
    pending=[c for c in config["categories"] if counts.get(c,0)<target]
    if not pending: return {"status":"complete","counts":counts}
    category=min(pending,key=lambda c:(counts.get(c,0)/target,counts.get(c,0),c))
    geography=config["geographies"][counts.get(category,0)%len(config["geographies"])]
    candidates=source.search(category,geography)
    accepted=[]; rejections=defaultdict(int); local={k:set(v) for k,v in existing.items()}
    for lead in candidates:
        phone=normalize_phone(lead.phone,lead.country)
        if not phone:
            rejections["missing_or_invalid_phone"]+=1; continue
        lead.phone=phone
        fp=fingerprints(lead)
        if is_duplicate(fp,local):
            rejections["duplicate"]+=1; continue
        accepted.append(lead)
        local["source_id"].add(fp.source_id)
        if fp.domain: local["domain"].add(fp.domain)
        if fp.phone_name: local["phone_name"].add(fp.phone_name)
        local["business_location"].add(fp.business_location)
        local["unique"].add(fp.unique)
        if len(accepted)>=int(runtime["batch_accept_limit"]): break
    if dry_run:
        return {"status":"dry-run","category":category,"geography":geography,"discovered":len(candidates),"accepted":len(accepted),"rejections":dict(rejections)}
    for lead in accepted: store.commit_lead(daily,lead)
    return {"status":"ok","category":category,"geography":geography,"discovered":len(candidates),"accepted":len(accepted),"rejections":dict(rejections),"daily_sheet":daily}
