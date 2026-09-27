from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import time
from zoneinfo import ZoneInfo

from .dedupe import fingerprints,is_duplicate
from .normalize import normalize_phone
from .scheduler import build_shard_plan, run_cursor
from .sheets import GoogleSheetsStore
from .sources import build_sources


def _empty_fingerprints() -> dict[str, set[str]]:
    return {
        k:set()
        for k in ["place_id","source_id","domain","phone_name","business_location","unique"]
    }


def _search_with_retry(source, category: str, geography: dict, *, limit: int, attempts: int, backoff_seconds: float):
    last_error = ""
    retry_count = 0
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return source.search(category, geography, limit=limit), "", retry_count
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt >= max(1, attempts):
                break
            retry_count += 1
            if backoff_seconds > 0:
                time.sleep(backoff_seconds * (2 ** (attempt - 1)))
    return [], last_error, retry_count


def _close_sources(sources) -> None:
    for source in sources:
        close = getattr(source, "close", None)
        if callable(close):
            close()


def run_once(
    config: dict,
    dry_run: bool=False,
    *,
    run_date: str | None = None,
    sources=None,
    store: GoogleSheetsStore | None = None,
    cursor_offset: int = 0,
) -> dict:
    runtime=config["runtime"]
    run_date=run_date or datetime.now(ZoneInfo(runtime["timezone"])).date().isoformat()
    if not runtime.get("enabled") and not dry_run:
        return {"status":"disabled","message":"Lead collection is disabled pending explicit user consent."}

    sources=sources or build_sources(config)
    if not sources:
        return {"status":"no-sources","message":"No compliant free discovery source is enabled."}

    countries=list(dict.fromkeys(
        str(geo.get("country","")).strip()
        for geo in config["geographies"]
        if str(geo.get("country","")).strip()
    ))

    if dry_run:
        counts={c:0 for c in config["categories"]}
        country_counts={country:0 for country in countries}
        existing=_empty_fingerprints()
        workbook=None
    else:
        store=store or GoogleSheetsStore(config, run_date=run_date)
        workbook=store.ensure_lead_workbook()
        recovery=store.reconcile_pending_registry()
        counts=store.category_counts(workbook["id"])
        country_counts=store.daily_country_counts(workbook["id"])
        existing=store.registry_fingerprints()

    target=int(runtime["daily_target_per_category"])
    cursor=run_cursor()+int(cursor_offset)
    max_attempts=int(runtime.get("max_shard_attempts",12))
    batch_limit=int(runtime.get("batch_accept_limit",1000))
    per_shard_limit=int(runtime.get("candidate_limit_per_shard",500))
    source_retry_attempts=int(runtime.get("source_retry_attempts",3))
    source_retry_backoff_seconds=float(runtime.get("source_retry_backoff_seconds",2))
    plan=build_shard_plan(
        config["categories"],
        config["geographies"],
        counts,
        target,
        cursor=cursor,
        max_attempts=max_attempts,
        country_counts=country_counts,
    )
    if not plan:
        return {"status":"complete","counts":counts,"cursor":cursor}

    local={k:set(v) for k,v in existing.items()}
    accepted_by_category=defaultdict(list)
    accepted_by_country=defaultdict(int)
    rejections=defaultdict(int)
    attempts=[]
    total_discovered=0
    source_errors=0
    source_retries=0
    zero_result_shards=0
    accepted_total=0
    today=run_date

    for shard in plan:
        if accepted_total >= batch_limit:
            break
        category=shard["category"]
        geography=shard["geography"]
        already_today=counts.get(category,0)+len(accepted_by_category[category])
        if already_today >= target:
            continue

        shard_discovered=0
        shard_accepted_before=accepted_total
        source_attempts=[]

        for source in sources:
            if accepted_total >= batch_limit:
                break
            remaining=min(
                per_shard_limit,
                batch_limit-accepted_total,
                target-(counts.get(category,0)+len(accepted_by_category[category])),
            )
            if remaining <= 0:
                break

            candidates,source_error,retries=_search_with_retry(
                source,
                category,
                geography,
                limit=remaining,
                attempts=source_retry_attempts,
                backoff_seconds=source_retry_backoff_seconds,
            )
            source_retries+=retries
            if source_error:
                source_errors+=1

            shard_discovered+=len(candidates)
            total_discovered+=len(candidates)
            accepted_from_source=0

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

                accepted_by_category[category].append(lead)
                accepted_by_country[lead.country]+=1
                accepted_total+=1
                accepted_from_source+=1

                if fp.place_id:
                    local["place_id"].add(fp.place_id)
                if fp.source_id:
                    local["source_id"].add(fp.source_id)
                if fp.domain:
                    local["domain"].add(fp.domain)
                if fp.phone_name:
                    local["phone_name"].add(fp.phone_name)
                local["business_location"].add(fp.business_location)
                local["unique"].add(fp.unique)

                if accepted_total>=batch_limit:
                    break
                if counts.get(category,0)+len(accepted_by_category[category])>=target:
                    break

            source_attempts.append({
                "source":source.name,
                "discovered":len(candidates),
                "accepted":accepted_from_source,
                "error":source_error,
            })

        if shard_discovered == 0:
            zero_result_shards+=1

        attempts.append({
            "attempt":shard["attempt"],
            "category":category,
            "geography":{
                "country":geography["country"],
                "region":geography["region"],
                "city":geography["city"],
            },
            "discovered":shard_discovered,
            "accepted":accepted_total-shard_accepted_before,
            "priority_weight":shard.get("priority_weight",1),
            "sources":source_attempts,
        })

    result={
        "cursor":cursor,
        "shard_attempts":len(attempts),
        "zero_result_shards":zero_result_shards,
        "source_errors":source_errors,
        "source_retries":source_retries,
        "run_date":run_date,
        "discovered":total_discovered,
        "accepted":accepted_total,
        "accepted_by_category":{k:len(v) for k,v in accepted_by_category.items()},
        "accepted_by_country":dict(accepted_by_country),
        "country_counts_before":country_counts,
        "rejections":dict(rejections),
        "attempts":attempts,
    }
    if dry_run:
        return {"status":"dry-run",**result}
    result["pending_recovery"]=recovery

    for category in config["categories"]:
        leads=accepted_by_category.get(category,[])
        if leads:
            store.commit_leads(workbook,leads)

    counts=store.category_counts(workbook["id"])
    country_counts_after=store.daily_country_counts(workbook["id"])
    store.set_overview_metrics(
        workbook["id"],
        {
            "United States Leads Today":country_counts_after.get("United States",0),
            "Canada Leads Today":country_counts_after.get("Canada",0),
        }
    )
    store.update_overview(
        workbook["id"],
        counts,
        {
            "Free-Source Candidates":total_discovered,
            "Duplicate Rejections":int(rejections.get("duplicate",0)),
            "Missing-Phone Rejections":int(rejections.get("missing_or_invalid_phone",0)),
            "Shard Attempts":len(attempts),
            "Zero-Result Shards":zero_result_shards,
            "Source Errors":source_errors,
        }
    )
    return {
        "status":"ok",
        **result,
        "lead_workbook":workbook,
        "counts":counts,
        "country_counts":country_counts_after,
    }



