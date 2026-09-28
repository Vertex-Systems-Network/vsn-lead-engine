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
    assert config["runtime"]["recovery_supervisor_enabled"] is True
    assert config["runtime"]["tail_cycle_extension_enabled"] is True
    assert config["runtime"]["tail_max_cycles_per_run"]==8
    assert config["runtime"]["tail_incomplete_category_threshold"]==4
    assert config["runtime"]["tail_country_yield_routing_enabled"] is True
    assert config["runtime"]["tail_country_yield_incomplete_threshold"]==4
    assert config["runtime"]["tail_country_yield_min_visits"]==4
    assert config["runtime"]["tail_country_yield_preferred_weight"]==2
    assert config["runtime"]["tail_country_yield_advantage_ratio"]==1.5
    assert config["runtime"]["tail_geography_expansion_enabled"] is True
    assert config["runtime"]["tail_geography_expansion_incomplete_threshold"]==4
    assert config["runtime"]["tail_geography_expansion_factor"]==1.5
    assert config["runtime"]["tail_geography_high_completion_ratio"]==0.9
    assert config["runtime"]["tail_geography_high_completion_factor"]==2.0
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


def test_production_config_uses_runtime_default_user_agent():
    config=load_config()
    assert "user_agent" not in config["enrichment"]


def test_explicit_enrichment_user_agent_rejects_header_injection(tmp_path, monkeypatch):
    import json
    import vsn_lead_engine.config as config_module

    production=load_config()
    production["enrichment"]["user_agent"]="safe-agent\nInjected: value"
    path=tmp_path/"runtime.json"
    path.write_text(json.dumps(production),encoding="utf-8")
    monkeypatch.setenv("VSN_RUNTIME_CONFIG",str(path))

    with pytest.raises(ValueError,match="must not contain newlines"):
        config_module.load_config()


@pytest.mark.parametrize(
    "field,value,error",
    [
        (
            "tail_geography_high_completion_ratio",
            1.0,
            "tail_geography_high_completion_ratio",
        ),
        (
            "tail_geography_high_completion_factor",
            1.4,
            "tail_geography_high_completion_factor",
        ),
    ],
)
def test_progressive_tail_config_rejects_unsafe_values(
    tmp_path,
    monkeypatch,
    field,
    value,
    error,
):
    import json
    import vsn_lead_engine.config as config_module

    production=load_config()
    production["runtime"][field]=value
    path=tmp_path/"runtime.json"
    path.write_text(json.dumps(production),encoding="utf-8")
    monkeypatch.setenv("VSN_RUNTIME_CONFIG",str(path))

    with pytest.raises(ValueError,match=error):
        config_module.load_config()
