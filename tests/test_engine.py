import vsn_lead_engine.engine as engine
from vsn_lead_engine.engine import _candidate_partition_geography, _quality_summary, _search_with_retry, _update_yield_hints, _yield_hint_summary, check_workbook_readiness, recover_workbook_readiness


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


def test_run_until_quota_tries_bounded_rotated_cycles_after_zero_acceptance(monkeypatch):
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
            "max_zero_progress_cycles":3,
        },
        "categories":["A"],
    }

    result=engine.run_until_quota(config)
    assert result["cycles_executed"]==3
    assert result["zero_progress_streak"]==3
    assert [call["cursor_offset"] for call in calls]==[0,1,2]
    assert source.closed


def test_run_until_quota_zero_progress_streak_resets_after_progress(monkeypatch):
    source=FakeClosableSource()
    monkeypatch.setattr(engine,"build_sources",lambda config:[source])
    monkeypatch.setattr(engine,"GoogleSheetsStore",lambda config,run_date=None:object())

    results=[
        {
            "status":"ok",
            "accepted":0,
            "counts":{"A":100},
            "country_counts":{"United States":100,"Canada":0},
        },
        {
            "status":"ok",
            "accepted":10,
            "counts":{"A":110},
            "country_counts":{"United States":110,"Canada":0},
        },
        {
            "status":"ok",
            "accepted":0,
            "counts":{"A":110},
            "country_counts":{"United States":110,"Canada":0},
        },
    ]
    calls=[]

    def fake_run_once(config, dry_run=False, **kwargs):
        calls.append(kwargs)
        return results[len(calls)-1]

    monkeypatch.setattr(engine,"run_once",fake_run_once)
    config={
        "runtime":{
            "timezone":"Asia/Karachi",
            "daily_target_per_category":1000,
            "max_cycles_per_run":3,
            "max_zero_progress_cycles":2,
        },
        "categories":["A"],
    }

    result=engine.run_until_quota(config)
    assert result["cycles_executed"]==3
    assert result["accepted"]==10
    assert result["zero_progress_streak"]==1
    assert source.closed


def test_candidate_partition_rotates_with_cursor_and_attempt():
    geography={"country":"United States","region":"Texas","city":"Austin"}
    first=_candidate_partition_geography(
        geography,
        cursor=10,
        attempt=1,
        partition_count=8,
    )
    second=_candidate_partition_geography(
        geography,
        cursor=10,
        attempt=2,
        partition_count=8,
    )
    next_cycle=_candidate_partition_geography(
        geography,
        cursor=11,
        attempt=1,
        partition_count=8,
    )

    assert first["_candidate_partition_count"]==8
    assert first["_candidate_partition"]==2
    assert second["_candidate_partition"]==3
    assert next_cycle["_candidate_partition"]==3
    assert geography=={"country":"United States","region":"Texas","city":"Austin"}


def test_quality_summary_calculates_acceptance_enrichment_and_partitions():
    summary=_quality_summary(
        discovered=200,
        accepted=50,
        rejections={"duplicate":100,"missing_or_invalid_phone":50},
        enrichment={
            "candidates":40,
            "live_phone_recovered":6,
            "common_crawl_phone_recovered":2,
            "common_crawl_attempted":8,
            "skipped_budget":5,
            "errors":1,
        },
        attempts=[
            {
                "sources":[
                    {
                        "source":"Overture Maps Places",
                        "candidate_partition":2,
                    },
                    {
                        "source":"Overture Maps Places",
                        "candidate_partition":3,
                    },
                ]
            },
            {
                "sources":[
                    {
                        "source":"Overture Maps Places",
                        "candidate_partition":2,
                    }
                ]
            },
        ],
    )

    assert summary["acceptance_rate_pct"]==25.0
    assert summary["phone_recovery_rate_pct"]==20.0
    assert summary["phones_recovered"]==8
    assert summary["official_site_phone_recoveries"]==6
    assert summary["common_crawl_phone_recoveries"]==2
    assert summary["partitions_visited"]==2
    assert summary["enrichment_budget_skips"]==5
    assert summary["enrichment_errors"]==1


