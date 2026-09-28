from __future__ import annotations

from .overture import OverturePlaceSource
from .overpass import OverpassSource


def build_sources(config: dict):
    result = []
    sources = config.get("sources", {})

    overture = sources.get("overture", {})
    if overture.get("enabled", False):
        result.append(
            OverturePlaceSource(
                release=str(overture.get("release", "latest")),
                stac_url=str(overture.get("stac_url", "https://stac.overturemaps.org/catalog.json")),
                candidate_limit=int(overture.get("candidate_limit", 500)),
                website_candidate_reserve_fraction=float(
                    overture.get("website_candidate_reserve_fraction", 0.20)
                ),
                query_timeout_seconds=float(
                    overture.get("query_timeout_seconds",45)
                ),
            )
        )

    overpass = sources.get("overpass", {})
    if overpass.get("enabled", False):
        result.append(
            OverpassSource(
                timeout_seconds=int(overpass.get("timeout_seconds", 45)),
                min_interval_seconds=int(overpass.get("min_request_interval_seconds", 8)),
                endpoint=overpass.get("endpoint"),
            )
        )

    return result


__all__=["OverturePlaceSource","OverpassSource","build_sources"]
