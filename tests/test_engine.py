import vsn_lead_engine.engine as engine
from vsn_lead_engine.engine import _candidate_partition_geography, _critical_search_geography, _deadline_is_near, _dedupe_source_batch, _quality_summary, _search_with_retry, _source_contact_mix, _update_yield_hints, _yield_hint_summary, check_workbook_readiness, recover_workbook_readiness
from vsn_lead_engine.models import Lead


class FlakySource:
    def __init__(self, failures):
        self.failures=failures
        self.calls=0

    def search(self, category, geography, limit):
        self.calls+=1
        if self.calls<=self.failures:
            raise RuntimeError("temporary")
        return ["lead"]


def test_deadline_helper_respects_guard(monkeypatch):
    values=iter([100.0,100.0,100.0])
    monkeypatch.setattr(engine.time,"monotonic",lambda:next(values))
    assert _deadline_is_near(None,60) is False
    assert _deadline_is_near(170.0,60) is False
    assert _deadline_is_near(160.0,60) is True


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




class TimeoutSource:
    def __init__(self):
        self.calls=0

    def search(self, category, geography, limit):
        self.calls+=1
        raise TimeoutError("source wall clock exceeded")


def test_source_search_timeout_is_not_retried():
    source=TimeoutSource()
    candidates,error,retries=_search_with_retry(
        source,
        "IT & Software",
        {"country":"Canada"},
        limit=10,
        attempts=3,
        backoff_seconds=0,
    )
    assert candidates==[]
    assert "TimeoutError: source wall clock exceeded" in error
    assert retries==0
    assert source.calls==1


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


def test_run_until_quota_stops_cleanly_on_event_budget(monkeypatch):
    source=FakeClosableSource()
    monkeypatch.setattr(engine,"build_sources",lambda config:[source])
    monkeypatch.setattr(engine,"GoogleSheetsStore",lambda config,run_date=None:object())

    calls=[]
    def fake_run_once(config,dry_run=False,**kwargs):
        calls.append(kwargs)
        return {
            "status":"ok",
            "accepted":25,
            "counts":{"A":125},
            "country_counts":{"United States":125,"Canada":0},
            "event_budget_exhausted":True,
        }

    monkeypatch.setattr(engine,"run_once",fake_run_once)
    config={
        "runtime":{
            "timezone":"Asia/Karachi",
            "daily_target_per_category":1000,
            "max_cycles_per_run":3,
            "max_zero_progress_cycles":3,
            "event_wall_time_seconds":1500,
            "event_deadline_guard_seconds":60,
        },
        "categories":["A"],
    }

    result=engine.run_until_quota(config)
    assert result["status"]=="partial-budget"
    assert result["cycles_executed"]==1
    assert result["accepted"]==25
    assert result["event_budget_exhausted"] is True
    assert calls[0]["deadline_monotonic"] is not None
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
        "partitions_observed":0,
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
        "partitions_observed":0,
    }
    assert source.closed


