import argparse
import json
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v2ex_scrapy.data_quality import find_comment_gaps


def find_missing_ranges(database: Path, end_id: int) -> list[tuple[int, int]]:
    with sqlite3.connect(database) as conn:
        rows = conn.execute(
            """
            WITH ordered AS (
                SELECT id, lag(id, 1, 0) OVER (ORDER BY id) AS previous_id
                FROM topic
                WHERE id <= ?
            )
            SELECT previous_id + 1, id - 1
            FROM ordered
            WHERE id > previous_id + 1
            ORDER BY id
            """,
            (end_id,),
        ).fetchall()
        max_id = conn.execute(
            "SELECT COALESCE(MAX(id), 0) FROM topic WHERE id <= ?", (end_id,)
        ).fetchone()[0]

    ranges = [(int(start), int(end)) for start, end in rows]
    if max_id < end_id:
        ranges.append((int(max_id) + 1, end_id))
    return ranges


def format_ranges(ranges: list[tuple[int, int]]) -> str:
    return ",".join(
        str(start) if start == end else f"{start}-{end}" for start, end in ranges
    )


def ids_to_ranges(topic_ids: list[int]) -> list[tuple[int, int]]:
    if not topic_ids:
        return []

    ranges = []
    start = previous = topic_ids[0]
    for topic_id in topic_ids[1:]:
        if topic_id == previous + 1:
            previous = topic_id
            continue
        ranges.append((start, previous))
        start = previous = topic_id
    ranges.append((start, previous))
    return ranges


def find_quality_issue_ids(database: Path, end_id: int) -> list[tuple[int, int]]:
    with sqlite3.connect(database) as conn:
        rows = conn.execute(
            """
            SELECT id
            FROM topic
            WHERE id <= ?
              AND clicks >= 0
              AND (node = '' OR title = '' OR author = '')
            ORDER BY id
            """,
            (end_id,),
        ).fetchall()
    return ids_to_ranges([int(topic_id) for (topic_id,) in rows])


def find_interaction_issue_ids(database: Path, end_id: int) -> list[tuple[int, int]]:
    with sqlite3.connect(database) as conn:
        rows = conn.execute(
            """
            SELECT id
            FROM topic
            WHERE id <= ?
              AND clicks >= 0
              AND (favorite_count < 0 OR thank_count < 0)
            ORDER BY id
            """,
            (end_id,),
        ).fetchall()
    return ids_to_ranges([int(topic_id) for (topic_id,) in rows])


def find_comment_issue_ids(
    database: Path,
    end_id: int,
    minimum_gap: int = 100,
    include_first_page_shortfall: bool = True,
) -> list[tuple[int, int]]:
    with sqlite3.connect(database) as conn:
        gaps = find_comment_gaps(
            conn,
            end_id=end_id,
            minimum_gap=minimum_gap,
            include_first_page_shortfall=include_first_page_shortfall,
        )
    return ids_to_ranges([item.topic_id for item in gaps])


def read_comment_backfill_state(
    database: Path,
    topic_ids: list[int],
) -> dict[int, dict[str, int | None]]:
    if not topic_ids:
        return {}
    placeholders = ",".join("?" for _ in topic_ids)
    with sqlite3.connect(database) as conn:
        rows = conn.execute(
            f"""
            SELECT topic.id,
                   topic.reply_count,
                   COUNT(comment.id),
                   topic_fetch_state.last_status_code,
                   topic_fetch_state.last_fetched_at
            FROM topic
            LEFT JOIN comment ON comment.topic_id = topic.id
            LEFT JOIN topic_fetch_state
              ON topic_fetch_state.topic_id = topic.id
            WHERE topic.id IN ({placeholders})
            GROUP BY topic.id
            """,
            topic_ids,
        ).fetchall()
    return {
        int(topic_id): {
            "expected": int(expected),
            "actual": int(actual),
            "status_code": int(status_code) if status_code is not None else None,
            "fetched_at": int(fetched_at) if fetched_at is not None else None,
        }
        for topic_id, expected, actual, status_code, fetched_at in rows
    }


