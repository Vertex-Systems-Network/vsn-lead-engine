from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import os
import time
from zoneinfo import ZoneInfo

from .dedupe import fingerprints,is_duplicate
from .enrichment import build_contact_enricher
from .health import DailyHealthLedgerStore, run_health_event
from .normalize import normalize_phone
from .progress import emit_progress
from .scheduler import build_shard_plan, run_cursor, yield_hint_key
from .registry import build_registry_index, fingerprint_token, registry_mode
from .sheets import GoogleSheetsStore
from .sources import build_sources
from .yield_state import DailyYieldStateStore, HistoricalYieldProfileStore


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
        except TimeoutError as exc:
            # A source-enforced wall-clock timeout is not retried in the same
            # shard. Rotated shards/cycles provide the next bounded attempt.
            last_error=f"{type(exc).__name__}: {exc}"
            break
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt >= max(1, attempts):
                break
            retry_count += 1
            if backoff_seconds > 0:
                time.sleep(backoff_seconds * (2 ** (attempt - 1)))
    return [], last_error, retry_count


def _deadline_is_near(
    deadline_monotonic: float | None,
    guard_seconds: float = 0,
) -> bool:
    if deadline_monotonic is None:
        return False
    return (
        time.monotonic() + max(0.0,float(guard_seconds))
        >= float(deadline_monotonic)
    )


def _close_sources(sources) -> None:
    for source in sources:
        close = getattr(source, "close", None)
        if callable(close):
            close()


def _source_contact_mix(candidates: list) -> tuple[int,int]:
    """Match P23 source selection semantics without validating/recovering phones."""
    source_phone=sum(
        1 for lead in candidates
        if bool(str(lead.phone or "").strip())
    )
    website_only=sum(
        1 for lead in candidates
        if (
            not str(lead.phone or "").strip()
            and bool(str(lead.website or "").strip())
        )
    )
    return source_phone,website_only


def _lead_pre_enrichment_quality(lead) -> tuple[int,int,int]:
    phone=bool(normalize_phone(lead.phone,lead.country))
    website=bool(str(lead.website or "").strip())
    contact_fields=[
        lead.email,
        lead.instagram,
        lead.facebook,
        lead.linkedin,
        lead.twitter,
        lead.tiktok,
        lead.contact_person,
        lead.source_url,
        lead.street_address,
    ]
    richness=sum(1 for value in contact_fields if str(value or "").strip())
    return int(phone),int(website),richness


def _dedupe_source_batch(candidates: list) -> tuple[list,int]:
    """Collapse exact same-response duplicates before any network enrichment."""
    if len(candidates) < 2:
        return list(candidates),0

    ranked=sorted(
        enumerate(candidates),
        key=lambda item: (
            *_lead_pre_enrichment_quality(item[1]),
            -item[0],
        ),
        reverse=True,
    )
    seen=_empty_fingerprints()
    kept_indices=set()
    duplicate_count=0

    for index,lead in ranked:
        fp=fingerprints(lead)
        if is_duplicate(fp,seen):
            duplicate_count+=1
            continue
        kept_indices.add(index)
        if fp.place_id:
            seen["place_id"].add(fp.place_id)
        if fp.source_id:
            seen["source_id"].add(fp.source_id)
        if fp.domain:
            seen["domain"].add(fp.domain)
        if fp.phone_name:
            seen["phone_name"].add(fp.phone_name)
        if fp.business_location:
            seen["business_location"].add(fp.business_location)
        if fp.unique:
            seen["unique"].add(fp.unique)

    return [
        lead
        for index,lead in enumerate(candidates)
        if index in kept_indices
    ],duplicate_count


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


def _update_yield_hints(
    yield_hints: dict[str,dict],
    attempts: list[dict],
) -> None:
    for attempt in attempts or []:
        category=str(attempt.get("category","")).strip()
        geography=attempt.get("geography") or {}
        if not category or not geography:
            continue
        key=yield_hint_key(category,geography)
        hint=yield_hints.setdefault(
            key,
            {"visits":0,"discovered":0,"accepted":0},
        )
        hint["visits"]=int(hint.get("visits",0) or 0)+1
        hint["discovered"]=int(hint.get("discovered",0) or 0)+max(
            0,int(attempt.get("discovered",0) or 0)
        )
        hint["accepted"]=int(hint.get("accepted",0) or 0)+max(
            0,int(attempt.get("accepted",0) or 0)
        )
        partition_mask=max(0,int(hint.get("partition_mask",0) or 0))
        for source in attempt.get("sources",[]) or []:
            try:
                partition=int(source.get("candidate_partition"))
            except (TypeError,ValueError,AttributeError):
                continue
            if 0 <= partition < 64:
                partition_mask |= 1 << partition
        if partition_mask:
            hint["partition_mask"]=partition_mask


