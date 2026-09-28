from __future__ import annotations

import json
from datetime import datetime, timezone

from botocore.exceptions import ClientError


STATE_VERSION = 1


class DailyYieldStateStore:
    """Tiny date-scoped adaptive-routing state stored in the existing R2 bucket."""

    def __init__(self, registry_index, *, max_entries: int = 1500):
        if registry_index is None:
            raise ValueError("DailyYieldStateStore requires an R2 registry index.")
        self.client = registry_index.client
        self.bucket = registry_index.bucket
        self.prefix = str(registry_index.prefix).strip("/")
        self.max_entries = max(1, min(5000, int(max_entries)))

    def key(self, run_date: str) -> str:
        return f"{self.prefix}/adaptive-yield/v1/{run_date}.json"

    @staticmethod
    def _is_missing(exc: ClientError) -> bool:
        status = int(
            exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0) or 0
        )
        code = str(exc.response.get("Error", {}).get("Code", ""))
        return status == 404 or code in {"404", "NoSuchKey", "NotFound"}

    @staticmethod
    def _normalize_hint(raw) -> dict[str, int] | None:
        has_partition_mask=False
        partition_raw=0
        zero_unique_streak_raw=None
        recent_discovered_raw=None
        if isinstance(raw, dict):
            values = (
                raw.get("visits", 0),
                raw.get("discovered", 0),
                raw.get("accepted", 0),
            )
            if "partition_mask" in raw:
                has_partition_mask=True
                partition_raw=raw.get("partition_mask",0)
            if "zero_unique_streak" in raw:
                zero_unique_streak_raw=raw.get("zero_unique_streak",0)
            if "recent_discovered" in raw:
                recent_discovered_raw=raw.get("recent_discovered",0)
        elif isinstance(raw, (list, tuple)) and len(raw) in {3,4}:
            values = raw[:3]
            if len(raw)==4:
                has_partition_mask=True
                partition_raw=raw[3]
        else:
            return None

        try:
            visits, discovered, accepted = [max(0, int(value or 0)) for value in values]
            partition_mask=max(0,int(partition_raw or 0))
        except (TypeError, ValueError):
            return None

        accepted = min(accepted, discovered)
        result={
            "visits": visits,
            "discovered": discovered,
            "accepted": accepted,
        }
        if has_partition_mask:
            # Runtime partitions are capped at 64, so retain only the lower 64 bits.
            result["partition_mask"]=partition_mask & ((1 << 64) - 1)
        if zero_unique_streak_raw is not None:
            try:
                result["zero_unique_streak"]=max(
                    0,int(zero_unique_streak_raw or 0)
                )
            except (TypeError,ValueError):
                result["zero_unique_streak"]=0
        if recent_discovered_raw is not None:
            try:
                result["recent_discovered"]=max(
                    0,int(recent_discovered_raw or 0)
                )
            except (TypeError,ValueError):
                result["recent_discovered"]=0
        return result

    def load(self, run_date: str) -> tuple[dict[str, dict], dict]:
        key = self.key(run_date)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if self._is_missing(exc):
                return {}, {
                    "status": "empty",
                    "key": key,
                    "entries": 0,
                    "bytes": 0,
                }
            raise

        body = response["Body"].read()
        payload = json.loads(body.decode("utf-8"))
        if int(payload.get("version", 0) or 0) != STATE_VERSION:
            raise RuntimeError(
                f"Unsupported adaptive yield state version: {payload.get('version')!r}"
            )
        if str(payload.get("run_date", "")).strip() != run_date:
            raise RuntimeError("Adaptive yield state date does not match requested run date.")

        raw_hints = payload.get("hints", {}) or {}
        if not isinstance(raw_hints, dict):
            raise RuntimeError("Adaptive yield state hints must be an object.")

        hints: dict[str, dict] = {}
        for key_name, raw in raw_hints.items():
            normalized = self._normalize_hint(raw)
            if normalized is None:
                continue
            hints[str(key_name)] = normalized
            if len(hints) >= self.max_entries:
                break

        return hints, {
            "status": "loaded",
            "key": key,
            "entries": len(hints),
            "bytes": len(body),
            "updated_at": str(payload.get("updated_at", "")),
        }

    def save(self, run_date: str, hints: dict[str, dict]) -> dict:
        entries = []
        for key_name in sorted(hints):
            normalized = self._normalize_hint(hints[key_name])
            if normalized is None:
                continue
            if (
                "zero_unique_streak" in normalized
                or "recent_discovered" in normalized
            ):
                serialized={
                    "visits":normalized["visits"],
                    "discovered":normalized["discovered"],
                    "accepted":normalized["accepted"],
                    "zero_unique_streak":int(
                        normalized.get("zero_unique_streak",0) or 0
                    ),
                    "recent_discovered":int(
                        normalized.get("recent_discovered",0) or 0
                    ),
                }
                if "partition_mask" in normalized:
                    serialized["partition_mask"]=normalized["partition_mask"]
            else:
                serialized=[
                    normalized["visits"],
                    normalized["discovered"],
                    normalized["accepted"],
                ]
                if "partition_mask" in normalized:
                    serialized.append(normalized["partition_mask"])
            entries.append((str(key_name),normalized,serialized))

        # Keep the most observed state if a future configuration ever exceeds the
        # compact state ceiling.
        if len(entries) > self.max_entries:
            entries.sort(
                key=lambda item: (
                    -int(item[1]["visits"]),
                    -int(item[1]["accepted"]),
                    item[0],
                )
            )
            entries = entries[: self.max_entries]
            entries.sort(key=lambda item: item[0])

        payload = {
            "version": STATE_VERSION,
            "run_date": run_date,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "hints": {
                key_name: serialized
                for key_name,_normalized,serialized in entries
            },
        }
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        key = self.key(run_date)
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
            Metadata={
                "state": "adaptive-yield-v1",
                "run-date": run_date,
            },
        )
        return {
            "status": "saved",
            "key": key,
            "entries": len(entries),
            "bytes": len(body),
        }


