import pytest

from vsn_lead_engine.config import _validate_geographies, load_config


def test_production_free_source_breadth_is_expanded():
    config=load_config()
    assert config["runtime"]["candidate_partition_count"]==16
    assert config["runtime"]["adaptive_yield_routing"] is True
    assert config["runtime"]["adaptive_yield_exploration_bonus"]==0.15
    assert config["runtime"]["adaptive_yield_persist_daily"] is True
    assert config["runtime"]["adaptive_yield_state_max_entries"]==1500
    assert config["runtime"]["adaptive_yield_history_enabled"] is True
    assert config["runtime"]["adaptive_yield_history_weight"]==0.25
    assert config["runtime"]["adaptive_yield_history_decay"]==0.75
    assert config["runtime"]["adaptive_yield_history_max_entries"]==1500
    assert config["runtime"]["adaptive_zero_yield_cooldown_enabled"] is True
    assert config["runtime"]["adaptive_zero_yield_cooldown_min_visits"]==2
    assert config["runtime"]["adaptive_zero_yield_cooldown_min_discovered"]==100
    assert config["runtime"]["adaptive_zero_yield_cooldown_min_partitions"]==4
    assert config["runtime"]["r2_pre_enrichment_prefilter_enabled"] is True
    assert config["runtime"]["source_batch_dedupe_enabled"] is True
    assert config["runtime"]["precreated_workbook_bootstrap_enabled"] is True
    assert config["runtime"]["health_ledger_enabled"] is True
    assert config["registry"]["read_cache_enabled"] is True
    assert config["registry"]["read_cache_max_entries"]==128
    assert config["registry"]["legacy_read_cache_max_entries"]==4096
    assert config["registry"]["pending_read_cache_enabled"] is True
    assert config["sources"]["overture"]["query_timeout_seconds"]==45
    assert config["runtime"]["event_wall_time_seconds"]==1500
    assert config["runtime"]["event_deadline_guard_seconds"]==60
    assert config["runtime"]["health_ledger_max_events"]==96
    assert config["runtime"]["start_hour"]==8
    assert config["runtime"]["end_hour"]==23
    assert config["runtime"]["timezone"]=="Asia/Karachi"
    assert config["sources"]["overture"]["website_candidate_reserve_fraction"]==0.20
    assert config["enrichment"]["max_candidates_per_run"]==160
    assert config["enrichment"]["max_candidates_per_call"]==12
    assert config["enrichment"]["common_crawl"]["max_lookups_per_run"]==8
    assert config["enrichment"]["common_crawl"]["max_lookups_per_call"]==1
    assert len(config["geographies"])>=56
    cities={geo["city"] for geo in config["geographies"]}
    assert {
        "New York City",
        "San Francisco",
        "San Jose",
        "Washington",
        "Mississauga",
        "Quebec City",
    }.issubset(cities)


def test_geography_validation_rejects_duplicate_market():
    geographies=[
        {
            "country":"United States",
            "region":"New York",
            "city":"New York City",
            "bbox":[-74.30,40.45,-73.65,40.95],
        },
        {
            "country":"United States",
            "region":"New York",
            "city":"New York City",
            "bbox":[-74.20,40.50,-73.70,40.90],
        },
    ]
    with pytest.raises(ValueError,match="Duplicate geography"):
        _validate_geographies(geographies)


def test_geography_validation_rejects_unsupported_country():
    with pytest.raises(ValueError,match="Unsupported geography country"):
        _validate_geographies([
            {
                "country":"Mexico",
                "region":"Nuevo Leon",
                "city":"Monterrey",
                "bbox":[-100.6,25.4,-99.9,26.0],
            }
        ])


@pytest.mark.parametrize(
    "bbox,error",
    [
        ([-181,40,-73,41],"Longitude outside valid range"),
        ([-74,-91,-73,41],"Latitude outside valid range"),
        ([-73,40,-74,41],"Invalid bbox order"),
    ],
)
def test_geography_validation_rejects_invalid_bounds(bbox,error):
    with pytest.raises(ValueError,match=error):
        _validate_geographies([
            {
                "country":"Canada",
                "region":"Ontario",
                "city":"Example",
                "bbox":bbox,
            }
        ])
