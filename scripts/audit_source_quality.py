#!/usr/bin/env python3
import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v2ex_scrapy.data_quality import (
    crawl_tracking_summary,
    filter_severe_comment_gaps,
    find_all_comment_gaps,
    quality_metrics,
    quality_regressions,
    serialize_comment_gaps,
    source_quality_summary,
)

DEFAULT_BASELINE = ROOT / "analysis" / "source_quality_baseline.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=ROOT / "v2ex.sqlite")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--details", type=int, default=10)
    parser.add_argument("--comment-gap-min", type=int, default=100)
    parser.add_argument("--fail-on-severe", action="store_true")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("--fail-on-regression", action="store_true")
    args = parser.parse_args()

    with sqlite3.connect(args.database) as conn:
        max_topic_id = int(
            conn.execute("SELECT COALESCE(MAX(id), 0) FROM topic").fetchone()[0]
        )
        all_comment_gaps = find_all_comment_gaps(conn, end_id=max_topic_id)
        summary = source_quality_summary(conn, comment_gaps=all_comment_gaps)
        crawl_tracking = crawl_tracking_summary(conn)
        gaps = filter_severe_comment_gaps(
            all_comment_gaps,
            minimum_gap=max(1, args.comment_gap_min),
        )

    metrics = quality_metrics(summary, gaps)
    if args.write_baseline:
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(
            json.dumps(
                {
                    "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "max_topic_id": summary["topics"]["max_id"],
                    "maximums": metrics,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    baseline = (
        json.loads(args.baseline.read_text(encoding="utf-8"))
        if args.baseline.exists()
        else {}
    )
    if args.fail_on_regression and not baseline:
        raise SystemExit(
            f"Quality baseline is missing: {args.baseline}. "
            "Create it with --write-baseline after reviewing the audit."
        )
    regressions = quality_regressions(metrics, baseline.get("maximums", {}))
    payload = {
        "summary": summary,
        "severe_comment_gaps": {
            "count": len(gaps),
            "reply_snapshot_shortfall": sum(item.gap for item in gaps),
            "interpretation": (
                "Reply counts are cumulative snapshots and can include deleted "
                "comments. A shortfall is an audit candidate, not proof that the "
                "crawler can recover additional comments."
            ),
            "examples": serialize_comment_gaps(
                sorted(gaps, key=lambda item: (-item.gap, item.topic_id))[: args.details]
            ),
        },
        "quality_metrics": metrics,
        "crawl_tracking": crawl_tracking,
        "baseline": str(args.baseline) if baseline else None,
        "regressions": regressions,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            "Topics: {valid_time:,} valid-time records, {placeholders:,} placeholders; "
            "{empty_title:,} empty titles, {empty_author:,} empty authors, "
            "{empty_node:,} empty nodes.".format(
                **summary["topics"]
            )
        )
        print(
            "Comments: {total:,} stored; {invalid_commenter:,} invalid commenters, "
            "{invalid_number:,} invalid floor numbers; {topics:,} topics are below "
            "their reply snapshot by {comments:,} comments.".format(
                **summary["comments"], **summary["comment_gaps"]
            )
        )
        print(
            f"Large reply-snapshot shortfalls: {len(gaps):,} topics, "
            f"{sum(item.gap for item in gaps):,} fewer stored comment rows than "
            "the cumulative topic snapshots."
        )
        if gaps:
            print(
                "  These are audit candidates, not confirmed crawl omissions; "
                "deleted replies remain included in V2EX reply snapshots."
            )
        for item in payload["severe_comment_gaps"]["examples"]:
            print(
                f"  #{item['topic_id']}: expected {item['expected']:,}, "
                f"stored {item['actual']:,}, gap {item['gap']:,}"
            )
        if baseline:
            print(
                f"Quality baseline: {len(regressions)} regression(s) against "
                f"{args.baseline}."
            )
            for item in regressions:
                print(
                    f"  {item['metric']}: {item['actual']:,} exceeds "
                    f"{item['maximum']:,}"
                )
        latest_run = crawl_tracking["latest_run"]
        if latest_run:
            print(
                f"Latest crawl run #{latest_run['id']}: {latest_run['close_reason']}; "
                f"{crawl_tracking['tracked_topics']:,} topics have fetch state."
            )

    if args.fail_on_severe and gaps:
        raise SystemExit(1)
    if args.fail_on_regression and regressions:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
