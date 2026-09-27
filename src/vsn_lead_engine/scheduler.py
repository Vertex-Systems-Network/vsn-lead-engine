from __future__ import annotations

import math
import os
from collections import defaultdict
from datetime import UTC, datetime
from typing import Iterable


def run_cursor(now: datetime | None = None) -> int:
    """Return a cursor independent of accepted-lead counts."""
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


def _category_weight(count: int, target: int) -> int:
    """Bias shard budget toward the least-complete categories."""
    ratio = count / max(target, 1)
    if ratio < 0.25:
        return 3
    if ratio < 0.50:
        return 2
    return 1


def yield_hint_key(category: str, geography: dict) -> str:
    return "|".join(
        [
            str(category).strip(),
            str(geography.get("country","")).strip(),
            str(geography.get("region","")).strip(),
            str(geography.get("city","")).strip(),
        ]
    ).lower()


def _adaptive_yield_score(
    hint: dict | None,
    *,
    exploration_bonus: float,
) -> float:
    """Smoothed score that rewards yield while preserving exploration."""
    bonus=max(0.0,min(1.0,float(exploration_bonus)))
    if not hint:
        return bonus

    visits=max(0,int(hint.get("visits",0) or 0))
    discovered=max(0,int(hint.get("discovered",0) or 0))
    accepted=max(0,int(hint.get("accepted",0) or 0))
    if visits <= 0:
        return bonus

    empirical=(accepted / discovered) if discovered else 0.0
    exploration=bonus / math.sqrt(visits + 1)
    return empirical + exploration


def _adaptive_country_geographies(
    balanced_geographies: list[dict],
    *,
    category: str,
    yield_hints: dict[str, dict] | None,
    exploration_bonus: float,
) -> dict[str,list[dict]]:
    """Rank metros inside each country without changing country interleave."""
    groups: dict[str,list[tuple[int,dict]]] = defaultdict(list)
    for rank, geography in enumerate(balanced_geographies):
        country=str(geography.get("country","")).strip()
        groups[country].append((rank,geography))

    result={}
    for country, items in groups.items():
        if not yield_hints:
            result[country]=[geo for _rank,geo in items]
            continue
        ranked=sorted(
            items,
            key=lambda item: (
                -_adaptive_yield_score(
                    yield_hints.get(yield_hint_key(category,item[1])),
                    exploration_bonus=exploration_bonus,
                ),
                item[0],
            ),
        )
        result[country]=[geo for _rank,geo in ranked]
    return result


def _balanced_geographies(
    geographies: list[dict],
    *,
    cursor: int,
    country_counts: dict[str, int] | None = None,
) -> list[dict]:
    """Interleave countries and put the underrepresented country first."""
    groups: dict[str, list[dict]] = defaultdict(list)
    country_order: list[str] = []

    for geography in geographies:
        country = str(geography.get("country", "")).strip()
        if country not in groups:
            country_order.append(country)
        groups[country].append(geography)

    if not country_order:
        return []

    rotated_country_order = _rotate(country_order, cursor)
    if country_counts is not None:
        country_rank = {
            country: index for index, country in enumerate(rotated_country_order)
        }
        rotated_country_order.sort(
            key=lambda country: (
                int(country_counts.get(country, 0)),
                country_rank.get(country, 0),
            )
        )

    rotated_groups = {
        country: _rotate(group, cursor * 3 + index)
        for index, (country, group) in enumerate(groups.items())
    }

    positions = {country: 0 for country in rotated_country_order}
    result: list[dict] = []
    remaining = sum(len(group) for group in groups.values())

    while remaining > 0:
        progressed = False
        for country in rotated_country_order:
            group = rotated_groups.get(country, [])
            position = positions[country]
            if position >= len(group):
                continue
            result.append(group[position])
            positions[country] += 1
            remaining -= 1
            progressed = True
        if not progressed:
            break

    return result


def build_shard_plan(
    categories: Iterable[str],
    geographies: Iterable[dict],
    counts: dict[str, int],
    target: int,
    *,
    cursor: int,
    max_attempts: int,
    country_counts: dict[str, int] | None = None,
    yield_hints: dict[str, dict] | None = None,
    adaptive_enabled: bool = True,
    exploration_bonus: float = 0.15,
) -> list[dict]:
    """Build a progress-weighted, country-balanced rotating shard plan.

    Properties:
    - completed categories are skipped;
    - <25% complete categories receive 3x shard weight;
    - 25-50% complete categories receive 2x weight;
    - >=50% complete categories receive normal weight;
    - countries are interleaved, with the country having fewer usable leads
      scheduled first;
    - cursor rotation prevents repeatedly hitting the same metro;
    - optional in-memory yield hints reorder metros inside each country/category
      while leaving the country sequence unchanged.
    """
    category_list = list(categories)
    geography_list = list(geographies)
    if not category_list or not geography_list or max_attempts <= 0:
        return []

    rotated_categories = _rotate(category_list, cursor)
    pending = [c for c in rotated_categories if counts.get(c, 0) < target]
    if not pending:
        return []

    rotation_rank = {category: index for index, category in enumerate(rotated_categories)}
    pending.sort(
        key=lambda category: (
            counts.get(category, 0) / max(target, 1),
            counts.get(category, 0),
            rotation_rank.get(category, 0),
        )
    )

    weighted_categories: list[str] = []
    for category in pending:
        weighted_categories.extend(
            [category] * _category_weight(int(counts.get(category, 0)), target)
        )

    balanced_geographies = _balanced_geographies(
        geography_list,
        cursor=cursor,
        country_counts=country_counts,
    )
    if not balanced_geographies:
        return []

    adaptive_groups={}
    if adaptive_enabled:
        for category in pending:
            adaptive_groups[category]=_adaptive_country_geographies(
                balanced_geographies,
                category=category,
                yield_hints=yield_hints,
                exploration_bonus=exploration_bonus,
            )

    positions=defaultdict(int)
    plan: list[dict] = []
    for attempt in range(max_attempts):
        category = weighted_categories[attempt % len(weighted_categories)]
        base_geography = balanced_geographies[attempt % len(balanced_geographies)]
        country=str(base_geography.get("country","")).strip()
        geography=base_geography
        adaptive_score=None

        if adaptive_enabled:
            candidates=adaptive_groups.get(category,{}).get(country,[])
            if candidates:
                position=positions[(category,country)] % len(candidates)
                geography=candidates[position]
                positions[(category,country)] += 1
                adaptive_score=_adaptive_yield_score(
                    (yield_hints or {}).get(yield_hint_key(category,geography)),
                    exploration_bonus=exploration_bonus,
                )

        plan.append(
            {
                "attempt": attempt + 1,
                "category": category,
                "geography": geography,
                "priority_weight": _category_weight(
                    int(counts.get(category, 0)), target
                ),
                "adaptive_yield_score":(
                    round(float(adaptive_score),6)
                    if adaptive_score is not None else None
                ),
            }
        )
    return plan
