from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import time
from zoneinfo import ZoneInfo

from .dedupe import fingerprints,is_duplicate
from .enrichment import build_contact_enricher
from .normalize import normalize_phone
from .scheduler import build_shard_plan, run_cursor
from .registry import build_registry_index, fingerprint_token, registry_mode
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


def _candidate_partition_geography(
    geography: dict,
    *,
    cursor: int,
    attempt: int,
    partition_count: int,
) -> dict:
    """Attach a deterministic rotating source cohort to one shard search."""
    count=max(1,int(partition_count))
    partition=(int(cursor)+max(0,int(attempt)-1)) % count
    return {
        **geography,
        "_candidate_partition_count":count,
        "_candidate_partition":partition,
    }


def _quality_summary(
    *,
    discovered: int,
    accepted: int,
    rejections: dict,
    enrichment: dict,
    attempts: list[dict],
) -> dict:
    discovered=max(0,int(discovered or 0))
    accepted=max(0,int(accepted or 0))
    duplicate_rejections=max(0,int(rejections.get("duplicate",0) or 0))
    missing_phone=max(0,int(rejections.get("missing_or_invalid_phone",0) or 0))
    enrichment_candidates=max(0,int(enrichment.get("candidates",0) or 0))
    live_recovered=max(0,int(enrichment.get("live_phone_recovered",0) or 0))
    common_recovered=max(0,int(enrichment.get("common_crawl_phone_recovered",0) or 0))
    phones_recovered=live_recovered+common_recovered
    partitions={
        (
            str(source_attempt.get("source","")),
            int(source_attempt["candidate_partition"]),
        )
        for attempt in attempts or []
        for source_attempt in attempt.get("sources",[]) or []
        if source_attempt.get("candidate_partition") is not None
    }
    return {
        "discovered":discovered,
        "accepted":accepted,
        "acceptance_rate_pct":round((accepted/discovered)*100,2) if discovered else 0.0,
        "duplicate_rejections":duplicate_rejections,
        "missing_phone_rejections":missing_phone,
        "enrichment_candidates":enrichment_candidates,
        "phones_recovered":phones_recovered,
        "official_site_phone_recoveries":live_recovered,
        "common_crawl_phone_recoveries":common_recovered,
        "phone_recovery_rate_pct":(
            round((phones_recovered/enrichment_candidates)*100,2)
            if enrichment_candidates else 0.0
        ),
        "common_crawl_attempts":max(
            0,int(enrichment.get("common_crawl_attempted",0) or 0)
        ),
        "enrichment_budget_skips":max(
            0,int(enrichment.get("skipped_budget",0) or 0)
        ),
        "enrichment_errors":max(0,int(enrichment.get("errors",0) or 0)),
        "partitions_visited":len(partitions),
    }


