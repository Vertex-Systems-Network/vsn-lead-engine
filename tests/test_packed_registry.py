import io
import json

import pytest
from botocore.exceptions import ClientError

from vsn_lead_engine.dedupe import fingerprints
from vsn_lead_engine.models import Lead
from vsn_lead_engine.packed_registry import PackedR2RegistryIndex
from vsn_lead_engine.registry import (
    R2RegistryIndex,
    build_registry_index,
    lead_registry_payload,
)


def client_error(status, code, operation):
    return ClientError(
        {
            "Error": {"Code": str(code), "Message": str(code)},
            "ResponseMetadata": {"HTTPStatusCode": status},
        },
        operation,
    )


class FakePaginator:
    def __init__(self, client):
        self.client = client

    def paginate(self, Bucket, Prefix):
        contents = [
            {"Key": key, "Size": len(value["body"])}
            for key, value in sorted(self.client.objects.items())
            if key.startswith(Prefix)
        ]
        yield {"Contents": contents}


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.get_counts = {}
        self.head_counts = {}

    def head_bucket(self, Bucket):
        return {}

    def head_object(self, Bucket, Key):
        self.head_counts[Key] = self.head_counts.get(Key, 0) + 1
        if Key not in self.objects:
            raise client_error(404, "NoSuchKey", "HeadObject")
        return {"Metadata": dict(self.objects[Key]["metadata"])}

    def put_object(
        self,
        Bucket,
        Key,
        Body=b"",
        ContentType=None,
        Metadata=None,
        IfNoneMatch=None,
    ):
        if IfNoneMatch == "*" and Key in self.objects:
            raise client_error(412, "PreconditionFailed", "PutObject")
        if hasattr(Body, "read"):
            Body = Body.read()
        if isinstance(Body, str):
            Body = Body.encode()
        self.objects[Key] = {
            "body": bytes(Body or b""),
            "metadata": dict(Metadata or {}),
            "content_type": ContentType,
        }
        return {"ETag": '"fake"'}

    def delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)
        return {}

    def get_object(self, Bucket, Key):
        self.get_counts[Key] = self.get_counts.get(Key, 0) + 1
        if Key not in self.objects:
            raise client_error(404, "NoSuchKey", "GetObject")
        return {"Body": io.BytesIO(self.objects[Key]["body"])}

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return FakePaginator(self)

    def close(self):
        return None


def set_r2_env(monkeypatch):
    monkeypatch.setenv("R2_ACCOUNT_ID", "acct")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "access")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("R2_BUCKET", "vsn-lead-engine")


def config(layout="packed-v2"):
    return {
        "registry": {
            "mode": "r2",
            "layout": layout,
            "prefix": "vsn-lead-ledger/v1",
            "max_workers": 8,
            "retry_attempts": 2,
            "pack_shard_chars": 1,
            "lock_stale_seconds": 180,
        }
    }


def make_lead(**changes):
    data = dict(
        country="Canada",
        category="IT & Software",
        business_name="Packed Example Systems",
        phone="+1 416 555 0123",
        city="Toronto",
        region="Ontario",
        source="Overture Maps Places",
        source_id="overture:packed-abc123",
        website="https://packed-example.com",
    )
    data.update(changes)
    return Lead(**data)


def test_build_registry_selects_packed_layout(monkeypatch):
    set_r2_env(monkeypatch)
    index = build_registry_index(config(), client=FakeS3())
    assert isinstance(index, PackedR2RegistryIndex)
    assert index.verify()["layout"] == "packed-v2"


def test_reservation_is_one_pending_marker_without_per_fingerprint_objects(monkeypatch):
    set_r2_env(monkeypatch)
    fake = FakeS3()
    index = PackedR2RegistryIndex(config(), client=fake)
    lead = make_lead()
    payload = lead_registry_payload(lead, {"id": "sheet123"})

    reserved = index.reserve_pending([lead], {"id": "sheet123"})

    assert reserved == {payload["unique_token"]}
    assert len([key for key in fake.objects if "/pending/" in key]) == 1
    assert not any("/fp/" in key for key in fake.objects)
    assert not any("/packs/v2/" in key for key in fake.objects)
    assert not any("/locks/" in key for key in fake.objects)
    assert index.collision_keys([lead]) == {payload["unique_token"]}


def test_activation_commits_exact_binary_packs_and_keeps_legacy_path_empty(monkeypatch):
    set_r2_env(monkeypatch)
    fake = FakeS3()
    index = PackedR2RegistryIndex(config(), client=fake)
    lead = make_lead()
    payload = lead_registry_payload(lead, {"id": "sheet123"})

    reserved = index.reserve_pending([lead], {"id": "sheet123"})
    assert index.activate(reserved) == 1

    pack_keys = [key for key in fake.objects if "/packs/v2/" in key]
    assert pack_keys
    assert not any("/pending/" in key for key in fake.objects)
    assert not any("/fp/" in key for key in fake.objects)
    assert all(len(fake.objects[key]["body"]) % 12 == 0 for key in pack_keys)
    assert index.collision_keys([lead]) == {payload["unique_token"]}

    stats = index.stats()
    assert stats["packed_objects"] == len(pack_keys)
    assert stats["packed_tokens"] == len(payload["fingerprints"])
    assert stats["fingerprint_objects"] == 0