def test_quality_summary_handles_zero_denominators():
    summary=_quality_summary(
        discovered=0,
        accepted=0,
        rejections={},
        enrichment={},
        attempts=[],
    )
    assert summary["acceptance_rate_pct"]==0.0
    assert summary["phone_recovery_rate_pct"]==0.0
    assert summary["partitions_visited"]==0


def test_workbook_readiness_resolves_counts_and_quota_state():
    class FakeStore:
        def ensure_lead_workbook(self):
            return {
                "id":"sheet-123",
                "name":"US + Canada Business Leads — 2026-09-28",
                "webViewLink":"https://docs.google.com/spreadsheets/d/sheet-123/edit",
                "created":True,
            }

        def category_counts(self, spreadsheet_id):
            assert spreadsheet_id=="sheet-123"
            return {"A":1000,"B":999}

        def daily_country_counts(self, spreadsheet_id):
            assert spreadsheet_id=="sheet-123"
            return {"United States":1200,"Canada":799}

    result=check_workbook_readiness(
        {
            "runtime":{
                "timezone":"Asia/Karachi",
                "daily_target_per_category":1000,
            },
            "categories":["A","B"],
        },
        run_date="2026-09-28",
        store=FakeStore(),
    )

    assert result["status"]=="ready"
    assert result["run_date"]=="2026-09-28"
    assert result["workbook"]["created"] is True
    assert result["counts"]=={"A":1000,"B":999}
    assert result["country_counts"]["Canada"]==799
    assert result["quota_complete"] is False


def test_workbook_readiness_marks_complete_only_when_all_categories_hit_target():
    class FakeStore:
        def ensure_lead_workbook(self):
            return {"id":"sheet-456","name":"daily","created":False}

        def category_counts(self, spreadsheet_id):
            return {"A":1000,"B":1001}

        def daily_country_counts(self, spreadsheet_id):
            return {"United States":1000,"Canada":1001}

    result=check_workbook_readiness(
        {
            "runtime":{
                "timezone":"Asia/Karachi",
                "daily_target_per_category":1000,
            },
            "categories":["A","B"],
        },
        run_date="2026-09-28",
        store=FakeStore(),
    )
    assert result["quota_complete"] is True


def test_workbook_readiness_recovery_succeeds_after_transient_failure():
    calls=[]
    sleeps=[]

    def fake_check(config,run_date=None):
        calls.append(run_date)
        if len(calls)==1:
            raise RuntimeError("temporary Google API failure")
        return {
            "status":"ready",
            "run_date":run_date,
            "workbook":{"id":"sheet-1","name":"daily","created":False},
            "counts":{"A":0},
            "country_counts":{"United States":0,"Canada":0},
            "quota_complete":False,
        }

    result=recover_workbook_readiness(
        {
            "runtime":{
                "timezone":"Asia/Karachi",
                "daily_target_per_category":1000,
            },
            "categories":["A"],
        },
        run_date="2026-09-28",
        attempts=3,
        delay_seconds=5,
        sleep_fn=sleeps.append,
        check_fn=fake_check,
    )

    assert result["status"]=="recovered"
    assert result["attempts_used"]==2
    assert result["attempts_configured"]==3
    assert len(result["failures"])==1
    assert result["failures"][0]["error_type"]=="RuntimeError"
    assert calls==["2026-09-28","2026-09-28"]
    assert sleeps==[5]


def test_workbook_readiness_recovery_returns_incident_after_bound_exhausted():
    sleeps=[]

    def always_fail(config,run_date=None):
        raise PermissionError("service account cannot create dated workbook")

    result=recover_workbook_readiness(
        {
            "runtime":{
                "timezone":"Asia/Karachi",
                "daily_target_per_category":1000,
            },
            "categories":["A"],
        },
        run_date="2026-09-28",
        attempts=3,
        delay_seconds=2,
        sleep_fn=sleeps.append,
        check_fn=always_fail,
    )

    assert result["status"]=="incident"
    assert result["attempts_used"]==3
    assert len(result["failures"])==3
    assert result["last_error"]["error_type"]=="PermissionError"
    assert "cannot create" in result["last_error"]["message"]
    assert result["quota_complete"] is False
    assert sleeps==[2,2]


