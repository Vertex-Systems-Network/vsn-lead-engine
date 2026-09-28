from collections import Counter

from vsn_lead_engine.scheduler import (
    build_shard_plan,
    partition_yield_hint_key,
    select_candidate_partition,
)


CATEGORIES=["A","B","C"]
GEOS=[
    {"country":"United States","region":"R1","city":"US1","bbox":[0,0,1,1]},
    {"country":"United States","region":"R2","city":"US2","bbox":[1,1,2,2]},
    {"country":"Canada","region":"R3","city":"CA1","bbox":[2,2,3,3]},
    {"country":"Canada","region":"R4","city":"CA2","bbox":[3,3,4,4]},
]


def first_signature(cursor):
    plan=build_shard_plan(
        CATEGORIES,
        GEOS,
        {"A":0,"B":0,"C":0},
        1000,
        cursor=cursor,
        max_attempts=3,
    )
    first=plan[0]
    return first["category"],first["geography"]["city"]


def test_consecutive_cursors_change_first_shard():
    assert first_signature(10) != first_signature(11)


def test_completed_category_is_skipped():
    plan=build_shard_plan(
        CATEGORIES,
        GEOS,
        {"A":1000,"B":2,"C":2},
        1000,
        cursor=3,
        max_attempts=5,
    )
    assert all(item["category"] != "A" for item in plan)


def test_lower_progress_category_is_prioritized():
    plan=build_shard_plan(
        CATEGORIES,
        GEOS,
        {"A":500,"B":10,"C":400},
        1000,
        cursor=5,
        max_attempts=3,
    )
    assert plan[0]["category"] == "B"


def test_underrepresented_country_is_scheduled_first_and_interleaved():
    plan=build_shard_plan(
        CATEGORIES,
        GEOS,
        {"A":10,"B":20,"C":30},
        1000,
        cursor=7,
        max_attempts=4,
        country_counts={"United States":2876,"Canada":0},
    )
    countries=[item["geography"]["country"] for item in plan]
    assert countries[0]=="Canada"
    assert countries[:4]==["Canada","United States","Canada","United States"]


def test_low_completion_categories_receive_more_shard_slots():
    plan=build_shard_plan(
        CATEGORIES,
        GEOS,
        {"A":10,"B":300,"C":800},
        1000,
        cursor=2,
        max_attempts=6,
        country_counts={"United States":10,"Canada":10},
    )
    counts=Counter(item["category"] for item in plan)
    assert counts["A"] >= counts["B"] >= counts["C"]
    assert counts["A"] >= 3


def test_priority_weight_is_exposed_for_audit():
    plan=build_shard_plan(
        CATEGORIES,
        GEOS,
        {"A":10,"B":300,"C":800},
        1000,
        cursor=1,
        max_attempts=3,
    )
    assert plan[0]["priority_weight"]==6


def test_adaptive_yield_prefers_good_metro_within_country_only():
    hints={
        "a|united states|r1|us1":{
            "visits":1,
            "discovered":100,
            "accepted":0,
        },
        "a|united states|r2|us2":{
            "visits":1,
            "discovered":100,
            "accepted":40,
        },
    }
    plan=build_shard_plan(
        ["A"],
        GEOS,
        {"A":0},
        1000,
        cursor=0,
        max_attempts=4,
        country_counts={"United States":0,"Canada":0},
        yield_hints=hints,
        adaptive_enabled=True,
        exploration_bonus=0.15,
    )

    countries=[item["geography"]["country"] for item in plan]
    assert countries==["United States","Canada","United States","Canada"]
    us_cities=[
        item["geography"]["city"]
        for item in plan
        if item["geography"]["country"]=="United States"
    ]
    assert us_cities==["US2","US1"]
    assert plan[0]["adaptive_yield_score"] > 0.15