def test_retryable_discards_reservation_without_poisoning_permanent_dedupe(monkeypatch):
    set_r2_env(monkeypatch)
    fake = FakeS3()
    index = PackedR2RegistryIndex(config(), client=fake)
    lead = make_lead()
    payload = lead_registry_payload(lead, {"id": "sheet123"})

    reserved = index.reserve_pending([lead], {"id": "sheet123"})
    assert index.mark_retryable(reserved) == 1

    assert not any("/pending/" in key for key in fake.objects)
    assert not any("/packs/v2/" in key for key in fake.objects)
    assert index.collision_keys([lead]) == set()
    assert payload["unique_token"] not in index.collision_keys([lead])


def test_packed_layout_still_reads_historical_v1_fingerprint_objects(monkeypatch):
    set_r2_env(monkeypatch)
    fake = FakeS3()
    legacy = R2RegistryIndex(config("objects-v1"), client=fake)
    lead = make_lead()
    payload = lead_registry_payload(lead, {"id": "sheet123"})
    assert legacy.import_rows([payload])["imported"] == 1
    assert any("/fp/" in key for key in fake.objects)

    packed = PackedR2RegistryIndex(config(), client=fake)
    assert packed.collision_keys([lead]) == {payload["unique_token"]}


def _store_with_unique_key(unique_key):
    class ValuesGet:
        def get(self, **kwargs):
            return self

        def execute(self, **kwargs):
            return {"values": [[unique_key]] if unique_key else []}

    class FakeSheets:
        def spreadsheets(self):
            return self

        def values(self):
            return ValuesGet()

    class Store:
        sheets = FakeSheets()
        api_retries = 0

    return Store()


def test_crash_recovery_promotes_written_pending_rows_into_packs(monkeypatch):
    set_r2_env(monkeypatch)
    fake = FakeS3()
    lead = make_lead()
    first = PackedR2RegistryIndex(config(), client=fake)
    payload = lead_registry_payload(lead, {"id": "sheet123"})
    first.reserve_pending([lead], {"id": "sheet123"})

    recovered = PackedR2RegistryIndex(config(), client=fake)
    result = recovered.reconcile_pending(_store_with_unique_key(fingerprints(lead).unique))

    assert result["activated"] == 1
    assert result["rolled_back"] == 0
    assert not any("/pending/" in key for key in fake.objects)
    assert any("/packs/v2/" in key for key in fake.objects)
    assert recovered.collision_keys([lead]) == {payload["unique_token"]}


def test_crash_recovery_discards_unwritten_pending_rows_without_pack_write(monkeypatch):
    set_r2_env(monkeypatch)
    fake = FakeS3()
    lead = make_lead()
    first = PackedR2RegistryIndex(config(), client=fake)
    first.reserve_pending([lead], {"id": "sheet123"})

    recovered = PackedR2RegistryIndex(config(), client=fake)
    result = recovered.reconcile_pending(_store_with_unique_key(""))

    assert result["activated"] == 0
    assert result["rolled_back"] == 1
    assert not any("/pending/" in key for key in fake.objects)
    assert not any("/packs/v2/" in key for key in fake.objects)
    assert recovered.collision_keys([lead]) == set()


def test_same_batch_secondary_fingerprint_collision_accepts_only_first(monkeypatch):
    set_r2_env(monkeypatch)
    fake = FakeS3()
    index = PackedR2RegistryIndex(config(), client=fake)
    first = make_lead()
    second = make_lead(
        source_id="overture:other-id",
        website="https://other-domain.example",
    )

    reserved = index.reserve_pending([first, second], {"id": "sheet123"})

    assert len(reserved) == 1
    batch = index.pending_rows()[0]
    assert len(batch["rows"]) == 1


def test_live_smoke_activates_and_cleans_packed_layout(monkeypatch):
    from vsn_lead_engine import packed_registry as packed_module
    from vsn_lead_engine import registry as registry_module

    set_r2_env(monkeypatch)
    fake = FakeS3()

    class SmokePackedIndex(PackedR2RegistryIndex):
        def __init__(self, config):
            super().__init__(config, client=fake)

    monkeypatch.setattr(packed_module, "PackedR2RegistryIndex", SmokePackedIndex)
    result = registry_module.live_smoke_test(config())

    assert result["status"] == "ok"
    assert result["layout"] == "packed-v2"
    assert result["rollback_reserved"] == 1
    assert result["rolled_back"] == 1
    assert result["activation_reserved"] == 1
    assert result["activated"] == 1
    assert result["collision_after_activation"] == 1
    assert result["permanent_objects_during_activation"] > 0
    assert result["permanent_tokens_during_activation"] >= 3
    assert result["cleanup_objects_deleted"] > 0
    assert result["collision_after_cleanup"] == 0
    assert result["remaining_fingerprint_objects"] == 0
    assert result["remaining_packed_objects"] == 0


