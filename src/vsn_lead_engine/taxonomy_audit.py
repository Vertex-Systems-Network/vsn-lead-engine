from __future__ import annotations

from collections import defaultdict
import threading
import time

from .sources.overture import OverturePlaceSource, category_match_reason


MOTORBIKE_AUDIT_PATTERN = (
    r"(motorcycle|motorbike|motor.?scooter|scooter|powersport|motocross|"
    r"moped|all.?terrain|(^|[^a-z])atv([^a-z]|$)|dirt.?bike)"
)


def select_balanced_geographies(
    geographies: list[dict],
    max_geographies: int,
) -> list[dict]:
    """Select a deterministic country-balanced diagnostic sample."""
    limit=max(1,int(max_geographies))
    groups: dict[str,list[dict]] = defaultdict(list)
    country_order: list[str] = []
    for geography in geographies:
        country=str(geography.get("country","")).strip()
        if country not in groups:
            country_order.append(country)
        groups[country].append(geography)

    selected=[]
    positions={country:0 for country in country_order}
    while len(selected) < limit:
        progressed=False
        for country in country_order:
            position=positions[country]
            group=groups[country]
            if position >= len(group):
                continue
            selected.append(group[position])
            positions[country]+=1
            progressed=True
            if len(selected) >= limit:
                break
        if not progressed:
            break
    return selected


def summarize_taxonomy_rows(rows: list[dict]) -> list[dict]:
    """Aggregate diagnostic rows without exposing business/contact payloads."""
    buckets={}
    for row in rows:
        primary=str(row.get("taxonomy_primary") or "").strip()
        basic=str(row.get("basic_category") or "").strip()
        hierarchy=row.get("taxonomy_hierarchy") or []
        name=str(row.get("name") or "")
        key=(primary,basic)
        bucket=buckets.setdefault(
            key,
            {
                "taxonomy_primary":primary,
                "basic_category":basic,
                "rows":0,
                "with_phone":0,
                "with_website":0,
                "name_keyword_hits":0,
                "taxonomy_keyword_hits":0,
                "recognized_by_current_rule":0,
                "countries":set(),
                "metros":set(),
            },
        )
        bucket["rows"]+=1
        bucket["with_phone"]+=int(bool(str(row.get("phone") or "").strip()))
        bucket["with_website"]+=int(bool(str(row.get("website") or "").strip()))
        bucket["name_keyword_hits"]+=int(bool(row.get("name_match")))
        bucket["taxonomy_keyword_hits"]+=int(bool(row.get("taxonomy_match")))
        bucket["recognized_by_current_rule"]+=int(
            category_match_reason(
                "Motorbikes",
                primary=primary,
                basic=basic,
                hierarchy=hierarchy,
                name=name,
            )
            is not None
        )
        country=str(row.get("_country") or "").strip()
        metro=str(row.get("_metro") or "").strip()
        if country:
            bucket["countries"].add(country)
        if metro:
            bucket["metros"].add(metro)

    result=[]
    for bucket in buckets.values():
        rows_count=int(bucket["rows"])
        recognized=int(bucket["recognized_by_current_rule"])
        result.append({
            **{
                key:value
                for key,value in bucket.items()
                if key not in {"countries","metros"}
            },
            "unrecognized_by_current_rule":rows_count-recognized,
            "countries":sorted(bucket["countries"]),
            "metros":sorted(bucket["metros"]),
        })
    result.sort(
        key=lambda item: (
            -int(item["with_phone"]),
            -int(item["rows"]),
            item["taxonomy_primary"],
            item["basic_category"],
        )
    )
    return result


