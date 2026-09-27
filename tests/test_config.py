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
    assert config["runtime"]["health_ledger_enabled"] is True
    assert config["runtime"]["health_ledger_max_events"]==96
    assert config["runtime"]["start_hour"]==8
    assert config["runtime"]["end_hour"]==23
    assert config["runtime"]["timezone"]=="Asia/Karachi"
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