def test_adaptive_yield_explores_unseen_before_known_zero_yield_metro():
    hints={
        "a|united states|r1|us1":{
            "visits":1,
            "discovered":100,
            "accepted":0,
        },
    }
    plan=build_shard_plan(
        ["A"],
        GEOS,
        {"A":0},
        1000,
        cursor=0,
        max_attempts=2,
        country_counts={"United States":0,"Canada":1000},
        yield_hints=hints,
        adaptive_enabled=True,
        exploration_bonus=0.15,
    )

    assert plan[0]["geography"]["country"]=="United States"
    assert plan[0]["geography"]["city"]=="US2"
    assert plan[0]["adaptive_yield_score"]==0.15


def test_adaptive_disabled_preserves_rotated_base_order():
    hints={
        "a|united states|r2|us2":{
            "visits":1,
            "discovered":100,
            "accepted":100,
        },
    }
    adaptive=build_shard_plan(
        ["A"],
        GEOS,
        {"A":0},
        1000,
        cursor=0,
        max_attempts=1,
        yield_hints=hints,
        adaptive_enabled=True,
    )
    baseline=build_shard_plan(
        ["A"],
        GEOS,
        {"A":0},
        1000,
        cursor=0,
        max_attempts=1,
        yield_hints=hints,
        adaptive_enabled=False,
    )

    assert adaptive[0]["geography"]["city"]=="US2"
    assert baseline[0]["geography"]["city"]=="US1"
    assert baseline[0]["adaptive_yield_score"] is None


def test_same_day_zero_yield_route_is_deferred_when_alternative_exists():
    blended={
        "a|united states|r1|us1":{
            "visits":8,
            "discovered":400,
            "accepted":0,
        },
        "a|united states|r2|us2":{
            "visits":1,
            "discovered":50,
            "accepted":5,
        },
    }
    daily={
        "a|united states|r1|us1":{
            "visits":4,
            "discovered":120,
            "accepted":0,
            "partition_mask":15,
        },
    }

    plan=build_shard_plan(
        ["A"],
        GEOS,
        {"A":0},
        1000,
        cursor=0,
        max_attempts=4,
        country_counts={"United States":0,"Canada":0},
        yield_hints=blended,
        daily_yield_hints=daily,
        adaptive_enabled=True,
        cooldown_enabled=True,
        cooldown_min_visits=2,
        cooldown_min_discovered=100,
    )

    us_items=[
        item for item in plan
        if item["geography"]["country"]=="United States"
    ]
    assert us_items
    assert all(item["geography"]["city"]=="US2" for item in us_items)
    assert all(item["adaptive_cooldown"] is False for item in us_items)
    assert all(item["adaptive_cooldown_deferred_count"]==1 for item in us_items)


def test_historical_zero_yield_alone_never_triggers_cooldown():
    blended={
        "a|united states|r1|us1":{
            "visits":10,
            "discovered":500,
            "accepted":0,
        },
    }
    plan=build_shard_plan(
        ["A"],
        GEOS,
        {"A":0},
        1000,
        cursor=0,
        max_attempts=4,
        country_counts={"United States":0,"Canada":0},
        yield_hints=blended,
        daily_yield_hints={},
        adaptive_enabled=True,
        cooldown_enabled=True,
    )

    us_cities=[
        item["geography"]["city"]
        for item in plan
        if item["geography"]["country"]=="United States"
    ]
    assert "US1" in us_cities
    assert all(item["adaptive_cooldown_deferred_count"]==0 for item in plan)


def test_all_same_day_routes_cooling_falls_back_without_starvation():
    daily={
        "a|united states|r1|us1":{
            "visits":4,
            "discovered":150,
            "accepted":0,
            "partition_mask":15,
        },
        "a|united states|r2|us2":{
            "visits":4,
            "discovered":200,
            "accepted":0,
            "partition_mask":15,
        },
    }
    plan=build_shard_plan(
        ["A"],
        GEOS,
        {"A":0},
        1000,
        cursor=0,
        max_attempts=4,
        country_counts={"United States":0,"Canada":0},
        yield_hints=daily,
        daily_yield_hints=daily,
        adaptive_enabled=True,
        cooldown_enabled=True,
        cooldown_min_visits=2,
        cooldown_min_discovered=100,
    )

    us_cities=[
        item["geography"]["city"]
        for item in plan
        if item["geography"]["country"]=="United States"
    ]
    assert set(us_cities)=={"US1","US2"}
    assert all(item["adaptive_cooldown_deferred_count"]==0 for item in plan)