def test_run_until_quota_loads_and_saves_daily_yield_state_once(monkeypatch):
    source=FakeClosableSource()
    monkeypatch.setattr(engine,"build_sources",lambda config:[source])
    monkeypatch.setattr(engine,"GoogleSheetsStore",lambda config,run_date=None:object())

    class FakeRegistry:
        def close(self):
            pass

    registry=FakeRegistry()
    monkeypatch.setattr(engine,"build_registry_index",lambda config:registry)
    monkeypatch.setattr(engine,"build_contact_enricher",lambda config:None)

    state_events={"loads":0,"saves":[]}

    class FakeStateStore:
        def __init__(self, registry_index, max_entries=1500):
            assert registry_index is registry
            assert max_entries==1500

        def load(self, run_date):
            state_events["loads"]+=1
            return (
                {
                    "a|united states|r1|us1":{
                        "visits":2,
                        "discovered":100,
                        "accepted":20,
                    }
                },
                {
                    "status":"loaded",
                    "key":f"state/{run_date}.json",
                    "entries":1,
                    "bytes":100,
                },
            )

        def save(self, run_date, hints):
            state_events["saves"].append((run_date,{
                key:dict(value) for key,value in hints.items()
            }))
            return {
                "status":"saved",
                "key":f"state/{run_date}.json",
                "entries":len(hints),
                "bytes":120,
            }

    monkeypatch.setattr(engine,"DailyYieldStateStore",FakeStateStore)

    snapshots=[]
    results=[
        {
            "status":"ok",
            "accepted":10,
            "counts":{"A":10},
            "country_counts":{"United States":10,"Canada":0},
            "attempts":[
                {
                    "category":"A",
                    "geography":{
                        "country":"United States",
                        "region":"R1",
                        "city":"US1",
                    },
                    "discovered":50,
                    "accepted":10,
                }
            ],
        },
        {
            "status":"complete",
            "accepted":990,
            "counts":{"A":1000},
            "country_counts":{"United States":1000,"Canada":0},
            "attempts":[],
        },
    ]

    def fake_run_once(config,dry_run=False,**kwargs):
        snapshots.append({
            key:dict(value)
            for key,value in (kwargs.get("yield_hints") or {}).items()
        })
        return results[len(snapshots)-1]

    monkeypatch.setattr(engine,"run_once",fake_run_once)
    result=engine.run_until_quota({
        "runtime":{
            "timezone":"Asia/Karachi",
            "daily_target_per_category":1000,
            "max_cycles_per_run":3,
            "max_zero_progress_cycles":3,
            "adaptive_yield_routing":True,
            "adaptive_yield_persist_daily":True,
            "adaptive_yield_state_max_entries":1500,
        },
        "categories":["A"],
    })

    assert state_events["loads"]==1
    assert len(state_events["saves"])==1
    assert snapshots[0][
        "a|united states|r1|us1"
    ]=={
        "visits":2,
        "discovered":100,
        "accepted":20,
    }
    assert snapshots[1][
        "a|united states|r1|us1"
    ]=={
        "visits":3,
        "discovered":150,
        "accepted":30,
    }
    saved=state_events["saves"][0][1][
        "a|united states|r1|us1"
    ]
    assert saved=={
        "visits":3,
        "discovered":150,
        "accepted":30,
    }
    assert result["adaptive_yield_state"]["loaded"] is True
    assert result["adaptive_yield_state"]["saved"] is True
    assert source.closed


def test_run_until_quota_does_not_write_yield_state_without_attempts(monkeypatch):
    source=FakeClosableSource()
    monkeypatch.setattr(engine,"build_sources",lambda config:[source])
    monkeypatch.setattr(engine,"GoogleSheetsStore",lambda config,run_date=None:object())

    class FakeRegistry:
        def close(self):
            pass

    monkeypatch.setattr(engine,"build_registry_index",lambda config:FakeRegistry())
    monkeypatch.setattr(engine,"build_contact_enricher",lambda config:None)

    class FakeStateStore:
        saved=0

        def __init__(self, registry_index, max_entries=1500):
            pass

        def load(self, run_date):
            return {},{
                "status":"empty",
                "key":f"state/{run_date}.json",
                "entries":0,
                "bytes":0,
            }

        def save(self, run_date, hints):
            type(self).saved+=1
            return {"status":"saved","entries":len(hints),"bytes":1}

    monkeypatch.setattr(engine,"DailyYieldStateStore",FakeStateStore)
    monkeypatch.setattr(
        engine,
        "run_once",
        lambda *args,**kwargs:{
            "status":"complete",
            "accepted":0,
            "counts":{"A":1000},
            "country_counts":{"United States":500,"Canada":500},
            "attempts":[],
        },
    )

    result=engine.run_until_quota({
        "runtime":{
            "timezone":"Asia/Karachi",
            "daily_target_per_category":1000,
            "max_cycles_per_run":3,
            "max_zero_progress_cycles":3,
            "adaptive_yield_routing":True,
            "adaptive_yield_persist_daily":True,
            "adaptive_yield_state_max_entries":1500,
        },
        "categories":["A"],
    })

    assert FakeStateStore.saved==0
    assert result["adaptive_yield_state"]["saved"] is False
    assert source.closed


