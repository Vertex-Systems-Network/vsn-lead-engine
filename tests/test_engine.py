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
