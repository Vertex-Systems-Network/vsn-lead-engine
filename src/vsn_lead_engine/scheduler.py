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


def _category_weight(
    count: int,
    target: int,
    *,
    rescue_enabled: bool = True,
    critical_ratio: float = 0.10,
    critical_weight: int = 6,
    low_ratio: float = 0.25,
    low_weight: int = 4,
    mid_ratio: float = 0.50,
    mid_weight: int = 2,
) -> int:
    """Bias shard budget toward the least-complete categories.

    P35 keeps the layered fairness invariant (every pending category gets one
    pass before repeats) but gives extreme shortfalls enough repeat slots to
    make meaningful progress inside the fixed event budget.
    """
    ratio = count / max(target, 1)
    if not rescue_enabled:
        if ratio < 0.25:
            return 3
        if ratio < 0.50:
            return 2
        return 1

    critical_ratio=max(0.0,min(1.0,float(critical_ratio)))
    low_ratio=max(critical_ratio,min(1.0,float(low_ratio)))
    mid_ratio=max(low_ratio,min(1.0,float(mid_ratio)))
    critical_weight=max(1,int(critical_weight))
    low_weight=max(1,min(critical_weight,int(low_weight)))
    mid_weight=max(1,min(low_weight,int(mid_weight)))

    if ratio < critical_ratio:
        return critical_weight
    if ratio < low_ratio:
        return low_weight
    if ratio < mid_ratio:
        return mid_weight
    return 1


def _fair_weighted_categories(
    categories: list[str],
    counts: dict[str,int],
    target: int,
    *,
    rescue_enabled: bool = True,
    critical_ratio: float = 0.10,
    critical_weight: int = 6,
    low_ratio: float = 0.25,
    low_weight: int = 4,
    mid_ratio: float = 0.50,
    mid_weight: int = 2,
) -> list[str]:
    """Layer weights so every pending category gets one pass before repeats."""
    weights={
        category:_category_weight(
            int(counts.get(category,0)),
            target,
            rescue_enabled=rescue_enabled,
            critical_ratio=critical_ratio,
            critical_weight=critical_weight,
            low_ratio=low_ratio,
            low_weight=low_weight,
            mid_ratio=mid_ratio,
            mid_weight=mid_weight,
        )
        for category in categories
    }
    max_weight=max(weights.values(),default=0)
    sequence=[]
    for layer in range(max_weight):
        for category in categories:
            if weights[category] > layer:
                sequence.append(category)
    return sequence


def yield_hint_key(category: str, geography: dict) -> str:
    return "|".join(
        [
            str(category).strip(),
            str(geography.get("country","")).strip(),
            str(geography.get("region","")).strip(),
            str(geography.get("city","")).strip(),
        ]
    ).lower()


def partition_yield_hint_key(
    category: str,
    geography: dict,
    partition: int,
) -> str:
    return (
        f"{yield_hint_key(category,geography)}|partition:"
        f"{max(0,int(partition))}"
    )


def _adaptive_yield_score(
    hint: dict | None,
    *,
    exploration_bonus: float,
    score_mode: str = "throughput",
) -> float:
    """Smoothed score that rewards usable lead throughput plus exploration.

    throughput ranks routes by accepted leads per attempted shard, which aligns
    routing with the daily quota objective. conversion preserves the legacy
    accepted/discovered ratio for emergency rollback.
    """
    bonus=max(0.0,min(1.0,float(exploration_bonus)))
    if not hint:
        return bonus

    visits=max(0,int(hint.get("visits",0) or 0))
    discovered=max(0,int(hint.get("discovered",0) or 0))
    accepted=max(0,int(hint.get("accepted",0) or 0))
    if visits <= 0:
        return bonus

    mode=str(score_mode or "throughput").strip().lower()
    if mode=="conversion":
        empirical=(accepted / discovered) if discovered else 0.0
    else:
        empirical=accepted / visits
    exploration=bonus / math.sqrt(visits + 1)
    return empirical + exploration


