from __future__ import annotations

import json
import os
from pathlib import Path


def load_config() -> dict:
    path=Path(os.getenv("VSN_RUNTIME_CONFIG","config/runtime.json"))
    with path.open("r",encoding="utf-8") as handle:
        config=json.load(handle)

    required={"runtime","drive","sources","categories","geographies"}
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

    for geo in config["geographies"]:
        bbox=geo.get("bbox")
        if not isinstance(bbox,list) or len(bbox)!=4:
            raise ValueError(f"Geography is missing a 4-value bbox: {geo}")
        xmin,ymin,xmax,ymax=[float(v) for v in bbox]
        if not (xmin < xmax and ymin < ymax):
            raise ValueError(f"Invalid bbox order: {bbox}")

    return config