def _packed_get_count(fake):
    return sum(
        count
        for key,count in fake.get_counts.items()
        if "/packs/v2/" in key
    )


def test_advisory_collision_checks_reuse_packed_read_cache(monkeypatch):
    set_r2_env(monkeypatch)
    fake=FakeS3()

    writer=PackedR2RegistryIndex(config(),client=fake)
    lead=make_lead()
    reserved=writer.reserve_pending([lead],{"id":"sheet123"})
    writer.activate(reserved)

    reader=PackedR2RegistryIndex(config(),client=fake)
    before=_packed_get_count(fake)
    first=reader.collision_keys([lead])
    after_first=_packed_get_count(fake)
    second=reader.collision_keys([lead])
    after_second=_packed_get_count(fake)

    assert first
    assert second==first
    assert after_first > before
    assert after_second == after_first
    stats=reader.cache_stats()
    assert stats["entries"] > 0
    assert stats["hits"] > 0
    assert stats["misses"] > 0


def test_reserve_pending_uses_fresh_reads_even_when_advisory_cache_is_stale(monkeypatch):
    set_r2_env(monkeypatch)
    fake=FakeS3()
    lead=make_lead()

    reader=PackedR2RegistryIndex(config(),client=fake)
    assert reader.collision_keys([lead]) == set()
    assert reader.cache_stats()["entries"] > 0

    writer=PackedR2RegistryIndex(config(),client=fake)
    reserved=writer.reserve_pending([lead],{"id":"sheet123"})
    assert reserved
    assert writer.activate(reserved) == 1

    # Reader still has a stale advisory miss cached.
    assert reader.collision_keys([lead]) == set()

    # Commit-time reservation must ignore advisory cache and read fresh packs.
    assert reader.reserve_pending([lead],{"id":"sheet456"}) == set()


def test_clear_read_cache_forces_next_advisory_refresh(monkeypatch):
    set_r2_env(monkeypatch)
    fake=FakeS3()
    lead=make_lead()

    writer=PackedR2RegistryIndex(config(),client=fake)
    reserved=writer.reserve_pending([lead],{"id":"sheet123"})
    writer.activate(reserved)

    reader=PackedR2RegistryIndex(config(),client=fake)
    assert reader.collision_keys([lead])
    first_reads=_packed_get_count(fake)
    reader.clear_read_cache()
    assert reader.cache_stats()["entries"] == 0
    assert reader.collision_keys([lead])
    assert _packed_get_count(fake) > first_reads


def _legacy_head_count(fake):
    return sum(
        count
        for key,count in fake.head_counts.items()
        if "/fp/" in key
    )


def test_advisory_collision_checks_reuse_legacy_v1_head_cache(monkeypatch):
    set_r2_env(monkeypatch)
    fake=FakeS3()
    legacy=R2RegistryIndex(config("objects-v1"),client=fake)
    lead=make_lead()
    payload=lead_registry_payload(lead,{"id":"sheet123"})
    assert legacy.import_rows([payload])["imported"]==1

    reader=PackedR2RegistryIndex(config(),client=fake)
    before=_legacy_head_count(fake)
    first=reader.collision_keys([lead])
    after_first=_legacy_head_count(fake)
    second=reader.collision_keys([lead])
    after_second=_legacy_head_count(fake)

    assert first=={payload["unique_token"]}
    assert second==first
    assert after_first > before
    assert after_second == after_first
    stats=reader.cache_stats()
    assert stats["legacy_entries"] > 0
    assert stats["legacy_hits"] > 0
    assert stats["legacy_misses"] > 0


def test_reserve_pending_uses_fresh_legacy_heads_despite_stale_negative_cache(monkeypatch):
    set_r2_env(monkeypatch)
    fake=FakeS3()
    lead=make_lead()

    reader=PackedR2RegistryIndex(config(),client=fake)
    assert reader.collision_keys([lead]) == set()
    assert reader.cache_stats()["legacy_entries"] > 0

    legacy=R2RegistryIndex(config("objects-v1"),client=fake)
    payload=lead_registry_payload(lead,{"id":"sheet123"})
    assert legacy.import_rows([payload])["imported"]==1

    # Advisory cache is intentionally stale for this event.
    assert reader.collision_keys([lead]) == set()

    # Reservation path bypasses advisory caches and must still block the lead.
    assert reader.reserve_pending([lead],{"id":"sheet456"}) == set()


def test_packed_import_rows_clears_legacy_advisory_cache(monkeypatch):
    set_r2_env(monkeypatch)
    fake=FakeS3()
    index=PackedR2RegistryIndex(config(),client=fake)
    lead=make_lead()
    payload=lead_registry_payload(lead,{"id":"sheet123"})

    assert index.collision_keys([lead]) == set()
    assert index.cache_stats()["legacy_entries"] > 0

    assert index.import_rows([payload])["imported"]==1
    assert index.cache_stats()["legacy_entries"] == 0
    assert index.collision_keys([lead]) == {payload["unique_token"]}