def run_once(
    config: dict,
    dry_run: bool=False,
    *,
    run_date: str | None = None,
    sources=None,
    store: GoogleSheetsStore | None = None,
    registry_index=None,
    enricher=None,
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

    mode=registry_mode(config)
    registry_shadow_errors=0
    if dry_run:
        counts={c:0 for c in config["categories"]}
        country_counts={country:0 for country in countries}
        existing=_empty_fingerprints()
        workbook=None
        recovery={}
    else:
        store=store or GoogleSheetsStore(config, run_date=run_date)
        registry_index=registry_index or build_registry_index(config)
        workbook=store.ensure_lead_workbook()
        if mode=="r2":
            if registry_index is None:
                raise RuntimeError("R2 Registry mode requires configured R2 credentials.")
            recovery={"r2":registry_index.reconcile_pending(store)}
            existing=_empty_fingerprints()
        else:
            recovery={"sheets":store.reconcile_pending_registry()}
            existing=store.registry_fingerprints()
            if mode=="dual" and registry_index is not None:
                try:
                    recovery["r2"]=registry_index.reconcile_pending(store)
                except Exception as exc:
                    registry_shadow_errors+=1
                    recovery["r2_error"]=f"{type(exc).__name__}: {exc}"
        counts=store.category_counts(workbook["id"])
        country_counts=store.daily_country_counts(workbook["id"])

    target=int(runtime["daily_target_per_category"])
    cursor=run_cursor()+int(cursor_offset)
    max_attempts=int(runtime.get("max_shard_attempts",12))
    batch_limit=int(runtime.get("batch_accept_limit",1000))
    per_shard_limit=int(runtime.get("candidate_limit_per_shard",500))
    source_retry_attempts=int(runtime.get("source_retry_attempts",3))
    source_retry_backoff_seconds=float(runtime.get("source_retry_backoff_seconds",2))
    candidate_partition_count=max(1,int(runtime.get("candidate_partition_count",8)))
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
    enrichment_totals=defaultdict(int)
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

            search_geography=_candidate_partition_geography(
                geography,
                cursor=cursor,
                attempt=shard["attempt"],
                partition_count=candidate_partition_count,
            )
            candidates,source_error,retries=_search_with_retry(
                source,
                category,
                search_geography,
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

            # Cheap in-process duplicate checks happen before any website fetch.
            # Permanent R2 collision checks happen after enrichment so a recovered
            # phone participates in the final exact fingerprint decision.
            enrichment_candidates=[]
            for lead in candidates:
                pre_fp=fingerprints(lead)
                if is_duplicate(pre_fp,local):
                    rejections["duplicate"]+=1
                    continue
                enrichment_candidates.append(lead)

            if enricher is not None and enrichment_candidates:
                enrichment_stats=enricher.enrich(enrichment_candidates)
                for key,value in enrichment_stats.items():
                    enrichment_totals[key]+=int(value or 0)

            remote_collisions=set()
            if mode=="r2" and enrichment_candidates:
                remote_collisions=registry_index.collision_keys(enrichment_candidates)

            for lead in enrichment_candidates:
                phone=normalize_phone(lead.phone,lead.country)
                if not phone:
                    rejections["missing_or_invalid_phone"]+=1
                    continue
                lead.phone=phone
                lead.date_added=today
                fp=fingerprints(lead)
                remote_unique_token=fingerprint_token("u",fp.unique)
                if is_duplicate(fp,local) or remote_unique_token in remote_collisions:
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
                "candidate_partition":search_geography["_candidate_partition"],
                "candidate_partition_count":search_geography["_candidate_partition_count"],
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
        "candidate_partition_count":candidate_partition_count,
        "registry_mode":mode,
        "registry_shadow_errors":registry_shadow_errors,
        "run_date":run_date,
        "discovered":total_discovered,
        "accepted":accepted_total,
        "accepted_by_category":{k:len(v) for k,v in accepted_by_category.items()},
        "accepted_by_country":dict(accepted_by_country),
        "country_counts_before":country_counts,
        "rejections":dict(rejections),
        "enrichment":dict(enrichment_totals),
        "attempts":attempts,
    }
    result["quality"]=_quality_summary(
        discovered=total_discovered,
        accepted=accepted_total,
        rejections=dict(rejections),
        enrichment=dict(enrichment_totals),
        attempts=attempts,
    )
    if dry_run:
        return {"status":"dry-run",**result}
    result["pending_recovery"]=recovery

    committed_by_category=defaultdict(list)
    for category in config["categories"]:
        leads=accepted_by_category.get(category,[])
        if not leads:
            continue

        if mode=="r2":
            reserved=registry_index.reserve_pending(leads,workbook)
            committed=[
                lead for lead in leads
                if fingerprint_token("u",fingerprints(lead).unique) in reserved
            ]
            conflicts=len(leads)-len(committed)
            if conflicts:
                rejections["duplicate"]+=conflicts
            if committed:
                keys={
                    fingerprint_token("u",fingerprints(lead).unique)
                    for lead in committed
                }
                try:
                    store.append_daily_leads(workbook,committed)
                except Exception:
                    registry_index.mark_retryable(keys)
                    raise
                registry_index.activate(keys)
                committed_by_category[category].extend(committed)
        else:
            store.commit_leads(workbook,leads)
            committed_by_category[category].extend(leads)
            if mode=="dual" and registry_index is not None:
                try:
                    shadow=registry_index.shadow_active(leads,workbook)
                    registry_shadow_errors+=int(shadow.get("conflicts",0) or 0)
                except Exception:
                    registry_shadow_errors+=1

    if mode=="r2":
        committed_total=sum(len(items) for items in committed_by_category.values())
        result["accepted"]=committed_total
        result["accepted_by_category"]={
            category:len(items) for category,items in committed_by_category.items()
        }
        committed_country=defaultdict(int)
        for items in committed_by_category.values():
            for lead in items:
                committed_country[lead.country]+=1
        result["accepted_by_country"]=dict(committed_country)
        result["rejections"]=dict(rejections)
    result["registry_shadow_errors"]=registry_shadow_errors
    result["quality"]=_quality_summary(
        discovered=total_discovered,
        accepted=int(result.get("accepted",0) or 0),
        rejections=dict(rejections),
        enrichment=dict(enrichment_totals),
        attempts=attempts,
    )

    counts=store.category_counts(workbook["id"])
    country_counts_after=store.daily_country_counts(workbook["id"])
    store.set_overview_metrics(
        workbook["id"],
        {
            "United States Leads Today":country_counts_after.get("United States",0),
            "Canada Leads Today":country_counts_after.get("Canada",0),
            "Last Acceptance Rate %":result["quality"]["acceptance_rate_pct"],
            "Last Phone Recovery Rate %":result["quality"]["phone_recovery_rate_pct"],
            "Last Partitions Visited":result["quality"]["partitions_visited"],
        }
    )
    store.update_overview(
        workbook["id"],
        counts,
        {
            "Accepted Leads":int(result.get("accepted",0) or 0),
            "Free-Source Candidates":total_discovered,
            "Duplicate Rejections":int(rejections.get("duplicate",0)),
            "Missing-Phone Rejections":int(rejections.get("missing_or_invalid_phone",0)),
            "Shard Attempts":len(attempts),
            "Zero-Result Shards":zero_result_shards,
            "Source Errors":source_errors,
            "Enrichment Candidates":int(enrichment_totals.get("candidates",0) or 0),
            "Phones Recovered":result["quality"]["phones_recovered"],
            "Official-Site Phone Recoveries":int(
                enrichment_totals.get("live_phone_recovered",0) or 0
            ),
            "Common-Crawl Phone Recoveries":int(
                enrichment_totals.get("common_crawl_phone_recovered",0) or 0
            ),
            "Common Crawl Attempts":int(
                enrichment_totals.get("common_crawl_attempted",0) or 0
            ),
            "Enrichment Budget Skips":int(
                enrichment_totals.get("skipped_budget",0) or 0
            ),
            "Enrichment Errors":int(enrichment_totals.get("errors",0) or 0),
            "Zero-Progress Cycles":1 if int(result.get("accepted",0) or 0)<=0 else 0,
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
    max_zero_progress_cycles=max(
        1,
        min(
            max_cycles,
            int(runtime.get("max_zero_progress_cycles", max_cycles)),
        ),
    )
    target=int(runtime["daily_target_per_category"])
    sources=build_sources(config)
    if not sources:
        return {"status":"no-sources","message":"No compliant free discovery source is enabled."}
    store=GoogleSheetsStore(config, run_date=run_date)
    registry_index=build_registry_index(config)
    enricher=build_contact_enricher(config)

    cycles=[]
    accepted_total=0
    final_counts={}
    final_country_counts={}
    final_status="ok"
    zero_progress_streak=0

    try:
        for cycle_index in range(max_cycles):
            result=run_once(
                config,
                dry_run=False,
                run_date=run_date,
                sources=sources,
                store=store,
                registry_index=registry_index,
                enricher=enricher,
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
                zero_progress_streak += 1
                if zero_progress_streak >= max_zero_progress_cycles:
                    break
            else:
                zero_progress_streak = 0
    finally:
        _close_sources(sources)
        if registry_index is not None:
            close=getattr(registry_index,"close",None)
            if callable(close):
                close()
        if enricher is not None:
            close=getattr(enricher,"close",None)
            if callable(close):
                close()

    return {
        "status": final_status,
        "run_date": run_date,
        "cycles_executed": len(cycles),
        "max_cycles_per_run": max_cycles,
        "max_zero_progress_cycles": max_zero_progress_cycles,
        "zero_progress_streak": zero_progress_streak,
        "accepted": accepted_total,
        "counts": final_counts,
        "country_counts": final_country_counts,
        "cycles": cycles,
    }