def select_candidate_partition(
    category: str,
    geography: dict,
    *,
    partition_count: int,
    cursor: int,
    attempt: int,
    yield_hints: dict[str,dict] | None = None,
    adaptive_enabled: bool = True,
    exploration_bonus: float = 0.15,
    score_mode: str = "throughput",
    exhaustion_cooldown_enabled: bool = True,
    exhaustion_min_visits: int = 2,
    exhaustion_min_discovered: int = 20,
) -> tuple[int,float | None]:
    """Choose one partition using persisted yield while preserving exploration."""
    count=max(1,min(64,int(partition_count)))
    base=(int(cursor)+max(0,int(attempt)-1)) % count
    if not adaptive_enabled:
        return base,None

    ordered=[(base+offset) % count for offset in range(count)]
    if not yield_hints:
        return base,round(float(exploration_bonus),6)

    eligible=ordered
    if exhaustion_cooldown_enabled:
        exhausted=[]
        for partition in ordered:
            hint=yield_hints.get(
                partition_yield_hint_key(category,geography,partition)
            )
            if not hint:
                continue
            visits=max(0,int(hint.get("visits",0) or 0))
            discovered=max(0,int(hint.get("discovered",0) or 0))
            accepted=max(0,int(hint.get("accepted",0) or 0))
            if (
                visits >= max(1,int(exhaustion_min_visits))
                and discovered >= max(1,int(exhaustion_min_discovered))
                and accepted == 0
            ):
                exhausted.append(partition)
        survivors=[partition for partition in ordered if partition not in exhausted]
        if survivors:
            eligible=survivors

    ranked=sorted(
        enumerate(eligible),
        key=lambda item: (
            -_adaptive_yield_score(
                yield_hints.get(
                    partition_yield_hint_key(
                        category,
                        geography,
                        item[1],
                    )
                ),
                exploration_bonus=exploration_bonus,
                score_mode=score_mode,
            ),
            item[0],
        ),
    )
    partition=ranked[0][1]
    score=_adaptive_yield_score(
        yield_hints.get(
            partition_yield_hint_key(category,geography,partition)
        ),
        exploration_bonus=exploration_bonus,
        score_mode=score_mode,
    )
    return partition,round(float(score),6)


def _same_day_route_is_cooldown(
    hint: dict | None,
    *,
    min_visits: int,
    min_discovered: int,
    min_partitions: int,
) -> bool:
    if not hint:
        return False
    visits=max(0,int(hint.get("visits",0) or 0))
    discovered=max(0,int(hint.get("discovered",0) or 0))
    accepted=max(0,int(hint.get("accepted",0) or 0))
    partition_mask=max(0,int(hint.get("partition_mask",0) or 0))
    partitions_observed=partition_mask.bit_count()
    return (
        visits >= max(1,int(min_visits))
        and discovered >= max(1,int(min_discovered))
        and partitions_observed >= max(1,int(min_partitions))
        and accepted == 0
    )


def _effective_cooldown_keys(
    items: list[tuple[int,dict]],
    *,
    category: str,
    daily_yield_hints: dict[str,dict] | None,
    min_visits: int,
    min_discovered: int,
    min_partitions: int,
) -> set[str]:
    """Cooldown zero-yield routes only when alternatives remain available."""
    if not daily_yield_hints or not items:
        return set()
    cooled={
        yield_hint_key(category,geo)
        for _rank,geo in items
        if _same_day_route_is_cooldown(
            daily_yield_hints.get(yield_hint_key(category,geo)),
            min_visits=min_visits,
            min_discovered=min_discovered,
            min_partitions=min_partitions,
        )
    }
    # Never starve a category/country. If every route is exhausted-looking,
    # fall back to score ordering and allow another rotated pass.
    return cooled if 0 < len(cooled) < len(items) else set()


