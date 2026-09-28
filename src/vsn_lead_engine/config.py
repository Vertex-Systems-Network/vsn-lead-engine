from __future__ import annotations

import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _validate_geographies(geographies: list[dict]) -> None:
    allowed_countries={"United States","Canada"}
    seen=set()
    for geo in geographies:
        country=str(geo.get("country","")).strip()
        region=str(geo.get("region","")).strip()
        city=str(geo.get("city","")).strip()
        if country not in allowed_countries:
            raise ValueError(f"Unsupported geography country: {country or geo}")
        if not region or not city:
            raise ValueError(f"Geography requires region and city: {geo}")
        key=(country.lower(),region.lower(),city.lower())
        if key in seen:
            raise ValueError(f"Duplicate geography: {country} / {region} / {city}")
        seen.add(key)

        bbox=geo.get("bbox")
        if not isinstance(bbox,list) or len(bbox)!=4:
            raise ValueError(f"Geography is missing a 4-value bbox: {geo}")
        xmin,ymin,xmax,ymax=[float(v) for v in bbox]
        if not (-180 <= xmin <= 180 and -180 <= xmax <= 180):
            raise ValueError(f"Longitude outside valid range: {bbox}")
        if not (-90 <= ymin <= 90 and -90 <= ymax <= 90):
            raise ValueError(f"Latitude outside valid range: {bbox}")
        if not (xmin < xmax and ymin < ymax):
            raise ValueError(f"Invalid bbox order: {bbox}")