HISTORY_VERSION = 1


class HistoricalYieldProfileStore:
    """Compact cross-day routing prior stored in one existing R2 object."""

    def __init__(self, registry_index, *, max_entries: int = 1500):
        if registry_index is None:
            raise ValueError("HistoricalYieldProfileStore requires an R2 registry index.")
        self.client = registry_index.client
        self.bucket = registry_index.bucket
        self.prefix = str(registry_index.prefix).strip("/")
        self.max_entries = max(1, min(5000, int(max_entries)))
        self._loaded_hints: dict[str, dict] = {}
        self._last_completed_date = ""

    def key(self) -> str:
        return f"{self.prefix}/adaptive-yield/v2/history.json"

    @staticmethod
    def _is_missing(exc: ClientError) -> bool:
        return DailyYieldStateStore._is_missing(exc)

    @staticmethod
    def _normalize_hint(raw) -> dict[str, int] | None:
        return DailyYieldStateStore._normalize_hint(raw)

    def load(self) -> tuple[dict[str, dict], dict]:
        key = self.key()
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if self._is_missing(exc):
                self._loaded_hints = {}
                self._last_completed_date = ""
                return {}, {
                    "status": "empty",
                    "key": key,
                    "entries": 0,
                    "bytes": 0,
                    "last_completed_date": "",
                }
            raise

        body = response["Body"].read()
        payload = json.loads(body.decode("utf-8"))
        if int(payload.get("version", 0) or 0) != HISTORY_VERSION:
            raise RuntimeError(
                f"Unsupported adaptive yield history version: {payload.get('version')!r}"
            )
        raw_hints = payload.get("hints", {}) or {}
        if not isinstance(raw_hints, dict):
            raise RuntimeError("Adaptive yield history hints must be an object.")

        hints: dict[str, dict] = {}
        for key_name, raw in raw_hints.items():
            normalized = self._normalize_hint(raw)
            if normalized is None:
                continue
            hints[str(key_name)] = normalized
            if len(hints) >= self.max_entries:
                break

        self._loaded_hints = hints
        self._last_completed_date = str(
            payload.get("last_completed_date", "")
        ).strip()
        return hints, {
            "status": "loaded",
            "key": key,
            "entries": len(hints),
            "bytes": len(body),
            "last_completed_date": self._last_completed_date,
            "updated_at": str(payload.get("updated_at", "")),
        }

    def save_completion(
        self,
        run_date: str,
        daily_hints: dict[str, dict],
        *,
        decay: float = 0.75,
    ) -> dict:
        if self._last_completed_date == run_date:
            return {
                "status": "already-completed",
                "key": self.key(),
                "entries": len(self._loaded_hints),
                "bytes": 0,
                "last_completed_date": run_date,
            }

        decay = max(0.0, min(1.0, float(decay)))
        merged: dict[str, dict] = {}
        keys = set(self._loaded_hints) | set(daily_hints)
        for key_name in keys:
            old = self._normalize_hint(self._loaded_hints.get(key_name, {})) or {
                "visits": 0,
                "discovered": 0,
                "accepted": 0,
            }
            today = self._normalize_hint(daily_hints.get(key_name, {})) or {
                "visits": 0,
                "discovered": 0,
                "accepted": 0,
            }
            item = {
                "visits": max(0, int(round(old["visits"] * decay))) + today["visits"],
                "discovered": max(
                    0, int(round(old["discovered"] * decay))
                ) + today["discovered"],
                "accepted": max(
                    0, int(round(old["accepted"] * decay))
                ) + today["accepted"],
            }
            item["accepted"] = min(item["accepted"], item["discovered"])
            if item["visits"] or item["discovered"] or item["accepted"]:
                merged[str(key_name)] = item

        entries = list(merged.items())
        if len(entries) > self.max_entries:
            entries.sort(
                key=lambda item: (
                    -int(item[1]["visits"]),
                    -int(item[1]["accepted"]),
                    item[0],
                )
            )
            entries = entries[: self.max_entries]
        entries.sort(key=lambda item: item[0])
        merged = {key_name: value for key_name, value in entries}

        payload = {
            "version": HISTORY_VERSION,
            "last_completed_date": run_date,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "hints": {
                key_name: [
                    value["visits"],
                    value["discovered"],
                    value["accepted"],
                ]
                for key_name, value in merged.items()
            },
        }
        body = json.dumps(
            payload,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        key = self.key()
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
            Metadata={
                "state": "adaptive-yield-history-v1",
                "last-completed-date": run_date,
            },
        )
        self._loaded_hints = merged
        self._last_completed_date = run_date
        return {
            "status": "saved",
            "key": key,
            "entries": len(merged),
            "bytes": len(body),
            "last_completed_date": run_date,
        }