def _adaptive_country_geographies(
    balanced_geographies: list[dict],
    *,
    category: str,
    yield_hints: dict[str, dict] | None,
    daily_yield_hints: dict[str, dict] | None,
    exploration_bonus: float,
    cooldown_enabled: bool,
    cooldown_min_visits: int,
    cooldown_min_discovered: int,
    cooldown_min_partitions: int,
    score_mode: str,
) -> tuple[dict[str,list[dict]],set[str]]:
    """Rank metros inside each country without changing country interleave."""
    groups: dict[str,list[tuple[int,dict]]] = defaultdict(list)
    for rank, geography in enumerate(balanced_geographies):
        country=str(geography.get("country","")).strip()
        groups[country].append((rank,geography))

    result={}
    applied_cooldowns=set()
    for country, items in groups.items():
        cooled=(
            _effective_cooldown_keys(
                items,
                category=category,
                daily_yield_hints=daily_yield_hints,
                min_visits=cooldown_min_visits,
                min_discovered=cooldown_min_discovered,
                min_partitions=cooldown_min_partitions,
            )
            if cooldown_enabled else set()
        )
        applied_cooldowns.update(cooled)
        if not yield_hints and not cooled:
            result[country]=[geo for _rank,geo in items]
            continue
        eligible=[
            item for item in items
            if yield_hint_key(category,item[1]) not in cooled
        ] or items
        ranked=sorted(
            eligible,
            key=lambda item: (
                -_adaptive_yield_score(
                    (yield_hints or {}).get(yield_hint_key(category,item[1])),
                    exploration_bonus=exploration_bonus,
                    score_mode=score_mode,
                ),
                item[0],
            ),
        )
        result[country]=[geo for _rank,geo in ranked]
    return result,applied_cooldowns


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
    daily_yield_hints: dict[str, dict] | None = None,
    adaptive_enabled: bool = True,
    exploration_bonus: float = 0.15,
    cooldown_enabled: bool = True,
    cooldown_min_visits: int = 2,
    cooldown_min_discovered: int = 100,
    cooldown_min_partitions: int = 4,
    critical_deficit_rescue_enabled: bool = True,
    critical_deficit_ratio: float = 0.10,
    critical_deficit_weight: int = 6,
    low_deficit_ratio: float = 0.25,
    low_deficit_weight: int = 4,
    mid_deficit_ratio: float = 0.50,
    mid_deficit_weight: int = 2,
    adaptive_score_mode: str = "throughput",
) -> list[dict]:
    """Build a progress-weighted, country-balanced rotating shard plan.

    Properties:
    - completed categories are skipped;
    - with P35 rescue enabled, <10% complete categories receive 6x weight;
    - 10-25% complete categories receive 4x weight;
    - 25-50% complete categories receive 2x weight;
    - >=50% complete categories receive normal weight;
    - weights are layered so every pending category gets one pass before
      higher-weight categories consume their repeat slots;
    - countries are interleaved, with the country having fewer usable leads
      scheduled first;
    - cursor rotation prevents repeatedly hitting the same metro;
    - adaptive scores default to accepted leads per shard attempt so routing
      optimizes quota throughput rather than small-shard conversion percentage;
    - optional yield hints reorder metros inside each country/category while
      leaving the country sequence unchanged.
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

    weighted_categories=_fair_weighted_categories(
        pending,
        counts,
        target,
        rescue_enabled=critical_deficit_rescue_enabled,
        critical_ratio=critical_deficit_ratio,
        critical_weight=critical_deficit_weight,
        low_ratio=low_deficit_ratio,
        low_weight=low_deficit_weight,
        mid_ratio=mid_deficit_ratio,
        mid_weight=mid_deficit_weight,
    )

    balanced_geographies = _balanced_geographies(
        geography_list,
        cursor=cursor,
        country_counts=country_counts,
    )
    if not balanced_geographies:
        return []

    adaptive_groups={}
    cooldown_keys_by_category={}
    if adaptive_enabled:
        for category in pending:
            groups,cooldowns=_adaptive_country_geographies(
                balanced_geographies,
                category=category,
                yield_hints=yield_hints,
                daily_yield_hints=daily_yield_hints,
                exploration_bonus=exploration_bonus,
                cooldown_enabled=cooldown_enabled,
                cooldown_min_visits=cooldown_min_visits,
                cooldown_min_discovered=cooldown_min_discovered,
                cooldown_min_partitions=cooldown_min_partitions,
                score_mode=adaptive_score_mode,
            )
            adaptive_groups[category]=groups
            cooldown_keys_by_category[category]=cooldowns

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
                    score_mode=adaptive_score_mode,
                )
        route_key=yield_hint_key(category,geography)
        deferred_keys=cooldown_keys_by_category.get(category,set())
        cooldown_applied=route_key in deferred_keys

        plan.append(
            {
                "attempt": attempt + 1,
                "category": category,
                "geography": geography,
                "priority_weight": _category_weight(
                    int(counts.get(category, 0)),
                    target,
                    rescue_enabled=critical_deficit_rescue_enabled,
                    critical_ratio=critical_deficit_ratio,
                    critical_weight=critical_deficit_weight,
                    low_ratio=low_deficit_ratio,
                    low_weight=low_deficit_weight,
                    mid_ratio=mid_deficit_ratio,
                    mid_weight=mid_deficit_weight,
                ),
                "adaptive_yield_score":(
                    round(float(adaptive_score),6)
                    if adaptive_score is not None else None
                ),
                "adaptive_cooldown":cooldown_applied,
                "adaptive_cooldown_deferred_count":len(deferred_keys),
            }
        )
    return plan
