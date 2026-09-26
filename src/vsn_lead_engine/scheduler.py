from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Iterable


def run_cursor(now: datetime | None = None) -> int:
    """Return a cursor independent of accepted-lead counts.

    GitHub run numbers are monotonic across workflow runs, so consecutive
    scheduled/manual executions naturally rotate to a different shard.
    Local runs fall back to the current UTC hour.
    """
    raw = os.getenv("GITHUB_RUN_NUMBER", "").strip()
    if raw.isdigit():
        return int(raw)
    current = now or datetime.now(UTC)
    return int(current.timestamp() // 3600)


def _rotate(items: list, offset: int) -> list:
    if not items:
        return []
    offset %= len(items)
    return items[offset:] + items[:offset]


def build_shard_plan(
    categories: Iterable[str],
    geographies: Iterable[dict],
    counts: dict[str, int],
    target: int,
    *,
    cursor: int,
    max_attempts: int,
) -> list[dict]:
    """Build a deterministic rotating category/geography plan.

    Categories with the lowest completion ratio stay prioritized, while the
    cursor changes tie order every run. Geography order rotates independently
    from accepted counts, preventing an empty shard from being retried forever.
    """
    category_list = list(categories)
    geography_list = list(geographies)
    if not category_list or not geography_list or max_attempts <= 0:
        return []

    rotated_categories = _rotate(category_list, cursor)
    pending = [c for c in rotated_categories if counts.get(c, 0) < target]
    if not pending:
        return []

    # Stable sort preserves cursor-derived order among equal-progress categories.
    pending.sort(
        key=lambda c: (
            counts.get(c, 0) / max(target, 1),
            counts.get(c, 0),
        )
    )
    rotated_geographies = _rotate(geography_list, cursor * 5 + 3)

    plan: list[dict] = []
    for attempt in range(max_attempts):
        category = pending[attempt % len(pending)]
        geography = rotated_geographies[attempt % len(rotated_geographies)]
        plan.append(
            {
                "attempt": attempt + 1,
                "category": category,
                "geography": geography,
            }
        )
    return plan