def test_run_until_quota_yield_state_load_failure_is_fail_open(monkeypatch):
    source=FakeClosableSource()
    monkeypatch.setattr(engine,"build_sources",lambda config:[source])
    monkeypatch.setattr(engine,"GoogleSheetsStore",lambda config,run_date=None:object())

    class FakeRegistry:
        def close(self):
            pass

    monkeypatch.setattr(engine,"build_registry_index",lambda config:FakeRegistry())
    monkeypatch.setattr(engine,"build_contact_enricher",lambda config:None)

    class FailingLoadStateStore:
        saved=0

        def __init__(self, registry_index, max_entries=1500):
            pass

        def load(self, run_date):
            raise ValueError("corrupt adaptive state")

        def save(self, run_date, hints):
            type(self).saved+=1
            return {
                "status":"saved",
                "key":f"state/{run_date}.json",
                "entries":len(hints),
                "bytes":80,
            }

    monkeypatch.setattr(engine,"DailyYieldStateStore",FailingLoadStateStore)
    monkeypatch.setattr(
        engine,
        "run_once",
        lambda *args,**kwargs:{
            "status":"complete",
            "accepted":1000,
            "counts":{"A":1000},
            "country_counts":{"United States":1000,"Canada":0},
            "attempts":[
                {
                    "category":"A",
                    "geography":{
                        "country":"United States",
                        "region":"R1",
                        "city":"US1",
                    },
                    "discovered":100,
                    "accepted":50,
                }
            ],
        },
    )

    result=engine.run_until_quota({
        "runtime":{
            "timezone":"Asia/Karachi",
            "daily_target_per_category":1000,
            "max_cycles_per_run":3,
            "max_zero_progress_cycles":3,
            "adaptive_yield_routing":True,
            "adaptive_yield_persist_daily":True,
            "adaptive_yield_state_max_entries":1500,
        },
        "categories":["A"],
    })

    assert "ValueError: corrupt adaptive state" in result[
        "adaptive_yield_state"
    ]["load_error"]
    assert FailingLoadStateStore.saved==1
    assert result["accepted"]==1000
    assert source.closed


def test_run_until_quota_records_daily_health_event_fail_open(monkeypatch):
    source=FakeClosableSource()
    monkeypatch.setattr(engine,"build_sources",lambda config:[source])
    monkeypatch.setattr(engine,"GoogleSheetsStore",lambda config,run_date=None:object())

    class FakeRegistry:
        def close(self):
            pass

    registry=FakeRegistry()
    monkeypatch.setattr(engine,"build_registry_index",lambda config:registry)
    monkeypatch.setattr(engine,"build_contact_enricher",lambda config:None)

    events=[]

    class FakeHealthStore:
        def __init__(self,registry_index,max_events=96):
            assert registry_index is registry
            assert max_events==96

        def append(self,run_date,event):
            events.append((run_date,dict(event)))
            return {
                "status":"appended",
                "key":f"health/{run_date}.json",
                "events":1,
                "bytes":120,
            }

    monkeypatch.setattr(engine,"DailyHealthLedgerStore",FakeHealthStore)
    monkeypatch.setattr(
        engine,
        "run_once",
        lambda *args,**kwargs:{
            "status":"complete",
            "accepted":1000,
            "discovered":2500,
            "counts":{"A":1000},
            "country_counts":{"United States":1000,"Canada":0},
            "attempts":[],
        },
    )

    result=engine.run_until_quota(
        {
            "runtime":{
                "timezone":"Asia/Karachi",
                "daily_target_per_category":1000,
                "max_cycles_per_run":3,
                "max_zero_progress_cycles":3,
                "adaptive_yield_routing":False,
                "adaptive_yield_persist_daily":False,
                "health_ledger_enabled":True,
                "health_ledger_max_events":96,
            },
            "categories":["A"],
        },
        origin="recovery-push",
    )

    assert len(events)==1
    assert events[0][1]["origin"]=="recovery-push"
    assert events[0][1]["quota_complete"] is True
    assert result["health_ledger"]["recorded"] is True
    assert result["health_ledger"]["write_status"]=="appended"
    assert source.closed


