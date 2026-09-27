import io
import json

from botocore.exceptions import ClientError

from vsn_lead_engine.yield_state import DailyYieldStateStore, HistoricalYieldProfileStore


def client_error(status, code, operation):
    return ClientError(
        {
            "Error": {"Code": str(code), "Message": str(code)},
            "ResponseMetadata": {"HTTPStatusCode": status},
        },
        operation,
    )


class FakeS3:
    def __init__(self):
        self.objects = {}

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise client_error(404, "NoSuchKey", "GetObject")
        return {"Body": io.BytesIO(self.objects[Key]["body"])}

    def put_object(self, Bucket, Key, Body=b"", ContentType=None, Metadata=None):
        if isinstance(Body, str):
            Body = Body.encode()
        self.objects[Key] = {
            "body": bytes(Body or b""),
            "content_type": ContentType,
            "metadata": dict(Metadata or {}),
        }
        return {}


class FakeRegistry:
    def __init__(self):
        self.client = FakeS3()
        self.bucket = "bucket"
        self.prefix = "vsn-lead-ledger/v1"


def test_daily_yield_state_missing_is_empty():
    store = DailyYieldStateStore(FakeRegistry())
    hints, meta = store.load("2026-09-28")
    assert hints == {}
    assert meta["status"] == "empty"
    assert meta["entries"] == 0
    assert meta["key"].endswith("/adaptive-yield/v1/2026-09-28.json")


def test_daily_yield_state_round_trip_is_compact_and_date_scoped():
    registry = FakeRegistry()
    store = DailyYieldStateStore(registry)
    hints = {
        "it & software|united states|texas|austin": {
            "visits": 2,
            "discovered": 150,
            "accepted": 25,
        },
        "cars|canada|ontario|toronto": {
            "visits": 1,
            "discovered": 80,
            "accepted": 20,
        },
    }

    saved = store.save("2026-09-28", hints)
    loaded, meta = store.load("2026-09-28")

    assert saved["status"] == "saved"
    assert saved["entries"] == 2
    assert loaded == hints
    assert meta["status"] == "loaded"
    assert meta["entries"] == 2
    assert saved["bytes"] < 1000

    raw = registry.client.objects[saved["key"]]["body"].decode("utf-8")
    payload = json.loads(raw)
    assert payload["version"] == 1
    assert payload["run_date"] == "2026-09-28"
    assert payload["hints"][
        "it & software|united states|texas|austin"
    ] == [2, 150, 25]


def test_daily_yield_state_next_day_does_not_reuse_prior_date():
    registry = FakeRegistry()
    store = DailyYieldStateStore(registry)
    store.save(
        "2026-09-28",
        {
            "a|united states|r1|city": {
                "visits": 1,
                "discovered": 10,
                "accepted": 2,
            }
        },
    )

    hints, meta = store.load("2026-09-29")
    assert hints == {}
    assert meta["status"] == "empty"


def test_daily_yield_state_caps_entries_by_observation_value():
    registry = FakeRegistry()
    store = DailyYieldStateStore(registry, max_entries=2)
    hints = {
        "a": {"visits": 1, "discovered": 100, "accepted": 10},
        "b": {"visits": 5, "discovered": 100, "accepted": 20},
        "c": {"visits": 3, "discovered": 100, "accepted": 30},
    }

    saved = store.save("2026-09-28", hints)
    loaded, _ = store.load("2026-09-28")

    assert saved["entries"] == 2
    assert set(loaded) == {"b", "c"}


def test_daily_yield_state_normalizes_invalid_counters():
    registry = FakeRegistry()
    store = DailyYieldStateStore(registry)
    key = store.key("2026-09-28")
    payload = {
        "version": 1,
        "run_date": "2026-09-28",
        "updated_at": "2026-09-28T00:00:00+00:00",
        "hints": {
            "good": [-3, 10, 50],
            "bad": "not-a-counter",
        },
    }
    registry.client.objects[key] = {
        "body": json.dumps(payload).encode("utf-8"),
        "content_type": "application/json",
        "metadata": {},
    }

    loaded, meta = store.load("2026-09-28")
    assert loaded == {
        "good": {
            "visits": 0,
            "discovered": 10,
            "accepted": 10,
        }
    }
    assert meta["entries"] == 1