def _yield_hint_summary(yield_hints: dict[str,dict]) -> dict:
    return {
        "markets_observed":len(yield_hints),
        "visits":sum(int(item.get("visits",0) or 0) for item in yield_hints.values()),
        "discovered":sum(int(item.get("discovered",0) or 0) for item in yield_hints.values()),
        "accepted":sum(int(item.get("accepted",0) or 0) for item in yield_hints.values()),
        "partitions_observed":sum(
            max(0,int(item.get("partition_mask",0) or 0)).bit_count()
            for item in yield_hints.values()
        ),
    }


def _merge_routing_hints(
    daily_hints: dict[str,dict],
    historical_hints: dict[str,dict],
    *,
    historical_weight: float,
) -> dict[str,dict]:
    """Blend weak historical priors with stronger same-day observations."""
    weight=max(0.0,min(1.0,float(historical_weight)))
    merged: dict[str,dict]={}

    for key,item in historical_hints.items():
        visits=max(0,int(item.get("visits",0) or 0))
        discovered=max(0,int(item.get("discovered",0) or 0))
        accepted=max(0,int(item.get("accepted",0) or 0))
        scaled={
            "visits":max(1,int(round(visits*weight))) if visits else 0,
            "discovered":max(0,int(round(discovered*weight))),
            "accepted":max(0,int(round(accepted*weight))),
        }
        scaled["accepted"]=min(scaled["accepted"],scaled["discovered"])
        if scaled["visits"] or scaled["discovered"] or scaled["accepted"]:
            merged[str(key)]=scaled

    for key,item in daily_hints.items():
        current=merged.setdefault(
            str(key),
            {"visits":0,"discovered":0,"accepted":0},
        )
        current["visits"]+=max(0,int(item.get("visits",0) or 0))
        current["discovered"]+=max(0,int(item.get("discovered",0) or 0))
        current["accepted"]+=max(0,int(item.get("accepted",0) or 0))
        current["accepted"]=min(current["accepted"],current["discovered"])

    return merged


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
    remote_prefilter_duplicates=max(
        0,int(rejections.get("remote_prefilter_duplicate",0) or 0)
    )
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
        "remote_prefilter_duplicates":remote_prefilter_duplicates,
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


def check_workbook_readiness(
    config: dict,
    *,
    run_date: str | None = None,
    store: GoogleSheetsStore | None = None,
) -> dict:
    """Resolve and self-heal the dated workbook before lead collection starts."""
    runtime=config["runtime"]
    run_date=run_date or datetime.now(
        ZoneInfo(runtime["timezone"])
    ).date().isoformat()
    store=store or GoogleSheetsStore(config,run_date=run_date)
    workbook=store.ensure_lead_workbook()
    counts=store.category_counts(workbook["id"])
    country_counts=store.daily_country_counts(workbook["id"])
    target=int(runtime["daily_target_per_category"])
    quota_complete=all(
        int(counts.get(category,0) or 0) >= target
        for category in config["categories"]
    )
    return {
        "status":"ready",
        "run_date":run_date,
        "workbook":{
            "id":workbook["id"],
            "name":workbook.get("name",""),
            "webViewLink":workbook.get("webViewLink",""),
            "created":bool(workbook.get("created",False)),
        },
        "counts":counts,
        "country_counts":country_counts,
        "quota_complete":quota_complete,
    }


