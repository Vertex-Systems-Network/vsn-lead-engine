from __future__ import annotations

import time

from .sources.overture import OverturePlaceSource
from .taxonomy_audit import select_balanced_geographies


def probe_motorbike_source(
    config: dict,
    *,
    max_geographies: int = 4,
    partitions_per_geography: int = 2,
    candidate_limit: int | None = None,
) -> dict:
    """Exercise the exact production Motorbikes source path without writes."""
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
            int(candidate_limit or runtime.get("candidate_limit_per_shard",500)),
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

    probes=[]
    failures=[]
    total_candidates=0
    total_phone_candidates=0
    total_website_only_candidates=0
    try:
        release=source._resolve_release()
        for geo_index,geography in enumerate(selected):
            # Offset each metro so the diagnostic covers different production
            # hash cohorts while remaining deterministic and repeatable.
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
                    elapsed=round(max(0.0,time.monotonic()-started),3)
                    phone_count=sum(
                        1 for lead in leads
                        if bool(str(lead.phone or "").strip())
                    )
                    website_only=sum(
                        1 for lead in leads
                        if (
                            not str(lead.phone or "").strip()
                            and bool(str(lead.website or "").strip())
                        )
                    )
                    total_candidates+=len(leads)
                    total_phone_candidates+=phone_count
                    total_website_only_candidates+=website_only
                    probes.append({
                        "country":geography["country"],
                        "region":geography["region"],
                        "city":geography["city"],
                        "partition":partition,
                        "partition_count":partition_count,
                        "limit":row_limit,
                        "candidates":len(leads),
                        "phone_candidates":phone_count,
                        "website_only_candidates":website_only,
                        "seconds":elapsed,
                        "status":"ok",
                    })
                except Exception as exc:
                    elapsed=round(max(0.0,time.monotonic()-started),3)
                    item={
                        "country":geography["country"],
                        "region":geography["region"],
                        "city":geography["city"],
                        "partition":partition,
                        "partition_count":partition_count,
                        "limit":row_limit,
                        "seconds":elapsed,
                        "status":"error",
                        "error_type":type(exc).__name__,
                        "message":str(exc),
                    }
                    probes.append(item)
                    failures.append(item)

        successful=[item for item in probes if item["status"]=="ok"]
        nonzero=[item for item in successful if int(item.get("candidates",0))>0]
        return {
            "status":"ok" if successful else "probe-failed",
            "probe":"motorbike-production-source",
            "release":release,
            "category":"Motorbikes",
            "partition_count":partition_count,
            "max_geographies":max_geographies,
            "partitions_per_geography":partitions_per_geography,
            "candidate_limit":row_limit,
            "queries":len(probes),
            "successful_queries":len(successful),
            "failed_queries":len(failures),
            "nonzero_queries":len(nonzero),
            "total_candidates":total_candidates,
            "total_phone_candidates":total_phone_candidates,
            "total_website_only_candidates":total_website_only_candidates,
            "max_candidates_in_query":max(
                [int(item.get("candidates",0)) for item in successful] or [0]
            ),
            "probes":probes,
            "write_operations":0,
        }
    finally:
        source.close()
