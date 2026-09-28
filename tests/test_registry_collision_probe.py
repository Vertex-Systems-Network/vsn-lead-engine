from types import SimpleNamespace

from vsn_lead_engine import registry_collision_probe


def _config():
    return {
        "runtime":{
            "candidate_partition_count":16,
            "candidate_limit_per_shard":500,
        },
        "sources":{
            "overture":{
                "enabled":True,
                "release":"2026-09-23.1",
                "candidate_limit":500,
                "website_candidate_reserve_fraction":0.2,
                "query_timeout_seconds":45,
            }
        },
        "registry":{"mode":"r2","layout":"packed-v2"},
        "geographies":[
            {"country":"United States","region":"Arizona","city":"Phoenix","bbox":[-113,33,-111,34]},
            {"country":"Canada","region":"Alberta","city":"Calgary","bbox":[-115,50,-113,52]},
        ],
    }


def test_registry_collision_probe_is_read_only_and_counts_survivors(monkeypatch):
    leads=[
        SimpleNamespace(
            phone="+12025550100",
            country="United States",
            website="https://one.test",
            google_place_id="",
            source_id="source-1",
            business_name="One Moto",
            city="Phoenix",
            region="Arizona",
        ),
        SimpleNamespace(
            phone="+12025550101",
            country="United States",
            website="https://two.test",
            google_place_id="",
            source_id="source-2",
            business_name="Two Moto",
            city="Phoenix",
            region="Arizona",
        ),
    ]

    class FakeSource:
        def __init__(self,**kwargs):
            pass
        def _resolve_release(self):
            return "2026-09-23.1"
        def search(self,category,geography,limit=None):
            return list(leads)
        def close(self):
            pass

    class FakeIndex:
        def __init__(self):
            self.calls=0
        def collision_keys(self,items):
            self.calls+=1
            first=fingerprints(items[0])
            return {fingerprint_token("u",first.unique)}
        def close(self):
            pass

    index=FakeIndex()
    monkeypatch.setattr(
        registry_collision_probe,
        "OverturePlaceSource",
        FakeSource,
    )
    monkeypatch.setattr(
        registry_collision_probe,
        "build_registry_index",
        lambda config:index,
    )

    result=registry_collision_probe.probe_motorbike_registry_collisions(
        _config(),
        max_geographies=1,
        partitions_per_geography=1,
    )

    assert result["status"]=="ok"
    assert result["total_candidates"]==2
    assert result["total_collisions"]==1
    assert result["total_survivors"]==1
    assert result["collision_rate_pct"]==50.0
    assert result["write_operations"]==0
    assert index.calls==1


from vsn_lead_engine.dedupe import fingerprints
from vsn_lead_engine.registry import fingerprint_token