def recover_workbook_readiness(
    config: dict,
    *,
    run_date: str | None = None,
    attempts: int | None = None,
    delay_seconds: float | None = None,
    sleep_fn=time.sleep,
    check_fn=check_workbook_readiness,
) -> dict:
    """Retry dated-workbook readiness and return incident telemetry on failure."""
    runtime=config["runtime"]
    run_date=run_date or datetime.now(
        ZoneInfo(runtime["timezone"])
    ).date().isoformat()
    attempts=max(
        1,
        min(
            5,
            int(
                attempts
                if attempts is not None
                else runtime.get("workbook_readiness_attempts",3)
            ),
        ),
    )
    delay_seconds=max(
        0.0,
        min(
            180.0,
            float(
                delay_seconds
                if delay_seconds is not None
                else runtime.get("workbook_readiness_retry_delay_seconds",60)
            ),
        ),
    )

    failures=[]
    for attempt_number in range(1,attempts+1):
        started_at=datetime.now(ZoneInfo(runtime["timezone"])).isoformat()
        try:
            result=check_fn(config,run_date=run_date)
            result={
                **result,
                "status":"ready" if attempt_number==1 else "recovered",
                "attempts_used":attempt_number,
                "attempts_configured":attempts,
                "retry_delay_seconds":delay_seconds,
                "failures":failures,
            }
            return result
        except Exception as exc:
            failures.append({
                "attempt":attempt_number,
                "timestamp":started_at,
                "error_type":type(exc).__name__,
                "message":str(exc),
            })
            if attempt_number < attempts and delay_seconds > 0:
                sleep_fn(delay_seconds)

    return {
        "status":"incident",
        "run_date":run_date,
        "attempts_used":attempts,
        "attempts_configured":attempts,
        "retry_delay_seconds":delay_seconds,
        "failures":failures,
        "last_error":failures[-1] if failures else {},
        "quota_complete":False,
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
    yield_hints: dict[str,dict] | None = None,
    daily_yield_hints: dict[str,dict] | None = None,
    cursor_offset: int = 0,
    deadline_monotonic: float | None = None,
) -> dict:
    runtime=config["runtime"]
    run_date=run_date or datetime.now(ZoneInfo(runtime["timezone"])).date().isoformat()
    cycle_started_monotonic=time.monotonic()
    progress_enabled=bool(runtime.get("progress_telemetry_enabled",True))
    emit_progress(
        "cycle_enter",
        enabled=progress_enabled,
        run_date=run_date,
        dry_run=bool(dry_run),
        cursor_offset=int(cursor_offset),
    )
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
    emit_progress(
        "cycle_ready",
        enabled=progress_enabled,
        started_monotonic=cycle_started_monotonic,
        run_date=run_date,
        registry_mode=mode,
        total_today=sum(int(value or 0) for value in counts.values()),
        target_per_category=target,
        countries=len(countries),
    )
    cursor=run_cursor()+int(cursor_offset)
    max_attempts=int(runtime.get("max_shard_attempts",12))
    batch_limit=int(runtime.get("batch_accept_limit",1000))
    per_shard_limit=int(runtime.get("candidate_limit_per_shard",500))
    source_retry_attempts=int(runtime.get("source_retry_attempts",3))
    source_retry_backoff_seconds=float(runtime.get("source_retry_backoff_seconds",2))
    candidate_partition_count=max(1,int(runtime.get("candidate_partition_count",8)))
    adaptive_yield_routing=bool(runtime.get("adaptive_yield_routing",True))
    remote_prefilter_enabled=bool(
        runtime.get("r2_pre_enrichment_prefilter_enabled",True)
    )
    source_batch_dedupe_enabled=bool(
        runtime.get("source_batch_dedupe_enabled",True)
    )
    adaptive_yield_exploration_bonus=float(
        runtime.get("adaptive_yield_exploration_bonus",0.15)
    )
    adaptive_cooldown_enabled=bool(
        runtime.get("adaptive_zero_yield_cooldown_enabled",True)
    )
    adaptive_cooldown_min_visits=int(
        runtime.get("adaptive_zero_yield_cooldown_min_visits",2)
    )
    adaptive_cooldown_min_discovered=int(
        runtime.get("adaptive_zero_yield_cooldown_min_discovered",100)
    )
    adaptive_cooldown_min_partitions=int(
        runtime.get("adaptive_zero_yield_cooldown_min_partitions",4)
    )
    event_deadline_guard_seconds=float(
        runtime.get("event_deadline_guard_seconds",60)
    )
    plan=build_shard_plan(
        config["categories"],
        config["geographies"],
        counts,
        target,
        cursor=cursor,
        max_attempts=max_attempts,
        country_counts=country_counts,
        yield_hints=yield_hints,
        daily_yield_hints=daily_yield_hints,
        adaptive_enabled=adaptive_yield_routing,
        exploration_bonus=adaptive_yield_exploration_bonus,
        cooldown_enabled=adaptive_cooldown_enabled,
        cooldown_min_visits=adaptive_cooldown_min_visits,
        cooldown_min_discovered=adaptive_cooldown_min_discovered,
        cooldown_min_partitions=adaptive_cooldown_min_partitions,
    )
    if not plan:
        return {"status":"complete","counts":counts,"cursor":cursor}

    local={k:set(v) for k,v in existing.items()}
    accepted_by_category=defaultdict(list)
    accepted_by_country=defaultdict(int)
    rejections=defaultdict(int)
    attempts=[]
    total_discovered=0
    source_phone_candidates=0
    website_only_candidates=0
    source_errors=0
    source_retries=0
    zero_result_shards=0
    enrichment_totals=defaultdict(int)
    accepted_total=0
    today=run_date
    event_budget_exhausted=False

    for shard in plan:
        if _deadline_is_near(
            deadline_monotonic,
            event_deadline_guard_seconds,
        ):
            event_budget_exhausted=True
            break
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
            if _deadline_is_near(
                deadline_monotonic,
                event_deadline_guard_seconds,
            ):
                event_budget_exhausted=True
                break
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
            source_started_monotonic=time.monotonic()
            emit_progress(
                "source_search_start",
                enabled=progress_enabled,
                run_date=run_date,
                category=category,
                country=geography["country"],
                region=geography["region"],
                city=geography["city"],
                source=source.name,
                shard_attempt=int(shard["attempt"]),
                candidate_partition=int(
                    search_geography["_candidate_partition"]
                ),
                candidate_partition_count=int(
                    search_geography["_candidate_partition_count"]
                ),
                requested_limit=int(remaining),
            )
            candidates,source_error,retries=_search_with_retry(
                source,
                category,
                search_geography,
                limit=remaining,
                attempts=source_retry_attempts,
                backoff_seconds=source_retry_backoff_seconds,
            )
            emit_progress(
                "source_search_end",
                enabled=progress_enabled,
                started_monotonic=source_started_monotonic,
                run_date=run_date,
                category=category,
                country=geography["country"],
                city=geography["city"],
                source=source.name,
                shard_attempt=int(shard["attempt"]),
                candidate_partition=int(
                    search_geography["_candidate_partition"]
                ),
                discovered=len(candidates),
                retries=int(retries),
                error=bool(source_error),
            )
            source_retries+=retries
            if source_error:
                source_errors+=1

            shard_discovered+=len(candidates)
            total_discovered+=len(candidates)
            source_phone_count,website_only_count=_source_contact_mix(
                candidates
            )
            source_phone_candidates+=source_phone_count
            website_only_candidates+=website_only_count
            accepted_from_source=0

            # Cheap local and same-response duplicate checks happen before any
            # website fetch. P17 may also read-filter stable R2 fingerprints before
            # enrichment, while the final R2 collision check still runs afterward
            # so any recovered phone participates in the exact decision.
            enrichment_candidates=[]
            for lead in candidates:
                pre_fp=fingerprints(lead)
                if is_duplicate(pre_fp,local):
                    rejections["duplicate"]+=1
                    continue
                enrichment_candidates.append(lead)

            source_batch_duplicates=0
            if source_batch_dedupe_enabled:
                (
                    enrichment_candidates,
                    source_batch_duplicates,
                )=_dedupe_source_batch(enrichment_candidates)
            if source_batch_duplicates:
                rejections["duplicate"]+=source_batch_duplicates
                rejections["source_batch_duplicate"]+=source_batch_duplicates

            remote_prefilter_candidates=0
            remote_prefilter_duplicates=0
            if (
                remote_prefilter_enabled
                and mode=="r2"
                and enricher is not None
                and enrichment_candidates
            ):
                prefilter_targets=[
                    lead for lead in enrichment_candidates
                    if (
                        not normalize_phone(lead.phone,lead.country)
                        and bool(str(lead.website or "").strip())
                    )
                ]
                remote_prefilter_candidates=len(prefilter_targets)
                if prefilter_targets:
                    prefilter_started_monotonic=time.monotonic()
                    emit_progress(
                        "remote_prefilter_start",
                        enabled=progress_enabled,
                        run_date=run_date,
                        category=category,
                        country=geography["country"],
                        city=geography["city"],
                        candidates=len(prefilter_targets),
                    )
                    prefilter_collisions=registry_index.collision_keys(
                        prefilter_targets
                    )
                    emit_progress(
                        "remote_prefilter_end",
                        enabled=progress_enabled,
                        started_monotonic=prefilter_started_monotonic,
                        run_date=run_date,
                        category=category,
                        candidates=len(prefilter_targets),
                        collisions=len(prefilter_collisions),
                    )
                    if prefilter_collisions:
                        survivors=[]
                        for lead in enrichment_candidates:
                            token=fingerprint_token(
                                "u",
                                fingerprints(lead).unique,
                            )
                            if token and token in prefilter_collisions:
                                rejections["duplicate"]+=1
                                rejections["remote_prefilter_duplicate"]+=1
                                remote_prefilter_duplicates+=1
                                continue
                            survivors.append(lead)
                        enrichment_candidates=survivors

            if enricher is not None and enrichment_candidates:
                enrichment_started_monotonic=time.monotonic()
                emit_progress(
                    "enrichment_start",
                    enabled=progress_enabled,
                    run_date=run_date,
                    category=category,
                    country=geography["country"],
                    city=geography["city"],
                    candidates=len(enrichment_candidates),
                )
                enrichment_stats=enricher.enrich(enrichment_candidates)
                emit_progress(
                    "enrichment_end",
                    enabled=progress_enabled,
                    started_monotonic=enrichment_started_monotonic,
                    run_date=run_date,
                    category=category,
                    candidates=len(enrichment_candidates),
                    live_phone_recovered=int(
                        enrichment_stats.get("live_phone_recovered",0) or 0
                    ),
                    common_crawl_phone_recovered=int(
                        enrichment_stats.get("common_crawl_phone_recovered",0)
                        or 0
                    ),
                    errors=int(enrichment_stats.get("errors",0) or 0),
                )
                for key,value in enrichment_stats.items():
                    enrichment_totals[key]+=int(value or 0)

            remote_collisions=set()
            if mode=="r2" and enrichment_candidates:
                collision_started_monotonic=time.monotonic()
                emit_progress(
                    "registry_collision_start",
                    enabled=progress_enabled,
                    run_date=run_date,
                    category=category,
                    candidates=len(enrichment_candidates),
                )
                remote_collisions=registry_index.collision_keys(enrichment_candidates)
                emit_progress(
                    "registry_collision_end",
                    enabled=progress_enabled,
                    started_monotonic=collision_started_monotonic,
                    run_date=run_date,
                    category=category,
                    candidates=len(enrichment_candidates),
                    collisions=len(remote_collisions),
                )

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
                "source_phone_candidates":source_phone_count,
                "website_only_candidates":website_only_count,
                "accepted":accepted_from_source,
                "candidate_partition":search_geography["_candidate_partition"],
                "candidate_partition_count":search_geography["_candidate_partition_count"],
                "source_batch_duplicates":source_batch_duplicates,
                "remote_prefilter_candidates":remote_prefilter_candidates,
                "remote_prefilter_duplicates":remote_prefilter_duplicates,
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
            "adaptive_yield_score":shard.get("adaptive_yield_score"),
            "adaptive_cooldown":bool(shard.get("adaptive_cooldown",False)),
            "adaptive_cooldown_deferred_count":int(
                shard.get("adaptive_cooldown_deferred_count",0) or 0
            ),
            "sources":source_attempts,
        })

        if event_budget_exhausted:
            break

    registry_read_cache={}
    cache_stats=getattr(registry_index,"cache_stats",None)
    if callable(cache_stats):
        try:
            registry_read_cache=dict(cache_stats())
        except Exception:
            registry_read_cache={}

    result={
        "cursor":cursor,
        "shard_attempts":len(attempts),
        "categories_attempted":len({
            str(item.get("category",""))
            for item in attempts
            if str(item.get("category",""))
        }),
        "zero_result_shards":zero_result_shards,
        "source_errors":source_errors,
        "source_retries":source_retries,
        "event_budget_exhausted":event_budget_exhausted,
        "candidate_partition_count":candidate_partition_count,
        "source_batch_dedupe":source_batch_dedupe_enabled,
        "r2_pre_enrichment_prefilter":remote_prefilter_enabled,
        "adaptive_yield_routing":adaptive_yield_routing,
        "adaptive_yield_hints_used":len(yield_hints or {}),
        "adaptive_zero_yield_cooldown":adaptive_cooldown_enabled,
        "adaptive_cooldown_routes_deferred":max(
            [
                int(item.get("adaptive_cooldown_deferred_count",0) or 0)
                for item in attempts
            ]
            or [0]
        ),
        "registry_mode":mode,
        "registry_shadow_errors":registry_shadow_errors,
        "registry_read_cache":registry_read_cache,
        "run_date":run_date,
        "discovered":total_discovered,
        "source_phone_candidates":source_phone_candidates,
        "website_only_candidates":website_only_candidates,
        "accepted":accepted_total,
        "accepted_by_category":{k:len(v) for k,v in accepted_by_category.items()},
        "accepted_by_country":dict(accepted_by_country),
        "country_counts_before":country_counts,
        "rejections":dict(rejections),
        "source_batch_duplicates":int(
            rejections.get("source_batch_duplicate",0) or 0
        ),
        "remote_prefilter_duplicates":int(
            rejections.get("remote_prefilter_duplicate",0) or 0
        ),
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
        emit_progress(
            "cycle_exit",
            enabled=progress_enabled,
            started_monotonic=cycle_started_monotonic,
            run_date=run_date,
            status="dry-run",
            accepted=int(result.get("accepted",0) or 0),
            discovered=int(result.get("discovered",0) or 0),
            shard_attempts=len(attempts),
            event_budget_exhausted=bool(event_budget_exhausted),
        )
        return {"status":"dry-run",**result}
    result["pending_recovery"]=recovery

    committed_by_category=defaultdict(list)
    for category in config["categories"]:
        leads=accepted_by_category.get(category,[])
        if not leads:
            continue

        commit_started_monotonic=time.monotonic()
        emit_progress(
            "category_commit_start",
            enabled=progress_enabled,
            run_date=run_date,
            category=category,
            candidates=len(leads),
            registry_mode=mode,
        )

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

        emit_progress(
            "category_commit_end",
            enabled=progress_enabled,
            started_monotonic=commit_started_monotonic,
            run_date=run_date,
            category=category,
            committed=len(committed_by_category.get(category,[])),
            registry_mode=mode,
        )

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
            "Source Phone Candidates":source_phone_candidates,
            "Website-Only Candidates":website_only_candidates,
            "Duplicate Rejections":int(rejections.get("duplicate",0)),
            "Source-Batch Duplicates":int(
                rejections.get("source_batch_duplicate",0) or 0
            ),
            "Remote Prefilter Duplicates":int(
                rejections.get("remote_prefilter_duplicate",0) or 0
            ),
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
    emit_progress(
        "cycle_exit",
        enabled=progress_enabled,
        started_monotonic=cycle_started_monotonic,
        run_date=run_date,
        status="ok",
        accepted=int(result.get("accepted",0) or 0),
        discovered=int(result.get("discovered",0) or 0),
        shard_attempts=len(attempts),
        event_budget_exhausted=bool(event_budget_exhausted),
    )
    return {
        "status":"ok",
        **result,
        "lead_workbook":workbook,
        "counts":counts,
        "country_counts":country_counts_after,
    }



def run_until_quota(
    config: dict,
    dry_run: bool=False,
    *,
    origin: str | None = None,
    schedule: dict | None = None,
) -> dict:
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
    event_wall_time_seconds=float(
        runtime.get("event_wall_time_seconds",1500)
    )
    event_started_monotonic=time.monotonic()
    event_deadline_monotonic=(
        event_started_monotonic + event_wall_time_seconds
    )
    progress_enabled=bool(runtime.get("progress_telemetry_enabled",True))
    emit_progress(
        "event_start",
        enabled=progress_enabled,
        run_date=run_date,
        origin=str(
            origin or os.getenv("VSN_RUN_ORIGIN","manual") or "manual"
        ).strip(),
        max_cycles=max_cycles,
        event_wall_time_seconds=event_wall_time_seconds,
    )
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
    yield_hints={}
    yield_state_store=None
    yield_state_telemetry={
        "enabled":False,
        "loaded":False,
        "saved":False,
        "load_error":"",
        "save_error":"",
    }
    yield_state_dirty=False
    historical_hints={}
    history_store=None
    history_telemetry={
        "enabled":False,
        "loaded":False,
        "saved":False,
        "load_error":"",
        "save_error":"",
    }
    health_store=None
    health_telemetry={
        "enabled":False,
        "recorded":False,
        "error":"",
        "origin":str(
            origin or os.getenv("VSN_RUN_ORIGIN","manual") or "manual"
        ).strip(),
    }
    final_result={}

    if bool(runtime.get("health_ledger_enabled",True)) and registry_index is not None:
        try:
            health_store=DailyHealthLedgerStore(
                registry_index,
                max_events=int(runtime.get("health_ledger_max_events",96)),
            )
            health_telemetry["enabled"]=True
        except Exception as exc:
            health_telemetry.update({
                "enabled":True,
                "error":f"{type(exc).__name__}: {exc}",
            })

    adaptive_enabled=bool(runtime.get("adaptive_yield_routing",True))
    persist_daily=bool(runtime.get("adaptive_yield_persist_daily",True))
    history_enabled=bool(runtime.get("adaptive_yield_history_enabled",True))
    history_weight=float(runtime.get("adaptive_yield_history_weight",0.25))
    history_decay=float(runtime.get("adaptive_yield_history_decay",0.75))

    if adaptive_enabled and history_enabled and registry_index is not None:
        try:
            history_store=HistoricalYieldProfileStore(
                registry_index,
                max_entries=int(
                    runtime.get("adaptive_yield_history_max_entries",1500)
                ),
            )
            loaded_history,history_meta=history_store.load()
            historical_hints.update(loaded_history)
            history_telemetry.update({
                "enabled":True,
                "loaded":history_meta.get("status")=="loaded",
                "load_status":history_meta.get("status",""),
                "load_entries":int(history_meta.get("entries",0) or 0),
                "load_bytes":int(history_meta.get("bytes",0) or 0),
                "last_completed_date":history_meta.get("last_completed_date",""),
                "state_key":history_meta.get("key",""),
                "weight":history_weight,
                "decay":history_decay,
            })
        except Exception as exc:
            # Historical routing is non-authoritative. Never overwrite an
            # unknown remote profile after a failed read; continue with
            # same-day learning only and preserve the existing object.
            history_store=None
            history_telemetry.update({
                "enabled":True,
                "load_error":f"{type(exc).__name__}: {exc}",
                "weight":history_weight,
                "decay":history_decay,
            })

    if adaptive_enabled and persist_daily and registry_index is not None:
        try:
            yield_state_store=DailyYieldStateStore(
                registry_index,
                max_entries=int(runtime.get("adaptive_yield_state_max_entries",1500)),
            )
            loaded_hints,load_meta=yield_state_store.load(run_date)
            yield_hints.update(loaded_hints)
            yield_state_telemetry.update({
                "enabled":True,
                "loaded":load_meta.get("status")=="loaded",
                "load_status":load_meta.get("status",""),
                "load_entries":int(load_meta.get("entries",0) or 0),
                "load_bytes":int(load_meta.get("bytes",0) or 0),
                "state_key":load_meta.get("key",""),
            })
        except Exception as exc:
            yield_state_telemetry.update({
                "enabled":True,
                "load_error":f"{type(exc).__name__}: {exc}",
            })

    event_budget_exhausted=False
    try:
        for cycle_index in range(max_cycles):
            if _deadline_is_near(
                event_deadline_monotonic,
                float(runtime.get("event_deadline_guard_seconds",60)),
            ):
                event_budget_exhausted=True
                final_status="partial-budget"
                break
            routing_hints=_merge_routing_hints(
                yield_hints,
                historical_hints,
                historical_weight=history_weight,
            ) if adaptive_enabled else yield_hints
            emit_progress(
                "event_cycle_start",
                enabled=progress_enabled,
                started_monotonic=event_started_monotonic,
                run_date=run_date,
                cycle=cycle_index+1,
                max_cycles=max_cycles,
                zero_progress_streak=zero_progress_streak,
            )
            result=run_once(
                config,
                dry_run=False,
                run_date=run_date,
                sources=sources,
                store=store,
                registry_index=registry_index,
                enricher=enricher,
                yield_hints=routing_hints,
                daily_yield_hints=yield_hints,
                cursor_offset=cycle_index,
                deadline_monotonic=event_deadline_monotonic,
            )
            cycles.append(result)
            emit_progress(
                "event_cycle_end",
                enabled=progress_enabled,
                started_monotonic=event_started_monotonic,
                run_date=run_date,
                cycle=cycle_index+1,
                status=result.get("status",""),
                accepted=int(result.get("accepted",0) or 0),
                discovered=int(result.get("discovered",0) or 0),
                event_budget_exhausted=bool(
                    result.get("event_budget_exhausted",False)
                ),
            )
            cycle_attempts=result.get("attempts",[]) or []
            if cycle_attempts:
                _update_yield_hints(yield_hints,cycle_attempts)
                yield_state_dirty=True
            accepted_total += int(result.get("accepted", 0) or 0)
            final_counts = result.get("counts", final_counts) or final_counts
            final_country_counts = result.get("country_counts", final_country_counts) or final_country_counts
            final_status = result.get("status", "ok")

            if bool(result.get("event_budget_exhausted",False)):
                event_budget_exhausted=True
                final_status="partial-budget"
                break

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

        if yield_state_store is not None and yield_state_dirty:
            try:
                save_meta=yield_state_store.save(run_date,yield_hints)
                yield_state_telemetry.update({
                    "saved":True,
                    "save_entries":int(save_meta.get("entries",0) or 0),
                    "save_bytes":int(save_meta.get("bytes",0) or 0),
                    "state_key":save_meta.get(
                        "key",
                        yield_state_telemetry.get("state_key",""),
                    ),
                })
            except Exception as exc:
                yield_state_telemetry["save_error"]=f"{type(exc).__name__}: {exc}"

        if (
            history_store is not None
            and final_status=="complete"
            and yield_hints
        ):
            try:
                history_meta=history_store.save_completion(
                    run_date,
                    yield_hints,
                    decay=history_decay,
                )
                history_telemetry.update({
                    "saved":history_meta.get("status")=="saved",
                    "save_status":history_meta.get("status",""),
                    "save_entries":int(history_meta.get("entries",0) or 0),
                    "save_bytes":int(history_meta.get("bytes",0) or 0),
                    "last_completed_date":history_meta.get(
                        "last_completed_date",
                        history_telemetry.get("last_completed_date",""),
                    ),
                    "state_key":history_meta.get(
                        "key",
                        history_telemetry.get("state_key",""),
                    ),
                })
            except Exception as exc:
                history_telemetry["save_error"]=f"{type(exc).__name__}: {exc}"

        final_result={
            "status":final_status,
            "run_date":run_date,
            "cycles_executed":len(cycles),
            "max_cycles_per_run":max_cycles,
            "max_zero_progress_cycles":max_zero_progress_cycles,
            "event_wall_time_seconds":event_wall_time_seconds,
            "event_budget_exhausted":event_budget_exhausted,
            "event_runtime_seconds":round(
                max(0.0,time.monotonic()-event_started_monotonic),
                3,
            ),
            "zero_progress_streak":zero_progress_streak,
            "accepted":accepted_total,
            "discovered":sum(
                int(item.get("discovered",0) or 0)
                for item in cycles
            ),
            "source_phone_candidates":sum(
                int(item.get("source_phone_candidates",0) or 0)
                for item in cycles
            ),
            "website_only_candidates":sum(
                int(item.get("website_only_candidates",0) or 0)
                for item in cycles
            ),
            "source_errors":sum(
                int(item.get("source_errors",0) or 0)
                for item in cycles
            ),
            "zero_result_shards":sum(
                int(item.get("zero_result_shards",0) or 0)
                for item in cycles
            ),
            "categories_attempted":max(
                [
                    int(item.get("categories_attempted",0) or 0)
                    for item in cycles
                ]
                or [0]
            ),
            "source_batch_duplicates":sum(
                int(item.get("source_batch_duplicates",0) or 0)
                for item in cycles
            ),
            "remote_prefilter_duplicates":sum(
                int(item.get("remote_prefilter_duplicates",0) or 0)
                for item in cycles
            ),
            "adaptive_cooldown_routes_deferred":max(
                [
                    int(item.get("adaptive_cooldown_routes_deferred",0) or 0)
                    for item in cycles
                ]
                or [0]
            ),
            "counts":final_counts,
            "country_counts":final_country_counts,
            "adaptive_yield":_yield_hint_summary(yield_hints),
            "adaptive_yield_state":yield_state_telemetry,
            "adaptive_yield_history":history_telemetry,
            "registry_read_cache":(
                dict(cycles[-1].get("registry_read_cache",{}) or {})
                if cycles else {}
            ),
            "cycles":cycles,
        }
        if schedule:
            final_result["schedule"]=dict(schedule)

        if health_store is not None:
            try:
                health_meta=health_store.append(
                    run_date,
                    run_health_event(
                        final_result,
                        origin=health_telemetry["origin"],
                    ),
                )
                health_telemetry.update({
                    "recorded":health_meta.get("status") in {"appended","duplicate"},
                    "write_status":health_meta.get("status",""),
                    "event_count":int(health_meta.get("events",0) or 0),
                    "bytes":int(health_meta.get("bytes",0) or 0),
                    "key":health_meta.get("key",""),
                })
            except Exception as exc:
                health_telemetry["error"]=f"{type(exc).__name__}: {exc}"
        final_result["health_ledger"]=health_telemetry
    finally:
        emit_progress(
            "event_cleanup_start",
            enabled=progress_enabled,
            started_monotonic=event_started_monotonic,
            run_date=run_date,
        )
        _close_sources(sources)
        if registry_index is not None:
            close=getattr(registry_index,"close",None)
            if callable(close):
                close()
        if enricher is not None:
            close=getattr(enricher,"close",None)
            if callable(close):
                close()
        emit_progress(
            "event_cleanup_end",
            enabled=progress_enabled,
            started_monotonic=event_started_monotonic,
            run_date=run_date,
        )

    emit_progress(
        "event_end",
        enabled=progress_enabled,
        started_monotonic=event_started_monotonic,
        run_date=run_date,
        status=final_result.get("status",""),
        accepted=int(final_result.get("accepted",0) or 0),
        cycles_executed=int(final_result.get("cycles_executed",0) or 0),
        event_budget_exhausted=bool(
            final_result.get("event_budget_exhausted",False)
        ),
    )
    return final_result