def test_route_with_any_acceptance_is_not_cooled():
    daily={
        "a|united states|r1|us1":{
            "visits":5,
            "discovered":500,
            "accepted":1,
        },
    }
    plan=build_shard_plan(
        ["A"],
        GEOS,
        {"A":0},
        1000,
        cursor=0,
        max_attempts=2,
        country_counts={"United States":0,"Canada":1000},
        yield_hints=daily,
        daily_yield_hints=daily,
        adaptive_enabled=True,
        cooldown_enabled=True,
    )
    assert plan[0]["adaptive_cooldown_deferred_count"]==0


def test_weighted_scheduler_covers_all_pending_categories_before_repeats():
    categories=[f"C{index}" for index in range(12)]
    plan=build_shard_plan(
        categories,
        GEOS,
        {category:0 for category in categories},
        1000,
        cursor=0,
        max_attempts=18,
        country_counts={"United States":0,"Canada":0},
    )

    first_pass=[item["category"] for item in plan[:12]]
    assert len(first_pass)==12
    assert set(first_pass)==set(categories)
    assert len(set(item["category"] for item in plan))==12


def test_weight_layers_preserve_rescue_priority_without_clumping():
    plan=build_shard_plan(
        ["A","B","C"],
        GEOS,
        {"A":10,"B":300,"C":800},
        1000,
        cursor=0,
        max_attempts=8,
    )
    assert [item["category"] for item in plan]==[
        "A","B","C","A","B","A","A","A"
    ]


def test_critical_deficit_rescue_gets_large_share_after_fair_first_pass():
    categories=["Critical","Mid","High","Almost"]
    plan=build_shard_plan(
        categories,
        GEOS,
        {
            "Critical":24,
            "Mid":400,
            "High":700,
            "Almost":990,
        },
        1000,
        cursor=0,
        max_attempts=14,
    )

    first_pass=[item["category"] for item in plan[:4]]
    assert set(first_pass)==set(categories)
    counts=Counter(item["category"] for item in plan)
    assert counts["Critical"] >= 6
    assert counts["Critical"] > counts["Mid"]
    assert counts["Mid"] >= counts["High"]


def test_rescue_can_be_disabled_to_preserve_legacy_three_two_one_weights():
    plan=build_shard_plan(
        ["A","B","C"],
        GEOS,
        {"A":10,"B":300,"C":800},
        1000,
        cursor=0,
        max_attempts=6,
        critical_deficit_rescue_enabled=False,
    )
    assert [item["category"] for item in plan]==[
        "A","B","C","A","B","A"
    ]
    assert plan[0]["priority_weight"]==3


def test_fair_weighting_keeps_lowest_progress_first_when_slots_are_tight():
    plan=build_shard_plan(
        ["A","B","C"],
        GEOS,
        {"A":700,"B":10,"C":300},
        1000,
        cursor=0,
        max_attempts=2,
    )
    assert [item["category"] for item in plan]==["B","C"]


def test_zero_yield_route_is_not_cooled_before_partition_floor():
    daily={
        "a|united states|r1|us1":{
            "visits":4,
            "discovered":300,
            "accepted":0,
            "partition_mask":3,
        },
    }
    plan=build_shard_plan(
        ["A"],
        GEOS,
        {"A":0},
        1000,
        cursor=0,
        max_attempts=2,
        country_counts={"United States":0,"Canada":1000},
        yield_hints=daily,
        daily_yield_hints=daily,
        adaptive_enabled=True,
        cooldown_enabled=True,
        cooldown_min_visits=2,
        cooldown_min_discovered=100,
        cooldown_min_partitions=4,
    )
    assert plan[0]["geography"]["city"]=="US2"
    assert all(item["adaptive_cooldown_deferred_count"]==0 for item in plan)