def load_config() -> dict:
    path=Path(os.getenv("VSN_RUNTIME_CONFIG","config/runtime.json"))
    with path.open("r",encoding="utf-8") as handle:
        config=json.load(handle)

    required={"runtime","drive","sources","categories","geographies","registry"}
    missing=required.difference(config)
    if missing:
        raise ValueError(f"Missing config sections: {sorted(missing)}")
    if len(config["categories"])!=12:
        raise ValueError("Exactly 12 categories are required.")
    if int(config["runtime"]["daily_target_per_category"])!=1000:
        raise ValueError("Daily target must remain 1000 per category.")
    if config["runtime"]["mode"]!="free":
        raise ValueError("This branch only supports FREE mode.")

    timezone=str(config["runtime"].get("timezone","")).strip()
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"Invalid runtime timezone: {timezone!r}") from None
    start_hour=int(config["runtime"].get("start_hour",8))
    end_hour=int(config["runtime"].get("end_hour",23))
    if start_hour < 0 or start_hour > 23:
        raise ValueError("runtime.start_hour must be between 0 and 23.")
    if end_hour < 0 or end_hour > 23:
        raise ValueError("runtime.end_hour must be between 0 and 23.")
    if start_hour > end_hour:
        raise ValueError("runtime.start_hour cannot be after runtime.end_hour.")

    drive=config["drive"]
    if not drive.get("folder_id"):
        raise ValueError("Lead Drive folder ID is required.")
    if not drive.get("master_registry_spreadsheet_id"):
        raise ValueError("Master Registry spreadsheet ID is required.")
    if not drive.get("master_registry_tab"):
        raise ValueError("Master Registry tab is required.")
    if not drive.get("daily_title_prefix"):
        raise ValueError("Daily workbook title prefix is required.")
    if not drive.get("daily_template_spreadsheet_id"):
        raise ValueError("Daily workbook template spreadsheet ID is required.")

    if int(config["runtime"].get("max_shard_attempts",0)) < 1:
        raise ValueError("max_shard_attempts must be at least 1.")
    if int(config["runtime"].get("batch_accept_limit",0)) < 1:
        raise ValueError("batch_accept_limit must be at least 1.")
    if int(config["runtime"].get("google_api_retries",5)) < 0:
        raise ValueError("google_api_retries cannot be negative.")
    if int(config["runtime"].get("source_retry_attempts",3)) < 1:
        raise ValueError("source_retry_attempts must be at least 1.")
    if float(config["runtime"].get("source_retry_backoff_seconds",2)) < 0:
        raise ValueError("source_retry_backoff_seconds cannot be negative.")
    max_cycles_per_run=int(config["runtime"].get("max_cycles_per_run",3))
    if max_cycles_per_run < 1:
        raise ValueError("max_cycles_per_run must be at least 1.")
    tail_max_cycles=int(
        config["runtime"].get("tail_max_cycles_per_run",max_cycles_per_run)
    )
    if tail_max_cycles < max_cycles_per_run or tail_max_cycles > 20:
        raise ValueError(
            "tail_max_cycles_per_run must be between max_cycles_per_run and 20."
        )
    tail_threshold=int(
        config["runtime"].get("tail_incomplete_category_threshold",4)
    )
    if tail_threshold < 1 or tail_threshold > len(config["categories"]):
        raise ValueError(
            "tail_incomplete_category_threshold must be between 1 and category count."
        )
    event_wall=float(
        config["runtime"].get("event_wall_time_seconds",1500)
    )
    if event_wall < 300 or event_wall > 1680:
        raise ValueError(
            "event_wall_time_seconds must be between 300 and 1680."
        )
    event_guard=float(
        config["runtime"].get("event_deadline_guard_seconds",60)
    )
    if event_guard < 10 or event_guard > 180:
        raise ValueError(
            "event_deadline_guard_seconds must be between 10 and 180."
        )
    if event_guard >= event_wall:
        raise ValueError(
            "event_deadline_guard_seconds must be less than event_wall_time_seconds."
        )
    commit_guard=float(
        config["runtime"].get("commit_deadline_guard_seconds",180)
    )
    if commit_guard < event_guard or commit_guard > 600:
        raise ValueError(
            "commit_deadline_guard_seconds must be between "
            "event_deadline_guard_seconds and 600."
        )
    if commit_guard >= event_wall:
        raise ValueError(
            "commit_deadline_guard_seconds must be less than event_wall_time_seconds."
        )
    readiness_attempts=int(
        config["runtime"].get("workbook_readiness_attempts",3)
    )
    if readiness_attempts < 1 or readiness_attempts > 5:
        raise ValueError("workbook_readiness_attempts must be between 1 and 5.")
    readiness_delay=float(
        config["runtime"].get("workbook_readiness_retry_delay_seconds",60)
    )
    if readiness_delay < 0 or readiness_delay > 180:
        raise ValueError(
            "workbook_readiness_retry_delay_seconds must be between 0 and 180."
        )

    max_zero_progress_cycles=int(
        config["runtime"].get("max_zero_progress_cycles",max_cycles_per_run)
    )
    if max_zero_progress_cycles < 1 or max_zero_progress_cycles > max_cycles_per_run:
        raise ValueError(
            "max_zero_progress_cycles must be between 1 and max_cycles_per_run."
        )
    candidate_partition_count=int(config["runtime"].get("candidate_partition_count",8))
    if candidate_partition_count < 1 or candidate_partition_count > 64:
        raise ValueError("candidate_partition_count must be between 1 and 64.")
    adaptive_bonus=float(
        config["runtime"].get("adaptive_yield_exploration_bonus",0.15)
    )
    if adaptive_bonus < 0 or adaptive_bonus > 1:
        raise ValueError(
            "adaptive_yield_exploration_bonus must be between 0 and 1."
        )
    adaptive_score_mode=str(
        config["runtime"].get("adaptive_yield_score_mode","throughput")
    ).strip().lower()
    if adaptive_score_mode not in {"throughput","conversion"}:
        raise ValueError(
            "adaptive_yield_score_mode must be throughput or conversion."
        )
    adaptive_state_max_entries=int(
        config["runtime"].get("adaptive_yield_state_max_entries",1500)
    )
    if adaptive_state_max_entries < 100 or adaptive_state_max_entries > 5000:
        raise ValueError(
            "adaptive_yield_state_max_entries must be between 100 and 5000."
        )

    adaptive_history_weight=float(
        config["runtime"].get("adaptive_yield_history_weight",0.25)
    )
    if adaptive_history_weight < 0 or adaptive_history_weight > 1:
        raise ValueError(
            "adaptive_yield_history_weight must be between 0 and 1."
        )
    adaptive_history_decay=float(
        config["runtime"].get("adaptive_yield_history_decay",0.75)
    )
    if adaptive_history_decay < 0 or adaptive_history_decay > 1:
        raise ValueError(
            "adaptive_yield_history_decay must be between 0 and 1."
        )
    adaptive_history_max_entries=int(
        config["runtime"].get("adaptive_yield_history_max_entries",1500)
    )
    if adaptive_history_max_entries < 100 or adaptive_history_max_entries > 5000:
        raise ValueError(
            "adaptive_yield_history_max_entries must be between 100 and 5000."
        )

    cooldown_min_visits=int(
        config["runtime"].get("adaptive_zero_yield_cooldown_min_visits",2)
    )
    if cooldown_min_visits < 1 or cooldown_min_visits > 10:
        raise ValueError(
            "adaptive_zero_yield_cooldown_min_visits must be between 1 and 10."
        )
    cooldown_min_discovered=int(
        config["runtime"].get("adaptive_zero_yield_cooldown_min_discovered",100)
    )
    if cooldown_min_discovered < 1 or cooldown_min_discovered > 5000:
        raise ValueError(
            "adaptive_zero_yield_cooldown_min_discovered must be between 1 and 5000."
        )

    cooldown_min_partitions=int(
        config["runtime"].get("adaptive_zero_yield_cooldown_min_partitions",4)
    )
    if cooldown_min_partitions < 1 or cooldown_min_partitions > 64:
        raise ValueError(
            "adaptive_zero_yield_cooldown_min_partitions must be between 1 and 64."
        )

    health_ledger_max_events=int(
        config["runtime"].get("health_ledger_max_events",96)
    )
    if health_ledger_max_events < 16 or health_ledger_max_events > 256:
        raise ValueError(
            "health_ledger_max_events must be between 16 and 256."
        )

    overture=config.get("sources",{}).get("overture",{})
    if overture.get("enabled",False):
        reserve=float(overture.get("website_candidate_reserve_fraction",0.20))
        if reserve < 0 or reserve > 0.5:
            raise ValueError(
                "sources.overture.website_candidate_reserve_fraction must be between 0 and 0.5."
            )
        query_timeout=float(overture.get("query_timeout_seconds",45))
        if query_timeout < 10 or query_timeout > 120:
            raise ValueError(
                "sources.overture.query_timeout_seconds must be between 10 and 120."
            )

    enrichment=config.get("enrichment",{})
    if enrichment.get("enabled",False):
        max_candidates=int(enrichment.get("max_candidates_per_run",160))
        if max_candidates < 1:
            raise ValueError("enrichment.max_candidates_per_run must be at least 1.")
        max_candidates_per_call=int(enrichment.get("max_candidates_per_call",12))
        if max_candidates_per_call < 1 or max_candidates_per_call > max_candidates:
            raise ValueError(
                "enrichment.max_candidates_per_call must be between 1 and max_candidates_per_run."
            )
        workers=int(enrichment.get("workers",8))
        if workers < 1 or workers > 16:
            raise ValueError("enrichment.workers must be between 1 and 16.")
        if float(enrichment.get("request_timeout_seconds",6)) < 1:
            raise ValueError("enrichment.request_timeout_seconds must be at least 1.")
        pages=int(enrichment.get("max_pages_per_site",2))
        if pages < 1 or pages > 3:
            raise ValueError("enrichment.max_pages_per_site must be between 1 and 3.")
        response_bytes=int(enrichment.get("max_response_bytes",524288))
        if response_bytes < 65536 or response_bytes > 2000000:
            raise ValueError("enrichment.max_response_bytes must be 65536..2000000.")
        if not str(enrichment.get("user_agent","")).strip():
            raise ValueError("enrichment.user_agent is required when enrichment is enabled.")

        common=enrichment.get("common_crawl",{})
        if common.get("enabled",False):
            common_max=int(common.get("max_lookups_per_run",8))
            if common_max < 1:
                raise ValueError("enrichment.common_crawl.max_lookups_per_run must be at least 1.")
            common_per_call=int(common.get("max_lookups_per_call",1))
            if common_per_call < 1 or common_per_call > common_max:
                raise ValueError(
                    "enrichment.common_crawl.max_lookups_per_call must be between 1 and max_lookups_per_run."
                )
            if float(common.get("min_interval_seconds",2.5)) < 1:
                raise ValueError("enrichment.common_crawl.min_interval_seconds must be at least 1.")
            for key in ["index_url","data_url"]:
                value=str(common.get(key,"")).strip()
                if not value.startswith("https://"):
                    raise ValueError(f"enrichment.common_crawl.{key} must use HTTPS.")

    registry=config["registry"]
    registry_mode=str(registry.get("mode","sheets")).strip().lower()
    if registry_mode not in {"sheets","dual","r2"}:
        raise ValueError("registry.mode must be one of: sheets, dual, r2.")
    for key in [
        "account_id_env",
        "access_key_id_env",
        "secret_access_key_env",
        "bucket_env",
    ]:
        if not registry.get(key):
            raise ValueError(f"registry.{key} is required.")
    if not str(registry.get("prefix","")).strip("/"):
        raise ValueError("registry.prefix is required.")
    max_registry_workers=int(registry.get("max_workers",32))
    if max_registry_workers < 4:
        raise ValueError("registry.max_workers must be at least 4.")
    pack_commit_workers=int(registry.get("pack_commit_workers",16))
    if pack_commit_workers < 1 or pack_commit_workers > max_registry_workers:
        raise ValueError(
            "registry.pack_commit_workers must be between 1 and max_workers."
        )
    if int(registry.get("retry_attempts",4)) < 1:
        raise ValueError("registry.retry_attempts must be at least 1.")

    registry_layout=str(registry.get("layout","objects-v1")).strip().lower()
    if registry_layout not in {"objects-v1","packed-v2"}:
        raise ValueError("registry.layout must be one of: objects-v1, packed-v2.")
    if registry_layout=="packed-v2":
        pack_shard_chars=int(registry.get("pack_shard_chars",1))
        if pack_shard_chars not in {1,2}:
            raise ValueError("registry.pack_shard_chars must be 1 or 2.")
        if int(registry.get("lock_stale_seconds",180)) < 30:
            raise ValueError("registry.lock_stale_seconds must be at least 30.")
        read_cache_max=int(registry.get("read_cache_max_entries",128))
        if read_cache_max < 16 or read_cache_max > 1024:
            raise ValueError(
                "registry.read_cache_max_entries must be between 16 and 1024."
            )
        legacy_cache_max=int(
            registry.get("legacy_read_cache_max_entries",4096)
        )
        if legacy_cache_max < 64 or legacy_cache_max > 20000:
            raise ValueError(
                "registry.legacy_read_cache_max_entries must be between 64 and 20000."
            )

    _validate_geographies(config["geographies"])

    return config