def test_health_ledger_failure_does_not_fail_lead_run(monkeypatch):
    source=FakeClosableSource()
    monkeypatch.setattr(engine,"build_sources",lambda config:[source])
    monkeypatch.setattr(engine,"GoogleSheetsStore",lambda config,run_date=None:object())

    class FakeRegistry:
        def close(self):
            pass

    monkeypatch.setattr(engine,"build_registry_index",lambda config:FakeRegistry())
    monkeypatch.setattr(engine,"build_contact_enricher",lambda config:None)

    class FailingHealthStore:
        def __init__(self,registry_index,max_events=96):
            pass

        def append(self,run_date,event):
            raise RuntimeError("health R2 unavailable")

    monkeypatch.setattr(engine,"DailyHealthLedgerStore",FailingHealthStore)
    monkeypatch.setattr(
        engine,
        "run_once",
        lambda *args,**kwargs:{
            "status":"complete",
            "accepted":1000,
            "counts":{"A":1000},
            "country_counts":{"United States":1000,"Canada":0},
            "attempts":[],
        },
    )

    result=engine.run_until_quota(
        {
            "runtime":{
                "timezone":"Asia/Karachi",
                "daily_target_per_category":1000,
                "max_cycles_per_run":3,
                "max_zero_progress_cycles":3,
                "adaptive_yield_routing":False,
                "adaptive_yield_persist_daily":False,
                "health_ledger_enabled":True,
                "health_ledger_max_events":96,
            },
            "categories":["A"],
        },
        origin="native-schedule",
    )

    assert result["status"]=="complete"
    assert result["accepted"]==1000
    assert result["health_ledger"]["recorded"] is False
    assert "RuntimeError: health R2 unavailable" in result["health_ledger"]["error"]
    assert source.closed


def test_merge_routing_hints_uses_weak_history_and_strong_daily_signal():
    merged=engine._merge_routing_hints(
        {
            "a|united states|r1|us1":{
                "visits":2,
                "discovered":100,
                "accepted":30,
            }
        },
        {
            "a|united states|r1|us1":{
                "visits":8,
                "discovered":400,
                "accepted":80,
            },
            "b|canada|r2|ca1":{
                "visits":4,
                "discovered":200,
                "accepted":20,
            },
        },
        historical_weight=0.25,
    )

    assert merged[
        "a|united states|r1|us1"
    ]=={
        "visits":4,
        "discovered":200,
        "accepted":50,
    }
    assert merged[
        "b|canada|r2|ca1"
    ]=={
        "visits":1,
        "discovered":50,
        "accepted":5,
    }