def summarize_comment_backfill(
    before: dict[int, dict[str, int | None]],
    after: dict[int, dict[str, int | None]],
    started_at: int,
) -> dict:
    summary = {
        "topics": len(before),
        "recovered_topics": 0,
        "recovered_comments": 0,
        "resolved_topics": 0,
        "refreshed_shortfalls": 0,
        "inaccessible_topics": 0,
        "unverified_topics": 0,
    }
    details = []
    for topic_id, previous in sorted(before.items()):
        current = after.get(topic_id, previous)
        recovered = max(0, int(current["actual"] or 0) - int(previous["actual"] or 0))
        expected = int(current["expected"] or 0)
        actual = int(current["actual"] or 0)
        fetched_at = current["fetched_at"]
        status_code = current["status_code"]
        if recovered:
            summary["recovered_topics"] += 1
            summary["recovered_comments"] += recovered
        if fetched_at is None or int(fetched_at) < started_at:
            classification = "unverified"
            summary["unverified_topics"] += 1
        elif status_code != 200:
            classification = "inaccessible"
            summary["inaccessible_topics"] += 1
        elif actual >= expected:
            classification = "resolved"
            summary["resolved_topics"] += 1
        else:
            classification = "reply_snapshot_shortfall"
            summary["refreshed_shortfalls"] += 1
        details.append(
            {
                "topic_id": topic_id,
                "expected": expected,
                "before": int(previous["actual"] or 0),
                "after": actual,
                "recovered": recovered,
                "status_code": status_code,
                "classification": classification,
            }
        )
    return {"summary": summary, "topics": details}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--end-id", type=int, required=True)
    parser.add_argument(
        "--mode",
        choices=("missing", "quality", "interactions", "comments"),
        default="missing",
    )
    parser.add_argument(
        "--comment-gap-min",
        type=int,
        default=100,
        help="Minimum reply-snapshot shortfall selected by comments mode.",
    )
    parser.add_argument(
        "--no-first-page-shortfall",
        action="store_true",
        help="Do not include topics reporting over 100 replies with at most 100 stored comments.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the selected count without starting Scrapy.",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Write a JSON before/after classification report for comments mode.",
    )
    args = parser.parse_args()

    database = ROOT / "v2ex.sqlite"
    if args.mode == "missing":
        ranges = find_missing_ranges(database, args.end_id)
    elif args.mode == "quality":
        ranges = find_quality_issue_ids(database, args.end_id)
    elif args.mode == "interactions":
        ranges = find_interaction_issue_ids(database, args.end_id)
    else:
        ranges = find_comment_issue_ids(
            database,
            args.end_id,
            minimum_gap=max(1, args.comment_gap_min),
            include_first_page_shortfall=not args.no_first_page_shortfall,
        )
    topic_ids = format_ranges(ranges)
    if topic_ids == "":
        print(f"No topic IDs found for {args.mode} backfill.")
        return

    topic_count = sum(end - start + 1 for start, end in ranges)
    print(
        f"Backfilling {topic_count} topics in {len(ranges)} ranges "
        f"for mode={args.mode}.",
        flush=True,
    )
    if args.dry_run:
        return

    selected_ids = [
        topic_id
        for start, end in ranges
        for topic_id in range(start, end + 1)
    ]
    before = (
        read_comment_backfill_state(database, selected_ids)
        if args.mode == "comments"
        else {}
    )
    started_at = int(time.time())

    with tempfile.NamedTemporaryFile("w", encoding="utf-8") as topic_file:
        topic_file.write(topic_ids)
        topic_file.flush()
        subprocess.run(
            [
                str(ROOT / ".venv" / "bin" / "scrapy"),
                "crawl",
                "v2ex",
                "-a",
                f"topic_ids_file={topic_file.name}",
                "-a",
                "force_update=true",
                "-a",
                f"refresh_comments={'true' if args.mode == 'comments' else 'false'}",
                "-a",
                f"crawl_purpose=backfill-{args.mode}",
                *(
                    ["-a", "crawl_members=false"]
                    if args.mode != "missing"
                    else []
                ),
                "-s",
                f"LOG_LEVEL={args.log_level}",
            ],
            cwd=ROOT,
            check=True,
        )

    if args.mode == "comments":
        report = summarize_comment_backfill(
            before,
            read_comment_backfill_state(database, selected_ids),
            started_at,
        )
        summary = report["summary"]
        print(
            "Comment refresh result: "
            f"{summary['recovered_comments']} comments recovered across "
            f"{summary['recovered_topics']} topics; "
            f"{summary['refreshed_shortfalls']} accessible topics remain below "
            "their cumulative reply snapshots; "
            f"{summary['inaccessible_topics']} topics were inaccessible; "
            f"{summary['unverified_topics']} topics were not verified.",
            flush=True,
        )
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )


if __name__ == "__main__":
    main()
