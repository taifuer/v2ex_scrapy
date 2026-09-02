import math
from collections import defaultdict
from statistics import median
from typing import Iterable, Mapping


STAGE_HOTSPOT_ROW_SCHEMA = [
    "key",
    "start_period",
    "peak_period",
    "end_period",
    "peak_count",
    "peak_share_percent",
    "baseline_share_percent",
    "lift",
    "score",
]

STAGE_HOTSPOT_RULES = {
    "month": {
        "baseline_periods": 12,
        "minimum_history": 6,
        "minimum_count": 20,
        "minimum_lift": 1.8,
        "minimum_share_delta": 0.0003,
    },
    "year": {
        "baseline_periods": 3,
        "minimum_history": 2,
        "minimum_count": 50,
        "minimum_lift": 1.5,
        "minimum_share_delta": 0.0005,
    },
}


def _bucket(period: str, grain: str) -> str:
    return period[:4] if grain == "year" else period


def _episodes(marked_indices: list[int]) -> list[list[int]]:
    episodes: list[list[int]] = []
    for index in marked_indices:
        if not episodes or index - episodes[-1][-1] > 2:
            episodes.append([index])
        else:
            episodes[-1].append(index)
    return episodes


def _stage_hotspots_for_grain(
    rows: list[tuple[str, str, int]],
    monthly_totals: Mapping[str, int],
    grain: str,
) -> list[list]:
    rules = STAGE_HOTSPOT_RULES[grain]
    periods = sorted({_bucket(period, grain) for period in monthly_totals})
    if len(periods) < rules["minimum_history"] + 1:
        return []

    totals: dict[str, int] = defaultdict(int)
    for period, count in monthly_totals.items():
        totals[_bucket(period, grain)] += int(count)

    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for period, key, count in rows:
        bucket = _bucket(period, grain)
        if bucket in totals:
            counts[key][bucket] += int(count)

    hotspots = []
    for key, values in counts.items():
        item_counts = [values.get(period, 0) for period in periods]
        shares = [
            count / max(1, totals[period])
            for period, count in zip(periods, item_counts)
        ]
        baselines = []
        for index in range(len(periods)):
            history = shares[
                max(0, index - rules["baseline_periods"]):index
            ]
            baselines.append(
                median(history)
                if len(history) >= rules["minimum_history"]
                else 0
            )

        marked = []
        for index, period in enumerate(periods):
            if (
                index < rules["minimum_history"]
                or item_counts[index] < rules["minimum_count"]
            ):
                continue
            observation_floor = 1 / max(1, totals[period])
            lift = (
                (shares[index] + observation_floor)
                / (baselines[index] + observation_floor)
            )
            if (
                lift >= rules["minimum_lift"]
                and shares[index] - baselines[index]
                >= rules["minimum_share_delta"]
            ):
                marked.append(index)

        for episode in _episodes(marked):
            peak_index = max(
                episode,
                key=lambda index: (
                    (shares[index] - baselines[index])
                    * math.log1p(item_counts[index]),
                    item_counts[index],
                ),
            )
            start_index = episode[0]
            end_index = episode[-1]
            continuation_share = max(
                baselines[peak_index] * 1.25,
                shares[peak_index] * 0.35,
            )
            continuation_count = max(5, rules["minimum_count"] // 2)
            while (
                start_index > 0
                and shares[start_index - 1] >= continuation_share
                and item_counts[start_index - 1] >= continuation_count
            ):
                start_index -= 1
            while (
                end_index + 1 < len(periods)
                and shares[end_index + 1] >= continuation_share
                and item_counts[end_index + 1] >= continuation_count
            ):
                end_index += 1

            baseline_share = baselines[peak_index]
            score = (
                (shares[peak_index] - baseline_share)
                * 10_000
                * math.log1p(item_counts[peak_index])
            )
            hotspots.append([
                key,
                periods[start_index],
                periods[peak_index],
                periods[end_index],
                item_counts[peak_index],
                round(shares[peak_index] * 100, 5),
                round(baseline_share * 100, 5),
                (
                    round(shares[peak_index] / baseline_share, 3)
                    if baseline_share > 0
                    else None
                ),
                round(score, 4),
            ])

    return sorted(
        hotspots,
        key=lambda item: (-item[8], -item[4], item[0].casefold(), item[2]),
    )


def build_stage_hotspots(
    rows: Iterable[tuple[str, str, int]],
    monthly_totals: Mapping[str, int],
) -> dict:
    rows = list(rows)
    return {
        "row_schema": STAGE_HOTSPOT_ROW_SCHEMA,
        "rules": STAGE_HOTSPOT_RULES,
        "month": _stage_hotspots_for_grain(rows, monthly_totals, "month"),
        "year": _stage_hotspots_for_grain(rows, monthly_totals, "year"),
        "method": (
            "以过去 12 个月（月度）或 3 年（年度）的帖子占比中位数为基线，"
            "识别达到最低帖子量、占比增量和相对增幅的连续阶段。"
        ),
    }