def test_run_until_quota_loads_history_and_saves_once_on_completion(monkeypatch):
    source=FakeClosableSource()
    monkeypatch.setattr(engine,"build_sources",lambda config:[source])
    monkeypatch.setattr(engine,"GoogleSheetsStore",lambda config,run_date=None:object())

    class FakeRegistry:
        def close(self):
            pass

    registry=FakeRegistry()
    monkeypatch.setattr(engine,"build_registry_index",lambda config:registry)
    monkeypatch.setattr(engine,"build_contact_enricher",lambda config:None)
    monkeypatch.setattr(engine,"DailyHealthLedgerStore",lambda *args,**kwargs:None)

    history_events={"load":0,"save":[]}

    class FakeHistoryStore:
        def __init__(self,registry_index,max_entries=1500):
            assert registry_index is registry
            assert max_entries==1500

        def load(self):
            history_events["load"]+=1
            return (
                {
                    "a|united states|r1|us1":{
                        "visits":8,
                        "discovered":400,
                        "accepted":80,
                    }
                },
                {
                    "status":"loaded",
                    "key":"history.json",
                    "entries":1,
                    "bytes":100,
                    "last_completed_date":"2026-09-27",
                },
            )

        def save_completion(self,run_date,daily_hints,decay=0.75):
            history_events["save"].append(
                (
                    run_date,
                    {
                        key:dict(value)
                        for key,value in daily_hints.items()
                    },
                    decay,
                )
            )
            return {
                "status":"saved",
                "key":"history.json",
                "entries":len(daily_hints),
                "bytes":120,
                "last_completed_date":run_date,
            }

    monkeypatch.setattr(engine,"HistoricalYieldProfileStore",FakeHistoryStore)

    class FakeDailyStateStore:
        def __init__(self,*args,**kwargs):
            pass

        def load(self,run_date):
            return {},{
                "status":"empty",
                "key":f"daily/{run_date}.json",
                "entries":0,
                "bytes":0,
            }

        def save(self,run_date,hints):
            return {
                "status":"saved",
                "key":f"daily/{run_date}.json",
                "entries":len(hints),
                "bytes":50,
            }

    monkeypatch.setattr(engine,"DailyYieldStateStore",FakeDailyStateStore)

    snapshots=[]

    def fake_run_once(config,dry_run=False,**kwargs):
        snapshots.append({
            key:dict(value)
            for key,value in (kwargs.get("yield_hints") or {}).items()
        })
        return {
            "status":"complete",
            "accepted":1000,
            "discovered":2000,
            "counts":{"A":1000},
            "country_counts":{"United States":1000,"Canada":0},
            "attempts":[
                {
                    "category":"A",
                    "geography":{
                        "country":"United States",
                        "region":"R1",
                        "city":"US1",
                    },
                    "discovered":100,
                    "accepted":25,
                }
            ],
        }

    monkeypatch.setattr(engine,"run_once",fake_run_once)

    result=engine.run_until_quota(
        {
            "runtime":{
                "timezone":"Asia/Karachi",
                "daily_target_per_category":1000,
                "max_cycles_per_run":3,
                "max_zero_progress_cycles":3,
                "adaptive_yield_routing":True,
                "adaptive_yield_persist_daily":True,
                "adaptive_yield_state_max_entries":1500,
                "adaptive_yield_history_enabled":True,
                "adaptive_yield_history_weight":0.25,
                "adaptive_yield_history_decay":0.75,
                "adaptive_yield_history_max_entries":1500,
                "health_ledger_enabled":False,
            },
            "categories":["A"],
        },
        origin="native-schedule",
    )

    assert history_events["load"]==1
    assert snapshots[0][
        "a|united states|r1|us1"
    ]=={
        "visits":2,
        "discovered":100,
        "accepted":20,
    }
    assert len(history_events["save"])==1
    assert history_events["save"][0][1][
        "a|united states|r1|us1"
    ]=={
        "visits":1,
        "discovered":100,
        "accepted":25,
    }
    assert history_events["save"][0][2]==0.75
    assert result["adaptive_yield_history"]["loaded"] is True
    assert result["adaptive_yield_history"]["saved"] is True
    assert source.closed


def test_run_until_quota_history_failure_is_fail_open(monkeypatch):
    source=FakeClosableSource()
    monkeypatch.setattr(engine,"build_sources",lambda config:[source])
    monkeypatch.setattr(engine,"GoogleSheetsStore",lambda config,run_date=None:object())

    class FakeRegistry:
        def close(self):
            pass

    monkeypatch.setattr(engine,"build_registry_index",lambda config:FakeRegistry())
    monkeypatch.setattr(engine,"build_contact_enricher",lambda config:None)
    monkeypatch.setattr(engine,"DailyHealthLedgerStore",lambda *args,**kwargs:None)

    class BrokenHistory:
        def __init__(self,*args,**kwargs):
            pass

        def load(self):
            raise ValueError("broken historical profile")

    monkeypatch.setattr(engine,"HistoricalYieldProfileStore",BrokenHistory)

    monkeypatch.setattr(
        engine,
        "run_once",
        lambda *args,**kwargs:{
            "status":"complete",
            "accepted":1000,
            "counts":{"A":1000},
            "country_counts":{"United States":1000,"Canada":0},
            "attempts":[],
        },
    )

    result=engine.run_until_quota(
        {
            "runtime":{
                "timezone":"Asia/Karachi",
                "daily_target_per_category":1000,
                "max_cycles_per_run":3,
                "max_zero_progress_cycles":3,
                "adaptive_yield_routing":True,
                "adaptive_yield_persist_daily":False,
                "adaptive_yield_history_enabled":True,
                "adaptive_yield_history_weight":0.25,
                "adaptive_yield_history_decay":0.75,
                "adaptive_yield_history_max_entries":1500,
                "health_ledger_enabled":False,
            },
            "categories":["A"],
        },
    )

    assert result["status"]=="complete"
    assert "ValueError: broken historical profile" in result[
        "adaptive_yield_history"
    ]["load_error"]
    assert source.closed