def _bounded_rows(
    source: OverturePlaceSource,
    geography: dict,
    *,
    rows_per_geography: int,
) -> list[dict]:
    release=source._resolve_release()
    path=(
        f"s3://overturemaps-us-west-2/release/{release}/"
        "theme=places/type=place/*"
    )
    xmin,ymin,xmax,ymax=[float(value) for value in geography["bbox"]]
    sql="""
    SELECT
        coalesce(taxonomy.primary, '') AS taxonomy_primary,
        coalesce(basic_category, '') AS basic_category,
        taxonomy.hierarchy AS taxonomy_hierarchy,
        coalesce(names.primary, '') AS name,
        coalesce(phones[1], '') AS phone,
        coalesce(websites[1], '') AS website,
        regexp_matches(lower(coalesce(names.primary, '')), ?) AS name_match,
        regexp_matches(
            lower(
                concat_ws(
                    '|',
                    coalesce(taxonomy.primary, ''),
                    coalesce(basic_category, ''),
                    coalesce(array_to_string(taxonomy.hierarchy, '|'), '')
                )
            ),
            ?
        ) AS taxonomy_match
    FROM read_parquet(
        ?,
        filename=true,
        hive_partitioning=1
    )
    WHERE
        bbox.xmin BETWEEN ? AND ?
        AND bbox.ymin BETWEEN ? AND ?
        AND names.primary IS NOT NULL
        AND (
            regexp_matches(lower(coalesce(names.primary, '')), ?)
            OR regexp_matches(
                lower(
                    concat_ws(
                        '|',
                        coalesce(taxonomy.primary, ''),
                        coalesce(basic_category, ''),
                        coalesce(array_to_string(taxonomy.hierarchy, '|'), '')
                    )
                ),
                ?
            )
        )
    LIMIT ?
    """
    params=[
        MOTORBIKE_AUDIT_PATTERN,
        MOTORBIKE_AUDIT_PATTERN,
        path,
        xmin,xmax,ymin,ymax,
        MOTORBIKE_AUDIT_PATTERN,
        MOTORBIKE_AUDIT_PATTERN,
        max(1,int(rows_per_geography)),
    ]
    connection=source._get_connection()
    timeout_fired=threading.Event()

    def interrupt_query():
        timeout_fired.set()
        try:
            connection.interrupt()
        except Exception:
            pass

    timer=threading.Timer(source.query_timeout_seconds,interrupt_query)
    timer.daemon=True
    timer.start()
    started=time.monotonic()
    try:
        cursor=connection.execute(sql,params)
        columns=[item[0] for item in cursor.description]
        rows=[dict(zip(columns,row)) for row in cursor.fetchall()]
    except Exception as exc:
        if timeout_fired.is_set():
            raise TimeoutError(
                "Taxonomy audit query exceeded "
                f"{source.query_timeout_seconds:g}s timeout."
            ) from exc
        raise
    finally:
        timer.cancel()

    for row in rows:
        row["_country"]=geography["country"]
        row["_metro"]=f'{geography["city"]}, {geography["region"]}'
        row["_query_seconds"]=round(max(0.0,time.monotonic()-started),3)
    return rows


def audit_motorbike_taxonomy(
    config: dict,
    *,
    max_geographies: int = 8,
    rows_per_geography: int = 250,
) -> dict:
    """Read-only evidence audit for Motorbikes taxonomy breadth."""
    overture=config.get("sources",{}).get("overture",{})
    if not overture.get("enabled",False):
        return {
            "status":"disabled",
            "message":"Overture source is disabled.",
        }

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

    rows=[]
    failures=[]
    timings=[]
    try:
        release=source._resolve_release()
        for geography in selected:
            started=time.monotonic()
            try:
                batch=_bounded_rows(
                    source,
                    geography,
                    rows_per_geography=rows_per_geography,
                )
                rows.extend(batch)
                timings.append({
                    "country":geography["country"],
                    "region":geography["region"],
                    "city":geography["city"],
                    "rows":len(batch),
                    "seconds":round(max(0.0,time.monotonic()-started),3),
                })
            except Exception as exc:
                failures.append({
                    "country":geography["country"],
                    "region":geography["region"],
                    "city":geography["city"],
                    "error_type":type(exc).__name__,
                    "message":str(exc),
                })
    finally:
        source.close()

    buckets=summarize_taxonomy_rows(rows)
    return {
        "status":"ok" if rows or not failures else "audit-failed",
        "audit":"motorbike-taxonomy-breadth",
        "release":release,
        "pattern":MOTORBIKE_AUDIT_PATTERN,
        "max_geographies":max(1,int(max_geographies)),
        "rows_per_geography":max(1,int(rows_per_geography)),
        "geographies_sampled":[
            {
                "country":item["country"],
                "region":item["region"],
                "city":item["city"],
            }
            for item in selected
        ],
        "matched_rows":len(rows),
        "matched_rows_with_phone":sum(
            1 for row in rows if str(row.get("phone") or "").strip()
        ),
        "recognized_rows":sum(
            int(bucket["recognized_by_current_rule"])
            for bucket in buckets
        ),
        "unrecognized_rows":sum(
            int(bucket["unrecognized_by_current_rule"])
            for bucket in buckets
        ),
        "taxonomy_buckets":buckets,
        "queries":timings,
        "failures":failures,
        "write_operations":0,
    }
