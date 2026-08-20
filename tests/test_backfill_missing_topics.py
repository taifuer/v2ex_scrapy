import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.backfill_missing_topics import (
    find_comment_issue_ids,
    find_interaction_issue_ids,
    find_quality_issue_ids,
    ids_to_ranges,
    summarize_comment_backfill,
)


class BackfillMissingTopicsTest(unittest.TestCase):
    def test_ids_to_ranges_collapses_consecutive_ids(self):
        self.assertEqual(
            ids_to_ranges([1, 2, 3, 6, 8, 9]),
            [(1, 3), (6, 6), (8, 9)],
        )

    def test_interaction_mode_selects_only_valid_unknown_topics(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "test.sqlite"
            with sqlite3.connect(database) as conn:
                conn.execute(
                    """
                    CREATE TABLE topic (
                        id INTEGER PRIMARY KEY,
                        clicks INTEGER NOT NULL,
                        favorite_count INTEGER NOT NULL,
                        thank_count INTEGER NOT NULL
                    )
                    """
                )
                conn.executemany(
                    "INSERT INTO topic VALUES (?, ?, ?, ?)",
                    [
                        (1, 10, -1, -1),
                        (2, 20, 3, -1),
                        (3, 30, 3, 2),
                        (4, -1, -1, -1),
                        (5, 40, -1, 0),
                    ],
                )

            self.assertEqual(
                find_interaction_issue_ids(database, end_id=5),
                [(1, 2), (5, 5)],
            )

    def test_quality_mode_includes_missing_authors(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "test.sqlite"
            with sqlite3.connect(database) as conn:
                conn.execute(
                    """
                    CREATE TABLE topic (
                        id INTEGER PRIMARY KEY, clicks INTEGER NOT NULL,
                        author TEXT NOT NULL, title TEXT NOT NULL,
                        node TEXT NOT NULL
                    )
                    """
                )
                conn.executemany(
                    "INSERT INTO topic VALUES (?, ?, ?, ?, ?)",
                    [
                        (1, 10, "", "title", "node"),
                        (2, 10, "alice", "", "node"),
                        (3, 10, "alice", "title", ""),
                        (4, 10, "alice", "title", "node"),
                        (5, -1, "", "", ""),
                    ],
                )

            self.assertEqual(find_quality_issue_ids(database, end_id=5), [(1, 3)])

    def test_comment_mode_selects_large_and_first_page_shortfalls(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "test.sqlite"
            with sqlite3.connect(database) as conn:
                conn.execute(
                    """
                    CREATE TABLE topic (
                        id INTEGER PRIMARY KEY,
                        title TEXT NOT NULL,
                        create_at INTEGER NOT NULL,
                        reply_count INTEGER NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE comment (
                        id INTEGER PRIMARY KEY,
                        topic_id INTEGER NOT NULL
                    )
                    """
                )
                conn.executemany(
                    "INSERT INTO topic VALUES (?, ?, ?, ?)",
                    [
                        (1, "complete", 1, 2),
                        (2, "first page", 1, 150),
                        (3, "large gap", 1, 220),
                        (4, "small deletion", 1, 3),
                        (5, "", 1, 500),
                    ],
                )
                comments = [(1, 1), (2, 1)]
                comments.extend((1000 + index, 2) for index in range(100))
                comments.extend((2000 + index, 3) for index in range(110))
                comments.extend([(3001, 4), (3002, 4)])
                conn.executemany("INSERT INTO comment VALUES (?, ?)", comments)

            self.assertEqual(
                find_comment_issue_ids(database, end_id=5),
                [(2, 3)],
            )

    def test_comment_backfill_summary_distinguishes_snapshot_shortfalls(self):
        before = {
            1: {"expected": 120, "actual": 90, "status_code": 200, "fetched_at": 1},
            2: {"expected": 150, "actual": 100, "status_code": 200, "fetched_at": 1},
            3: {"expected": 140, "actual": 99, "status_code": 200, "fetched_at": 1},
            4: {"expected": 110, "actual": 90, "status_code": 200, "fetched_at": 1},
        }
        after = {
            1: {"expected": 120, "actual": 100, "status_code": 200, "fetched_at": 20},
            2: {"expected": 150, "actual": 150, "status_code": 200, "fetched_at": 20},
            3: {"expected": 140, "actual": 99, "status_code": 404, "fetched_at": 20},
            4: {"expected": 110, "actual": 90, "status_code": 200, "fetched_at": 5},
        }

        report = summarize_comment_backfill(before, after, started_at=10)

        self.assertEqual(
            report["summary"],
            {
                "topics": 4,
                "recovered_topics": 2,
                "recovered_comments": 60,
                "resolved_topics": 1,
                "refreshed_shortfalls": 1,
                "inaccessible_topics": 1,
                "unverified_topics": 1,
            },
        )


if __name__ == "__main__":
    unittest.main()
