import argparse
import sqlite3
import subprocess
import sys
import tempfile
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
        help="Minimum missing comment count selected by comments mode.",
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


if __name__ == "__main__":
    main()
