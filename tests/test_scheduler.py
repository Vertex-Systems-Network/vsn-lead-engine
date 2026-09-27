from collections import Counter

from vsn_lead_engine.scheduler import build_shard_plan


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
    assert plan[0]["priority_weight"]==3