def test_workbook_readiness_recovery_first_attempt_reports_ready_without_sleep():
    sleeps=[]

    def ready(config,run_date=None):
        return {
            "status":"ready",
            "run_date":run_date,
            "workbook":{"id":"sheet-1","name":"daily","created":False},
            "counts":{"A":1000},
            "country_counts":{"United States":500,"Canada":500},
            "quota_complete":True,
        }

    result=recover_workbook_readiness(
        {
            "runtime":{
                "timezone":"Asia/Karachi",
                "daily_target_per_category":1000,
            },
            "categories":["A"],
        },
        run_date="2026-09-28",
        attempts=3,
        delay_seconds=60,
        sleep_fn=sleeps.append,
        check_fn=ready,
    )

    assert result["status"]=="ready"
    assert result["attempts_used"]==1
    assert result["failures"]==[]
    assert result["quota_complete"] is True
    assert sleeps==[]


def test_yield_hints_accumulate_shard_history():
    hints={}
    _update_yield_hints(
        hints,
        [
            {
                "category":"IT & Software",
                "geography":{
                    "country":"United States",
                    "region":"Texas",
                    "city":"Austin",
                },
                "discovered":100,
                "accepted":20,
            },
            {
                "category":"IT & Software",
                "geography":{
                    "country":"United States",
                    "region":"Texas",
                    "city":"Austin",
                },
                "discovered":50,
                "accepted":5,
            },
        ],
    )

    assert hints[
        "it & software|united states|texas|austin"
    ]=={
        "visits":2,
        "discovered":150,
        "accepted":25,
    }
    assert _yield_hint_summary(hints)=={
        "markets_observed":1,
        "visits":2,
        "discovered":150,
        "accepted":25,
    }


def test_run_until_quota_passes_learned_yield_to_next_cycle(monkeypatch):
    source=FakeClosableSource()
    monkeypatch.setattr(engine,"build_sources",lambda config:[source])
    monkeypatch.setattr(engine,"GoogleSheetsStore",lambda config,run_date=None:object())

    snapshots=[]

    results=[
        {
            "status":"ok",
            "accepted":20,
            "counts":{"A":20},
            "country_counts":{"United States":20,"Canada":0},
            "attempts":[
                {
                    "category":"A",
                    "geography":{
                        "country":"United States",
                        "region":"R1",
                        "city":"US1",
                    },
                    "discovered":100,
                    "accepted":20,
                }
            ],
        },
        {
            "status":"complete",
            "accepted":980,
            "counts":{"A":1000},
            "country_counts":{"United States":1000,"Canada":0},
            "attempts":[],
        },
    ]

    def fake_run_once(config,dry_run=False,**kwargs):
        snapshots.append({
            key:dict(value) if isinstance(value,dict) else value
            for key,value in (kwargs.get("yield_hints") or {}).items()
        })
        return results[len(snapshots)-1]

    monkeypatch.setattr(engine,"run_once",fake_run_once)
    config={
        "runtime":{
            "timezone":"Asia/Karachi",
            "daily_target_per_category":1000,
            "max_cycles_per_run":3,
            "max_zero_progress_cycles":3,
        },
        "categories":["A"],
    }

    result=engine.run_until_quota(config)

    assert snapshots[0]=={}
    assert snapshots[1][
        "a|united states|r1|us1"
    ]=={
        "visits":1,
        "discovered":100,
        "accepted":20,
    }
    assert result["adaptive_yield"]=={
        "markets_observed":1,
        "visits":1,
        "discovered":100,
        "accepted":20,
    }
    assert source.closed
