import vsn_lead_engine.engine as engine
from vsn_lead_engine.engine import _search_with_retry


class FlakySource:
    def __init__(self, failures):
        self.failures=failures
        self.calls=0

    def search(self, category, geography, limit):
        self.calls+=1
        if self.calls<=self.failures:
            raise RuntimeError("temporary")
        return ["lead"]


def test_source_search_retries_then_succeeds():
    source=FlakySource(2)
    candidates,error,retries=_search_with_retry(
        source,
        "IT & Software",
        {"country":"Canada"},
        limit=10,
        attempts=3,
        backoff_seconds=0,
    )
    assert candidates==["lead"]
    assert error==""
    assert retries==2
    assert source.calls==3


def test_source_search_stops_after_retry_budget():
    source=FlakySource(5)
    candidates,error,retries=_search_with_retry(
        source,
        "IT & Software",
        {"country":"Canada"},
        limit=10,
        attempts=3,
        backoff_seconds=0,
    )
    assert candidates==[]
    assert "RuntimeError: temporary" in error
    assert retries==2
    assert source.calls==3


class FakeClosableSource:
    def __init__(self):
        self.closed=False

    def close(self):
        self.closed=True


def test_run_until_quota_reuses_process_and_stops_on_complete(monkeypatch):
    source=FakeClosableSource()
    monkeypatch.setattr(engine,"build_sources",lambda config:[source])

    class FakeStore:
        def __init__(self, config, run_date=None):
            self.run_date=run_date

    monkeypatch.setattr(engine,"GoogleSheetsStore",FakeStore)

    categories=["A","B"]
    calls=[]
    results=[
        {
            "status":"ok",
            "accepted":1000,
            "counts":{"A":1000,"B":500},
            "country_counts":{"United States":1000,"Canada":500},
        },
        {
            "status":"ok",
            "accepted":500,
            "counts":{"A":1000,"B":1000},
            "country_counts":{"United States":1200,"Canada":800},
        },
    ]

    def fake_run_once(config, dry_run=False, **kwargs):
        calls.append(kwargs)
        return results[len(calls)-1]

    monkeypatch.setattr(engine,"run_once",fake_run_once)
    config={
        "runtime":{
            "timezone":"Asia/Karachi",
            "daily_target_per_category":1000,
            "max_cycles_per_run":3,
        },
        "categories":categories,
    }

    result=engine.run_until_quota(config)
    assert result["status"]=="complete"
    assert result["cycles_executed"]==2
    assert result["accepted"]==1500
    assert calls[0]["sources"] is calls[1]["sources"]
    assert calls[0]["store"] is calls[1]["store"]
    assert calls[0]["run_date"]==calls[1]["run_date"]
    assert calls[0]["cursor_offset"]==0
    assert calls[1]["cursor_offset"]==1
    assert source.closed


def test_run_until_quota_stops_on_zero_acceptance(monkeypatch):
    source=FakeClosableSource()
    monkeypatch.setattr(engine,"build_sources",lambda config:[source])
    monkeypatch.setattr(engine,"GoogleSheetsStore",lambda config,run_date=None:object())

    calls=[]

    def fake_run_once(config, dry_run=False, **kwargs):
        calls.append(kwargs)
        return {
            "status":"ok",
            "accepted":0,
            "counts":{"A":100},
            "country_counts":{"United States":100,"Canada":0},
        }

    monkeypatch.setattr(engine,"run_once",fake_run_once)
    config={
        "runtime":{
            "timezone":"Asia/Karachi",
            "daily_target_per_category":1000,
            "max_cycles_per_run":3,
        },
        "categories":["A"],
    }

    result=engine.run_until_quota(config)
    assert result["cycles_executed"]==1
    assert len(calls)==1
    assert source.closed
