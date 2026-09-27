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
        if isinstance(raw, dict):
            values = (
                raw.get("visits", 0),
                raw.get("discovered", 0),
                raw.get("accepted", 0),
            )
        elif isinstance(raw, (list, tuple)) and len(raw) == 3:
            values = raw
        else:
            return None

        try:
            visits, discovered, accepted = [max(0, int(value or 0)) for value in values]
        except (TypeError, ValueError):
            return None

        if accepted > discovered and discovered > 0:
            accepted = discovered
        return {
            "visits": visits,
            "discovered": discovered,
            "accepted": accepted,
        }

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
            entries.append(
                (
                    str(key_name),
                    [
                        normalized["visits"],
                        normalized["discovered"],
                        normalized["accepted"],
                    ],
                )
            )

        # Keep the most observed state if a future configuration ever exceeds the
        # compact state ceiling.
        if len(entries) > self.max_entries:
            entries.sort(
                key=lambda item: (
                    -int(item[1][0]),
                    -int(item[1][2]),
                    item[0],
                )
            )
            entries = entries[: self.max_entries]
            entries.sort(key=lambda item: item[0])

        payload = {
            "version": STATE_VERSION,
            "run_date": run_date,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "hints": {key_name: values for key_name, values in entries},
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
