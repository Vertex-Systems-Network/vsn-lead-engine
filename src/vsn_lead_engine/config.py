from __future__ import annotations
import json, os
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
    return config