def test_zero_yield_route_cools_after_four_distinct_partitions():
    daily={
        "a|united states|r1|us1":{
            "visits":4,
            "discovered":300,
            "accepted":0,
            "partition_mask":15,
        },
    }
    plan=build_shard_plan(
        ["A"],
        GEOS,
        {"A":0},
        1000,
        cursor=0,
        max_attempts=2,
        country_counts={"United States":0,"Canada":1000},
        yield_hints=daily,
        daily_yield_hints=daily,
        adaptive_enabled=True,
        cooldown_enabled=True,
        cooldown_min_visits=2,
        cooldown_min_discovered=100,
        cooldown_min_partitions=4,
    )
    assert plan[0]["geography"]["city"]=="US2"
    assert all(item["adaptive_cooldown_deferred_count"]==1 for item in plan)


def test_partition_key_is_scoped_to_category_market_and_partition():
    geo=GEOS[0]
    assert partition_yield_hint_key("Motorbikes",geo,3)==(
        "motorbikes|united states|r1|us1|partition:3"
    )


def test_partition_routing_prefers_productive_partition_over_rotated_base():
    geo=GEOS[0]
    hints={
        partition_yield_hint_key("Motorbikes",geo,0):{
            "visits":3,
            "discovered":90,
            "accepted":0,
        },
        partition_yield_hint_key("Motorbikes",geo,1):{
            "visits":2,
            "discovered":80,
            "accepted":40,
        },
    }
    partition,score=select_candidate_partition(
        "Motorbikes",
        geo,
        partition_count=4,
        cursor=0,
        attempt=1,
        yield_hints=hints,
        adaptive_enabled=True,
        exploration_bonus=0.15,
    )
    assert partition==1
    assert score > 0.5


def test_partition_routing_explores_unseen_before_known_zero_yield():
    geo=GEOS[0]
    hints={
        partition_yield_hint_key("Motorbikes",geo,0):{
            "visits":4,
            "discovered":120,
            "accepted":0,
        },
    }
    partition,score=select_candidate_partition(
        "Motorbikes",
        geo,
        partition_count=4,
        cursor=0,
        attempt=1,
        yield_hints=hints,
        adaptive_enabled=True,
        exploration_bonus=0.15,
    )
    assert partition==1
    assert score==0.15


def test_partition_routing_can_be_disabled_for_deterministic_rotation():
    geo=GEOS[0]
    hints={
        partition_yield_hint_key("Motorbikes",geo,2):{
            "visits":1,
            "discovered":50,
            "accepted":50,
        },
    }
    partition,score=select_candidate_partition(
        "Motorbikes",
        geo,
        partition_count=4,
        cursor=5,
        attempt=2,
        yield_hints=hints,
        adaptive_enabled=False,
    )
    assert partition==2
    assert score is None


def test_throughput_scoring_prefers_more_accepted_leads_per_shard():
    hints={
        "a|united states|r1|us1":{
            "visits":1,
            "discovered":2,
            "accepted":2,
        },
        "a|united states|r2|us2":{
            "visits":1,
            "discovered":40,
            "accepted":30,
        },
    }
    plan=build_shard_plan(
        ["A"],
        GEOS,
        {"A":0},
        1000,
        cursor=0,
        max_attempts=1,
        country_counts={"United States":0,"Canada":1000},
        yield_hints=hints,
        adaptive_enabled=True,
        adaptive_score_mode="throughput",
    )
    assert plan[0]["geography"]["city"]=="US2"


