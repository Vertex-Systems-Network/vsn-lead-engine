from __future__ import annotations

import json
import os
from pathlib import Path


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
    if int(config["runtime"].get("max_cycles_per_run",3)) < 1:
        raise ValueError("max_cycles_per_run must be at least 1.")

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
    if int(registry.get("max_workers",32)) < 4:
        raise ValueError("registry.max_workers must be at least 4.")
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

    for geo in config["geographies"]:
        bbox=geo.get("bbox")
        if not isinstance(bbox,list) or len(bbox)!=4:
            raise ValueError(f"Geography is missing a 4-value bbox: {geo}")
        xmin,ymin,xmax,ymax=[float(v) for v in bbox]
        if not (xmin < xmax and ymin < ymax):
            raise ValueError(f"Invalid bbox order: {bbox}")

    return config