def _batch_lead(**changes):
    data={
        "country":"United States",
        "category":"IT & Software",
        "business_name":"Example Systems",
        "phone":"",
        "city":"Austin",
        "region":"Texas",
        "source":"Test Source",
        "source_id":"source:example",
        "website":"https://example.com",
    }
    data.update(changes)
    return Lead(**data)


def test_source_batch_dedupe_prefers_valid_phone_representative():
    weak=_batch_lead(phone="",email="",source_url="")
    strong=_batch_lead(
        phone="+12025550199",
        email="hello@example.com",
        source_url="https://source.example/item",
    )

    kept,dropped=_dedupe_source_batch([weak,strong])

    assert dropped==1
    assert kept==[strong]


def test_source_batch_dedupe_prefers_website_when_phone_missing():
    weak=_batch_lead(
        source_id="",
        website="",
    )
    strong=_batch_lead(
        source_id="",
        website="https://example.com",
    )

    kept,dropped=_dedupe_source_batch([weak,strong])

    assert dropped==1
    assert kept==[strong]


def test_source_batch_dedupe_preserves_original_order_for_equal_quality():
    first=_batch_lead(
        business_name="Alpha",
        source_id="source:a",
        website="https://a.example",
    )
    duplicate=_batch_lead(
        business_name="Alpha",
        source_id="source:a",
        website="https://a.example",
    )
    unique=_batch_lead(
        business_name="Beta",
        source_id="source:b",
        website="https://b.example",
    )

    kept,dropped=_dedupe_source_batch([first,duplicate,unique])

    assert dropped==1
    assert kept==[first,unique]


def test_source_batch_dedupe_keeps_distinct_entities():
    first=_batch_lead(
        business_name="Alpha",
        source_id="source:a",
        website="https://a.example",
    )
    second=_batch_lead(
        business_name="Beta",
        source_id="source:b",
        website="https://b.example",
    )

    kept,dropped=_dedupe_source_batch([first,second])

    assert dropped==0
    assert kept==[first,second]


def test_source_contact_mix_matches_p23_raw_contact_semantics():
    candidates=[
        _batch_lead(
            business_name="Phone And Website",
            source_id="source:phone",
            phone="+1 202 555 0101",
            website="https://phone.example",
        ),
        _batch_lead(
            business_name="Website Only",
            source_id="source:website",
            phone="",
            website="https://website.example",
        ),
        _batch_lead(
            business_name="Raw Invalid Phone Still Source Phone",
            source_id="source:invalid",
            phone="not-a-valid-phone",
            website="https://invalid.example",
        ),
    ]

    source_phone,website_only=_source_contact_mix(candidates)

    assert source_phone==2
    assert website_only==1


def test_yield_hints_accumulate_distinct_partition_mask():
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
                "accepted":0,
                "sources":[
                    {"candidate_partition":2},
                    {"candidate_partition":2},
                ],
            },
            {
                "category":"IT & Software",
                "geography":{
                    "country":"United States",
                    "region":"Texas",
                    "city":"Austin",
                },
                "discovered":80,
                "accepted":0,
                "sources":[
                    {"candidate_partition":5},
                ],
            },
        ],
    )

    hint=hints["it & software|united states|texas|austin"]
    assert hint["partition_mask"]==(1 << 2) | (1 << 5)
    assert hint["partition_mask"].bit_count()==2
    assert _yield_hint_summary(hints)["partitions_observed"]==2


