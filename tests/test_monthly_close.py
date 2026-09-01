import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from scripts.run_monthly_close import (
    MonthWindow,
    close_status,
    close_scrapy_command,
    load_month_source,
    month_snapshot,
    parse_month,
    ready_at,
    validate_maturity,
    validate_source_coverage,
)
from scripts.run_incremental_crawl import LOCAL_TIMEZONE


class MonthlyCloseTest(unittest.TestCase):
    def timestamp(self, value: str) -> int:
        return int(datetime.fromisoformat(value).timestamp())

    def create_database(self, path: Path) -> None:
        with sqlite3.connect(path) as conn:
            conn.executescript(
                """
                CREATE TABLE topic (
                    id INTEGER PRIMARY KEY, create_at INTEGER NOT NULL,
                    title TEXT NOT NULL, author TEXT NOT NULL, node TEXT NOT NULL,
                    clicks INTEGER NOT NULL, reply_count INTEGER NOT NULL,
                    favorite_count INTEGER NOT NULL, thank_count INTEGER NOT NULL,
                    votes INTEGER NOT NULL
                );
                CREATE TABLE comment (id INTEGER PRIMARY KEY, topic_id INTEGER NOT NULL);
                CREATE TABLE topic_fetch_state (
                    topic_id INTEGER PRIMARY KEY, last_status_code INTEGER NOT NULL,
                    last_fetched_at INTEGER NOT NULL
                );
                """
            )

    def test_month_window_and_grace_period_use_shanghai_time(self):
        window = parse_month("2026-07")
        self.assertEqual(
            window.start_timestamp,
            int(datetime(2026, 7, 1, tzinfo=LOCAL_TIMEZONE).timestamp()),
        )
        self.assertEqual(
            ready_at(window, 7),
            int(datetime(2026, 8, 8, tzinfo=LOCAL_TIMEZONE).timestamp()),
        )
        with self.assertRaisesRegex(RuntimeError, "still maturing"):
            validate_maturity(
                window,
                7,
                int(datetime(2026, 8, 7, tzinfo=LOCAL_TIMEZONE).timestamp()),
                allow_early=False,
            )

    def test_source_requires_final_fetch_states_and_a_later_topic(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "test.sqlite"
            self.create_database(database)
            july = parse_month("2026-07")
            with sqlite3.connect(database) as conn:
                conn.executemany(
                    "INSERT INTO topic VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            9,
                            self.timestamp("2026-07-01T00:30:00+08:00"),
                            "unknown", "a", "qna", -1, -1, -1, -1, -1,
                        ),
                        (
                            10,
                            self.timestamp("2026-07-01T01:00:00+08:00"),
                            "first", "a", "qna", 10, 2, 1, 1, 0,
                        ),
                        (
                            12,
                            self.timestamp("2026-07-31T23:00:00+08:00"),
                            "last", "b", "qna", 20, 3, 2, 1, 1,
                        ),
                        (
                            13,
                            self.timestamp("2026-08-01T00:01:00+08:00"),
                            "next", "c", "qna", 5, 0, 0, 0, 0,
                        ),
                    ],
                )
                conn.executemany(
                    "INSERT INTO topic_fetch_state VALUES (?, ?, ?)",
                    [(9, 200, 1), (10, 200, 1), (11, 404, 1), (12, 200, 1)],
                )
                conn.executemany(
                    "INSERT INTO comment VALUES (?, ?)", [(1, 10), (2, 12)]
                )

            source = load_month_source(database, july)
            validate_source_coverage(source, july, allow_incomplete=False)

            self.assertEqual(source.topic_ids, [9, 10, 12])
            self.assertEqual(source.candidate_ids, 4)
            self.assertEqual(source.unverified_ids, 0)
            snapshot = month_snapshot(database, july)
            self.assertEqual(snapshot["comments"], 2)
            self.assertEqual(snapshot["reply_snapshot"], 5)
            self.assertEqual(snapshot["votes"], 1)

    def test_source_rejects_an_untracked_id(self):
        source = SimpleNamespace(
            source_max_created_at=parse_month("2026-08").start_timestamp,
            unverified_ids=1,
        )
        with self.assertRaisesRegex(RuntimeError, "neither a topic row"):
            validate_source_coverage(
                source, parse_month("2026-07"), allow_incomplete=False
            )

    def test_source_refreshes_placeholder_rows_inside_the_month_id_range(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "test.sqlite"
            self.create_database(database)
            july = parse_month("2026-07")
            with sqlite3.connect(database) as conn:
                conn.executemany(
                    "INSERT INTO topic VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            10,
                            self.timestamp("2026-07-01T01:00:00+08:00"),
                            "first", "a", "qna", 10, 2, 1, 1, 0,
                        ),
                        (11, 0, "", "", "", -1, -1, -1, -1, -1),
                        (
                            12,
                            self.timestamp("2026-07-31T23:00:00+08:00"),
                            "last", "b", "qna", 20, 3, 2, 1, 1,
                        ),
                        (
                            13,
                            self.timestamp("2026-08-01T00:01:00+08:00"),
                            "next", "c", "qna", 5, 0, 0, 0, 0,
                        ),
                    ],
                )
                conn.executemany(
                    "INSERT INTO topic_fetch_state VALUES (?, ?, ?)",
                    [(10, 200, 1), (11, 200, 1), (12, 200, 1)],
                )

            source = load_month_source(database, july)

            self.assertEqual(source.topic_ids, [10, 11, 12])
            self.assertEqual(source.unverified_ids, 0)

    def test_close_command_forces_topic_and_comment_refresh_without_members(self):
        plan = {
            "topic_ids_file": "/tmp/topic-ids.txt",
            "crawl_purpose": "month-close-2026-07",
        }
        args = SimpleNamespace(
            log_level="INFO",
            concurrency=1,
            delay=1.0,
            auto_throttle=False,
        )

        command = close_scrapy_command(plan, args)

        self.assertIn("topic_ids_file=/tmp/topic-ids.txt", command)
        self.assertIn("force_update=true", command)
        self.assertIn("crawl_members=false", command)
        self.assertIn("AUTOTHROTTLE_ENABLED=false", command)

    def test_invalid_month_is_rejected(self):
        with self.assertRaises(Exception):
            parse_month("2026-13")
        with self.assertRaises(Exception):
            parse_month("2026-7")

    def test_status_separates_inaccessible_topics_from_retryable_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "test.sqlite"
            ids_file = root / "topic-ids.txt"
            ids_file.write_text("10-13\n", encoding="utf-8")
            with sqlite3.connect(database) as conn:
                conn.executescript(
                    """
                    CREATE TABLE topic (
                        id INTEGER PRIMARY KEY, create_at INTEGER NOT NULL,
                        title TEXT NOT NULL, author TEXT NOT NULL, node TEXT NOT NULL,
                        clicks INTEGER NOT NULL, reply_count INTEGER NOT NULL,
                        favorite_count INTEGER NOT NULL, thank_count INTEGER NOT NULL,
                        votes INTEGER NOT NULL
                    );
                    CREATE TABLE topic_fetch_state (
                        topic_id INTEGER PRIMARY KEY, last_status_code INTEGER NOT NULL,
                        last_fetched_at INTEGER NOT NULL
                    );
                    CREATE TABLE crawl_run (
                        id INTEGER PRIMARY KEY, started_at INTEGER NOT NULL,
                        finished_at INTEGER, close_reason TEXT NOT NULL,
                        response_count INTEGER NOT NULL, error_count INTEGER NOT NULL,
                        configuration TEXT NOT NULL
                    );
                    INSERT INTO topic_fetch_state VALUES (10, 200, 101);
                    INSERT INTO topic_fetch_state VALUES (11, 404, 101);
                    INSERT INTO topic_fetch_state VALUES (12, 200, 101);
                    INSERT INTO topic_fetch_state VALUES (13, -1, 101);
                    INSERT INTO topic VALUES (10, 100, 'valid', 'a', 'qna', 1, 1, 1, 1, 1);
                    INSERT INTO topic VALUES (12, 100, 'invalid', 'b', 'qna', -1, -1, -1, -1, -1);
                    """
                )
            plan = {
                "topic_ids_file": str(ids_file),
                "created_at": 100,
                "crawl_purpose": "month-close-2026-07",
                "unit": None,
            }

            status = close_status(database, plan)

            self.assertEqual(status["fresh"], 4)
            self.assertEqual(status["refreshed"], 1)
            self.assertEqual(status["inaccessible_ids"], [11])
            self.assertEqual(status["retry_ids"], [12, 13])


if __name__ == "__main__":
    unittest.main()