def run_until_quota(config: dict, dry_run: bool=False) -> dict:
    """Run multiple bounded collection cycles inside one process.

    Production cycles re-read live sheet/registry state each time, but reuse the
    same Google client objects and source instances. This reduces runner startup
    overhead while preserving quota/dedupe safety.
    """
    if dry_run:
        return run_once(config, dry_run=True)

    runtime=config["runtime"]
    run_date=datetime.now(ZoneInfo(runtime["timezone"])).date().isoformat()
    max_cycles=max(1, int(runtime.get("max_cycles_per_run", 3)))
    target=int(runtime["daily_target_per_category"])
    sources=build_sources(config)
    if not sources:
        return {"status":"no-sources","message":"No compliant free discovery source is enabled."}
    store=GoogleSheetsStore(config, run_date=run_date)

    cycles=[]
    accepted_total=0
    final_counts={}
    final_country_counts={}
    final_status="ok"

    try:
        for cycle_index in range(max_cycles):
            result=run_once(
                config,
                dry_run=False,
                run_date=run_date,
                sources=sources,
                store=store,
                cursor_offset=cycle_index,
            )
            cycles.append(result)
            accepted_total += int(result.get("accepted", 0) or 0)
            final_counts = result.get("counts", final_counts) or final_counts
            final_country_counts = result.get("country_counts", final_country_counts) or final_country_counts
            final_status = result.get("status", "ok")

            if final_status in {"complete","disabled","no-sources"}:
                break
            if final_counts and all(int(final_counts.get(category,0)) >= target for category in config["categories"]):
                final_status="complete"
                break
            if int(result.get("accepted",0) or 0) <= 0:
                break
    finally:
        _close_sources(sources)

    return {
        "status": final_status,
        "run_date": run_date,
        "cycles_executed": len(cycles),
        "max_cycles_per_run": max_cycles,
        "accepted": accepted_total,
        "counts": final_counts,
        "country_counts": final_country_counts,
        "cycles": cycles,
    }
