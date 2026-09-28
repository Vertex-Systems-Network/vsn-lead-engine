from types import SimpleNamespace

from vsn_lead_engine import source_probe


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
        "geographies":[
            {"country":"United States","region":"Arizona","city":"Phoenix","bbox":[-113,33,-111,34]},
            {"country":"Canada","region":"Alberta","city":"Calgary","bbox":[-115,50,-113,52]},
            {"country":"United States","region":"California","city":"Los Angeles","bbox":[-119,33,-117,35]},
            {"country":"Canada","region":"Alberta","city":"Edmonton","bbox":[-114,53,-113,54]},
        ],
    }


def test_probe_uses_production_partition_shape_and_aggregates_only(monkeypatch):
    calls=[]

    class FakeSource:
        def __init__(self,**kwargs):
            self.kwargs=kwargs
        def _resolve_release(self):
            return "2026-09-23.1"
        def search(self,category,geography,limit=None):
            calls.append((category,geography,limit))
            return [
                SimpleNamespace(phone="+12025550100",website="https://example.test"),
                SimpleNamespace(phone="",website="https://website-only.test"),
            ]
        def close(self):
            pass

    monkeypatch.setattr(source_probe,"OverturePlaceSource",FakeSource)
    result=source_probe.probe_motorbike_source(
        _config(),
        max_geographies=2,
        partitions_per_geography=2,
    )

    assert result["status"]=="ok"
    assert result["queries"]==4
    assert result["total_candidates"]==8
    assert result["total_phone_candidates"]==4
    assert result["total_website_only_candidates"]==4
    assert result["write_operations"]==0
    assert all(call[0]=="Motorbikes" for call in calls)
    assert all(call[1]["_candidate_partition_count"]==16 for call in calls)
    assert all(call[2]==500 for call in calls)
    assert all("business_name" not in probe for probe in result["probes"])


def test_probe_records_source_error_without_writes(monkeypatch):
    class FakeSource:
        def __init__(self,**kwargs):
            pass
        def _resolve_release(self):
            return "2026-09-23.1"
        def search(self,category,geography,limit=None):
            raise TimeoutError("bounded timeout")
        def close(self):
            pass

    monkeypatch.setattr(source_probe,"OverturePlaceSource",FakeSource)
    result=source_probe.probe_motorbike_source(
        _config(),
        max_geographies=1,
        partitions_per_geography=1,
    )

    assert result["status"]=="probe-failed"
    assert result["failed_queries"]==1
    assert result["probes"][0]["error_type"]=="TimeoutError"
    assert result["write_operations"]==0