def test_conversion_score_mode_preserves_legacy_ratio_ranking():
    hints={
        "a|united states|r1|us1":{
            "visits":1,
            "discovered":2,
            "accepted":2,
        },
        "a|united states|r2|us2":{
            "visits":1,
            "discovered":40,
            "accepted":30,
        },
    }
    plan=build_shard_plan(
        ["A"],
        GEOS,
        {"A":0},
        1000,
        cursor=0,
        max_attempts=1,
        country_counts={"United States":0,"Canada":1000},
        yield_hints=hints,
        adaptive_enabled=True,
        adaptive_score_mode="conversion",
    )
    assert plan[0]["geography"]["city"]=="US1"


def test_partition_throughput_prefers_large_survivor_cohort():
    geo=GEOS[0]
    hints={
        partition_yield_hint_key("Motorbikes",geo,0):{
            "visits":1,
            "discovered":2,
            "accepted":2,
        },
        partition_yield_hint_key("Motorbikes",geo,1):{
            "visits":1,
            "discovered":40,
            "accepted":30,
        },
    }
    partition,score=select_candidate_partition(
        "Motorbikes",
        geo,
        partition_count=2,
        cursor=0,
        attempt=1,
        yield_hints=hints,
        adaptive_enabled=True,
        exploration_bonus=0.15,
        score_mode="throughput",
    )
    assert partition==1
    assert score > 20


def test_partition_exhaustion_cooldown_skips_proven_zero_unique_partition():
    geo=GEOS[0]
    hints={
        partition_yield_hint_key("Motorbikes",geo,0):{
            "visits":3,
            "discovered":80,
            "accepted":0,
        },
        partition_yield_hint_key("Motorbikes",geo,1):{
            "visits":2,
            "discovered":30,
            "accepted":5,
        },
    }
    partition,score=select_candidate_partition(
        "Motorbikes",
        geo,
        partition_count=4,
        cursor=0,
        attempt=1,
        yield_hints=hints,
        adaptive_enabled=True,
        exhaustion_cooldown_enabled=True,
        exhaustion_min_visits=2,
        exhaustion_min_discovered=20,
    )
    assert partition != 0
    assert score is not None


def test_partition_exhaustion_cooldown_requires_evidence_floor():
    geo=GEOS[0]
    hints={
        partition_yield_hint_key("Motorbikes",geo,0):{
            "visits":1,
            "discovered":100,
            "accepted":0,
        },
        partition_yield_hint_key("Motorbikes",geo,1):{
            "visits":4,
            "discovered":5,
            "accepted":0,
        },
    }
    partition,_=select_candidate_partition(
        "Motorbikes",
        geo,
        partition_count=2,
        cursor=0,
        attempt=1,
        yield_hints=hints,
        adaptive_enabled=True,
        exhaustion_cooldown_enabled=True,
        exhaustion_min_visits=2,
        exhaustion_min_discovered=20,
    )
    assert partition in {0,1}


def test_partition_exhaustion_cooldown_falls_back_when_all_are_exhausted():
    geo=GEOS[0]
    hints={
        partition_yield_hint_key("Motorbikes",geo,0):{
            "visits":3,
            "discovered":80,
            "accepted":0,
        },
        partition_yield_hint_key("Motorbikes",geo,1):{
            "visits":2,
            "discovered":40,
            "accepted":0,
        },
    }
    partition,score=select_candidate_partition(
        "Motorbikes",
        geo,
        partition_count=2,
        cursor=0,
        attempt=1,
        yield_hints=hints,
        adaptive_enabled=True,
        exhaustion_cooldown_enabled=True,
        exhaustion_min_visits=2,
        exhaustion_min_discovered=20,
    )
    assert partition in {0,1}
    assert score is not None


def test_partition_exhaustion_cooldown_can_be_disabled():
    geo=GEOS[0]
    hints={
        partition_yield_hint_key("Motorbikes",geo,0):{
            "visits":3,
            "discovered":80,
            "accepted":0,
        },
    }
    partition,_=select_candidate_partition(
        "Motorbikes",
        geo,
        partition_count=2,
        cursor=0,
        attempt=1,
        yield_hints=hints,
        adaptive_enabled=True,
        exhaustion_cooldown_enabled=False,
    )
    assert partition in {0,1}