def test_commit_deadline_guard_defaults_to_three_minutes():
    assert engine._commit_deadline_guard_seconds({
        "event_deadline_guard_seconds":60,
    })==180.0


def test_commit_deadline_guard_never_weakens_event_guard():
    assert engine._commit_deadline_guard_seconds({
        "event_deadline_guard_seconds":240,
        "commit_deadline_guard_seconds":180,
    })==240.0


def test_critical_search_geography_expands_bbox_for_extreme_shortfall():
    geography={
        "country":"United States",
        "region":"Texas",
        "city":"Austin",
        "bbox":[-98.0,30.0,-97.0,31.0],
    }
    result=_critical_search_geography(
        geography,
        enabled=True,
        completion_ratio=0.07,
        threshold=0.10,
        bbox_factor=1.75,
    )
    assert result["bbox"]==[-98.375,29.625,-96.625,31.375]
    assert result["_bbox_expansion_factor"]==1.75
    assert geography["bbox"]==[-98.0,30.0,-97.0,31.0]


def test_critical_search_geography_keeps_normal_categories_at_base_bbox():
    geography={
        "country":"Canada",
        "region":"Ontario",
        "city":"Toronto",
        "bbox":[-79.8,43.4,-79.0,44.0],
    }
    result=_critical_search_geography(
        geography,
        enabled=True,
        completion_ratio=0.10,
        threshold=0.10,
        bbox_factor=1.75,
    )
    assert result["bbox"]==geography["bbox"]
    assert result["_bbox_expansion_factor"]==1.0


def test_critical_search_geography_clamps_world_bounds():
    geography={
        "country":"Canada",
        "region":"Test",
        "city":"Edge",
        "bbox":[179.0,89.0,180.0,90.0],
    }
    result=_critical_search_geography(
        geography,
        enabled=True,
        completion_ratio=0.01,
        threshold=0.10,
        bbox_factor=3.0,
    )
    assert result["bbox"][2] <= 180.0
    assert result["bbox"][3] <= 90.0


def test_graduated_geography_expansion_uses_low_tier_after_ten_percent():
    geography={
        "country":"United States",
        "region":"Texas",
        "city":"Austin",
        "bbox":[-98.0,30.0,-97.0,31.0],
    }
    result=_critical_search_geography(
        geography,
        enabled=True,
        completion_ratio=0.104,
        threshold=0.10,
        bbox_factor=1.75,
        low_threshold=0.25,
        low_factor=1.50,
        mid_threshold=0.50,
        mid_factor=1.25,
    )
    assert result["_bbox_expansion_factor"]==1.50
    assert result["bbox"]==[-98.25,29.75,-96.75,31.25]


def test_graduated_geography_expansion_uses_mid_tier_before_half_quota():
    geography={
        "country":"United States",
        "region":"Texas",
        "city":"Austin",
        "bbox":[-98.0,30.0,-97.0,31.0],
    }
    result=_critical_search_geography(
        geography,
        enabled=True,
        completion_ratio=0.30,
        threshold=0.10,
        bbox_factor=1.75,
        low_threshold=0.25,
        low_factor=1.50,
        mid_threshold=0.50,
        mid_factor=1.25,
    )
    assert result["_bbox_expansion_factor"]==1.25


def test_graduated_geography_expansion_returns_base_at_half_quota():
    geography={
        "country":"United States",
        "region":"Texas",
        "city":"Austin",
        "bbox":[-98.0,30.0,-97.0,31.0],
    }
    result=_critical_search_geography(
        geography,
        enabled=True,
        completion_ratio=0.50,
        threshold=0.10,
        bbox_factor=1.75,
        low_threshold=0.25,
        low_factor=1.50,
        mid_threshold=0.50,
        mid_factor=1.25,
    )
    assert result["_bbox_expansion_factor"]==1.0
    assert result["bbox"]==geography["bbox"]
