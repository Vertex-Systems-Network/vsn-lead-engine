from vsn_lead_engine.scheduler import build_shard_plan


CATEGORIES=["A","B","C"]
GEOS=[
    {"country":"United States","region":"R1","city":"C1","bbox":[0,0,1,1]},
    {"country":"United States","region":"R2","city":"C2","bbox":[1,1,2,2]},
    {"country":"Canada","region":"R3","city":"C3","bbox":[2,2,3,3]},
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
