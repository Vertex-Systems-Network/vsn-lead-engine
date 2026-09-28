from __future__ import annotations

import time

from .dedupe import fingerprints
from .registry import build_registry_index, fingerprint_token
from .sources.overture import OverturePlaceSource
from .taxonomy_audit import select_balanced_geographies


def probe_motorbike_registry_collisions(
    config: dict,
    *,
    max_geographies: int = 4,
    partitions_per_geography: int = 2,
) -> dict:
    """Measure exact production R2 collision loss without mutating the ledger."""
    overture=config.get("sources",{}).get("overture",{})
    if not overture.get("enabled",False):
        return {"status":"disabled","message":"Overture source is disabled."}

    runtime=config["runtime"]
    partition_count=max(1,int(runtime.get("candidate_partition_count",16)))
    max_geographies=max(1,min(12,int(max_geographies)))
    partitions_per_geography=max(
        1,
        min(partition_count,int(partitions_per_geography)),
    )
    row_limit=max(
        1,
        min(
            int(runtime.get("candidate_limit_per_shard",500)),
            int(overture.get("candidate_limit",500)),
        ),
    )
    selected=select_balanced_geographies(
        config.get("geographies",[]),
        max_geographies,
    )
    source=OverturePlaceSource(
        release=str(overture.get("release","latest")),
        stac_url=str(
            overture.get(
                "stac_url",
                "https://stac.overturemaps.org/catalog.json",
            )
        ),
        candidate_limit=int(overture.get("candidate_limit",500)),
        website_candidate_reserve_fraction=float(
            overture.get("website_candidate_reserve_fraction",0.20)
        ),
        query_timeout_seconds=float(overture.get("query_timeout_seconds",45)),
    )
    index=build_registry_index(config)
    if index is None:
        source.close()
        return {
            "status":"disabled",
            "message":"R2 registry is not enabled.",
        }

    probes=[]
    failures=[]
    total_candidates=0
    total_collisions=0
    total_survivors=0
    try:
        release=source._resolve_release()
        for geo_index,geography in enumerate(selected):
            first_partition=(geo_index*partitions_per_geography) % partition_count
            for offset in range(partitions_per_geography):
                partition=(first_partition+offset) % partition_count
                search_geo={
                    **geography,
                    "_candidate_partition_count":partition_count,
                    "_candidate_partition":partition,
                }
                started=time.monotonic()
                try:
                    leads=source.search(
                        "Motorbikes",
                        search_geo,
                        limit=row_limit,
                    )
                    source_seconds=round(
                        max(0.0,time.monotonic()-started),
                        3,
                    )
                    collision_started=time.monotonic()
                    collision_keys=index.collision_keys(leads) if leads else set()
                    collision_seconds=round(
                        max(0.0,time.monotonic()-collision_started),
                        3,
                    )
                    lead_tokens={
                        fingerprint_token("u",fingerprints(lead).unique)
                        for lead in leads
                    }
                    lead_tokens.discard("")
                    collisions=len(lead_tokens & collision_keys)
                    survivors=max(0,len(lead_tokens)-collisions)
                    total_candidates+=len(lead_tokens)
                    total_collisions+=collisions
                    total_survivors+=survivors
                    probes.append({
                        "country":geography["country"],
                        "region":geography["region"],
                        "city":geography["city"],
                        "partition":partition,
                        "partition_count":partition_count,
                        "candidates":len(lead_tokens),
                        "collisions":collisions,
                        "survivors":survivors,
                        "collision_rate_pct":round(
                            (collisions/len(lead_tokens))*100,
                            2,
                        ) if lead_tokens else 0.0,
                        "source_seconds":source_seconds,
                        "collision_seconds":collision_seconds,
                        "status":"ok",
                    })
                except Exception as exc:
                    item={
                        "country":geography["country"],
                        "region":geography["region"],
                        "city":geography["city"],
                        "partition":partition,
                        "partition_count":partition_count,
                        "status":"error",
                        "error_type":type(exc).__name__,
                        "message":str(exc),
                    }
                    probes.append(item)
                    failures.append(item)

        successful=[item for item in probes if item["status"]=="ok"]
        return {
            "status":"ok" if successful else "probe-failed",
            "probe":"motorbike-r2-collisions",
            "release":release,
            "category":"Motorbikes",
            "registry_layout":str(
                config.get("registry",{}).get("layout","")
            ),
            "partition_count":partition_count,
            "queries":len(probes),
            "successful_queries":len(successful),
            "failed_queries":len(failures),
            "total_candidates":total_candidates,
            "total_collisions":total_collisions,
            "total_survivors":total_survivors,
            "collision_rate_pct":round(
                (total_collisions/total_candidates)*100,
                2,
            ) if total_candidates else 0.0,
            "probes":probes,
            "write_operations":0,
        }
    finally:
        source.close()
        index.close()