def test_historical_yield_profile_missing_is_empty():
    store=HistoricalYieldProfileStore(FakeRegistry())
    hints,meta=store.load()
    assert hints=={}
    assert meta["status"]=="empty"
    assert meta["last_completed_date"]==""
    assert meta["key"].endswith("/adaptive-yield/v2/history.json")


def test_historical_yield_profile_saves_completion_with_decay():
    registry=FakeRegistry()
    store=HistoricalYieldProfileStore(registry)
    store._loaded_hints={
        "a|united states|r1|city":{
            "visits":4,
            "discovered":200,
            "accepted":40,
        }
    }
    store._last_completed_date="2026-09-27"

    saved=store.save_completion(
        "2026-09-28",
        {
            "a|united states|r1|city":{
                "visits":2,
                "discovered":100,
                "accepted":30,
            },
            "b|canada|r2|city":{
                "visits":1,
                "discovered":50,
                "accepted":10,
            },
        },
        decay=0.75,
    )

    assert saved["status"]=="saved"
    loaded,meta=store.load()
    assert meta["last_completed_date"]=="2026-09-28"
    assert loaded[
        "a|united states|r1|city"
    ]=={
        "visits":5,
        "discovered":250,
        "accepted":60,
    }
    assert loaded[
        "b|canada|r2|city"
    ]=={
        "visits":1,
        "discovered":50,
        "accepted":10,
    }


def test_historical_yield_profile_writes_only_once_per_completed_date():
    registry=FakeRegistry()
    store=HistoricalYieldProfileStore(registry)
    store.load()
    first=store.save_completion(
        "2026-09-28",
        {
            "a":{
                "visits":1,
                "discovered":10,
                "accepted":2,
            }
        },
    )
    object_count=len(registry.client.objects)
    second=store.save_completion(
        "2026-09-28",
        {
            "a":{
                "visits":2,
                "discovered":20,
                "accepted":4,
            }
        },
    )

    assert first["status"]=="saved"
    assert second["status"]=="already-completed"
    assert len(registry.client.objects)==object_count


def test_historical_yield_profile_caps_entries():
    registry=FakeRegistry()
    store=HistoricalYieldProfileStore(registry,max_entries=2)
    store.load()
    saved=store.save_completion(
        "2026-09-28",
        {
            "a":{"visits":1,"discovered":10,"accepted":1},
            "b":{"visits":5,"discovered":50,"accepted":10},
            "c":{"visits":3,"discovered":30,"accepted":8},
        },
    )
    loaded,_=store.load()
    assert saved["entries"]==2
    assert set(loaded)=={"b","c"}


def test_daily_yield_state_round_trips_partition_mask():
    registry=FakeRegistry()
    store=DailyYieldStateStore(registry)
    hints={
        "a|united states|r1|city":{
            "visits":4,
            "discovered":300,
            "accepted":0,
            "partition_mask":(1 << 0) | (1 << 3) | (1 << 7),
        }
    }

    saved=store.save("2026-09-28",hints)
    loaded,_=store.load("2026-09-28")

    assert loaded==hints
    payload=json.loads(
        registry.client.objects[saved["key"]]["body"].decode("utf-8")
    )
    assert payload["hints"]["a|united states|r1|city"]==[
        4,
        300,
        0,
        137,
    ]


def test_daily_yield_state_still_loads_legacy_three_counter_hint():
    registry=FakeRegistry()
    store=DailyYieldStateStore(registry)
    key=store.key("2026-09-28")
    registry.client.objects[key]={
        "body":json.dumps({
            "version":1,
            "run_date":"2026-09-28",
            "hints":{"legacy":[2,100,0]},
        }).encode("utf-8"),
        "content_type":"application/json",
        "metadata":{},
    }

    loaded,_=store.load("2026-09-28")
    assert loaded["legacy"]=={
        "visits":2,
        "discovered":100,
        "accepted":0,
    }
