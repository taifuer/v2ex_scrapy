#!/usr/bin/env python3
"""Audit ranking coverage and optional source distributions for fixed thresholds."""

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v2ex_scrapy.analysis_policy import (  # noqa: E402
    PERIOD_POST_METRIC_MINIMUMS,
    REPRESENTATIVE_COMMENT_MIN_THANKS,
)

PUBLIC_DIR = ROOT / "analysis" / "v2ex-analysis" / "public"
SOURCE_DB = ROOT / "v2ex.sqlite"
POST_THANK_THRESHOLDS = tuple(
    sorted({1, 3, PERIOD_POST_METRIC_MINIMUMS["thank_count"], 10})
)
COMMENT_THANK_THRESHOLDS = tuple(
    sorted({1, REPRESENTATIVE_COMMENT_MIN_THANKS, 5, 10, 20})
)


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def generated_ranking_summary(index_name: str, period_key: str) -> dict:
    index = load_json(PUBLIC_DIR / index_name)
    periods = index[period_key]
    summary = {
        "periods": len(periods),
        "post_metric_minimums": index.get("post_metric_minimums", {}),
        "filtered_post_metrics": {
            metric: {"minimum": minimum, "posts": 0, "empty_periods": []}
            for metric, minimum in index.get("post_metric_minimums", {}).items()
        },
        "representative_comments": 0,
        "empty_comment_periods": [],
    }
    for period, filename in sorted(periods.items()):
        payload = load_json(PUBLIC_DIR / filename)
        payload = payload.get("ranking", payload)
        post_rankings = payload.get("post_rankings", {})
        comments = payload.get("comments", [])
        summary["representative_comments"] += len(comments)
        for metric, values in summary["filtered_post_metrics"].items():
            ranking = post_rankings.get(metric, [])
            values["posts"] += len(ranking)
            if not ranking:
                values["empty_periods"].append(period)
        if not comments:
            summary["empty_comment_periods"].append(period)
    return summary


def next_month(period: str) -> str:
    year, month = map(int, period.split("-"))
    if month == 12:
        return f"{year + 1}-01"
    return f"{year}-{month + 1:02d}"


def source_distribution() -> dict:
    overview = load_json(PUBLIC_DIR / "dynamic-overview.json")
    start_period = overview["metadata"]["start_period"]
    end_period = overview["metadata"]["default_end_period"]
    cutoff = next_month(end_period)
    connection = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro", uri=True)
    try:
        tracked_periods = load_json(
            PUBLIC_DIR / "dynamic-monthly-rankings-index.json"
        )["periods"]
        topic_counts = defaultdict(
            lambda: {value: 0 for value in POST_THANK_THRESHOLDS}
        )
        for period in tracked_periods:
            topic_counts[period]
        topic_rows = connection.execute(
            """
            SELECT strftime('%Y-%m', create_at, 'unixepoch') AS period,
                   thank_count
            FROM topic
            WHERE clicks >= 0
              AND strftime('%Y-%m', create_at, 'unixepoch') >= ?
              AND strftime('%Y-%m', create_at, 'unixepoch') < ?
              AND LOWER(node) != 'promotions'
            """,
            (start_period, cutoff),
        )
        for period, thank_count in topic_rows:
            for threshold in POST_THANK_THRESHOLDS:
                if thank_count >= threshold:
                    topic_counts[period][threshold] += 1

        comment_counts = {value: 0 for value in COMMENT_THANK_THRESHOLDS}
        for (thank_count,) in connection.execute(
            """
            SELECT thank_count
            FROM comment
            WHERE strftime('%Y-%m', create_at, 'unixepoch') >= ?
              AND strftime('%Y-%m', create_at, 'unixepoch') < ?
              AND LOWER(commenter) != 'usdc'
            """,
            (start_period, cutoff),
        ):
            for threshold in COMMENT_THANK_THRESHOLDS:
                if thank_count >= threshold:
                    comment_counts[threshold] += 1
    finally:
        connection.close()

    return {
        "post_thanks": {
            str(threshold): {
                "posts": sum(values[threshold] for values in topic_counts.values()),
                "empty_months": sum(values[threshold] == 0 for values in topic_counts.values()),
            }
            for threshold in POST_THANK_THRESHOLDS
        },
        "comment_thanks": {
            str(threshold): count for threshold, count in comment_counts.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scan-source",
        action="store_true",
        help="also scan v2ex.sqlite to compare candidate thresholds",
    )
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args()

    report = {
        "monthly": generated_ranking_summary(
            "dynamic-monthly-rankings-index.json", "periods"
        ),
        "annual": generated_ranking_summary(
            "dynamic-annual-rankings-index.json", "years"
        ),
    }
    if args.scan_source:
        report["source_distribution"] = source_distribution()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    for label in ("monthly", "annual"):
        values = report[label]
        print(
            f"{label}: {values['periods']} periods, "
            f"{values['representative_comments']} representative comments"
        )
        for metric, metric_values in values["filtered_post_metrics"].items():
            print(
                f"  {metric} >= {metric_values['minimum']}: "
                f"{metric_values['posts']} posts, "
                f"{len(metric_values['empty_periods'])} empty periods"
            )
    if args.scan_source:
        print(json.dumps(report["source_distribution"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
