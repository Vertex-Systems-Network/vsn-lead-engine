import io
import json

from botocore.exceptions import ClientError

from vsn_lead_engine.yield_state import DailyYieldStateStore


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
