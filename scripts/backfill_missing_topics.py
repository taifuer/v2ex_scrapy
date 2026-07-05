import argparse
import sqlite3
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


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


def find_quality_issue_ids(database: Path, end_id: int) -> list[tuple[int, int]]:
    with sqlite3.connect(database) as conn:
        rows = conn.execute(
            """
            SELECT id
            FROM topic
            WHERE id <= ?
              AND clicks >= 0
              AND (node = '' OR title = '')
            ORDER BY id
            """,
            (end_id,),
        ).fetchall()
    return [(int(topic_id), int(topic_id)) for (topic_id,) in rows]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--end-id", type=int, required=True)
    parser.add_argument(
        "--mode",
        choices=("missing", "quality"),
        default="missing",
    )
    args = parser.parse_args()

    database = ROOT / "v2ex.sqlite"
    ranges = (
        find_missing_ranges(database, args.end_id)
        if args.mode == "missing"
        else find_quality_issue_ids(database, args.end_id)
    )
    topic_ids = format_ranges(ranges)
    if topic_ids == "":
        print("No missing topic IDs found.")
        return

    subprocess.run(
        [
            str(ROOT / ".venv" / "bin" / "scrapy"),
            "crawl",
            "v2ex",
            "-a",
            f"topic_ids={topic_ids}",
            "-a",
            "force_update=true",
            "-s",
            "LOG_LEVEL=INFO",
        ],
        cwd=ROOT,
        check=True,
    )


if __name__ == "__main__":
    main()
