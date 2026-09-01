import json
import sqlite3
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from scripts.run_incremental_crawl import (
    TopicProbe,
    crawl_report,
    crawl_status,
    cutoff_timestamp,
    ids_to_ranges,
    locate_date_boundary,
    scrapy_command,
    systemd_command,
    validate_explicit_boundary,
)


class IncrementalCrawlTest(unittest.TestCase):
    def timestamp(self, value: str) -> int:
        return int(datetime.fromisoformat(value).timestamp())

    def test_cutoff_uses_next_midnight_in_shanghai(self):
        actual = cutoff_timestamp(date(2026, 8, 20))
        expected = int(
            datetime(2026, 8, 21, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp()
        )
        self.assertEqual(actual, expected)

    def test_boundary_locator_tolerates_inaccessible_ids(self):
        probes = {
            100: TopicProbe(100, 200, self.timestamp("2026-08-20T22:00:00+08:00")),
            101: TopicProbe(101, 404),
            102: TopicProbe(102, 200, self.timestamp("2026-08-20T23:59:00+08:00")),
            103: TopicProbe(103, 404),
            104: TopicProbe(104, 200, self.timestamp("2026-08-21T00:02:00+08:00")),
            105: TopicProbe(105, 200, self.timestamp("2026-08-21T00:05:00+08:00")),
        }

        actual = locate_date_boundary(
            probes.__getitem__,
            probes[100],
            latest_id=105,
            cutoff=cutoff_timestamp(date(2026, 8, 20)),
            final_scan_size=2,
        )

        self.assertEqual(actual, 103)

    def test_explicit_boundary_requires_valid_topics_on_both_sides(self):
        probes = {
            200: TopicProbe(200, 200, self.timestamp("2026-08-20T23:59:00+08:00")),
            201: TopicProbe(201, 404),
            202: TopicProbe(202, 200, self.timestamp("2026-08-21T00:01:00+08:00")),
        }
        before, after = validate_explicit_boundary(
            probes.get,
            end_id=201,
            cutoff=cutoff_timestamp(date(2026, 8, 20)),
            scan_distance=1,
        )
        self.assertEqual(before.topic_id, 200)
        self.assertEqual(after.topic_id, 202)

    def test_commands_keep_concurrency_and_runtime_environment_explicit(self):
        plan = {
            "start_id": 10,
            "end_id": 20,
            "crawl_purpose": "incremental-through-2026-08-20",
            "unit": "v2ex-test",
            "through": "2026-08-20",
            "job_dir": "/tmp/v2ex-test",
        }
        args = SimpleNamespace(
            no_members=False,
            log_level="INFO",
            concurrency=2,
            delay=1.0,
            auto_throttle=False,
            cookie_file=Path("/root/.v2"),
        )
        command = scrapy_command(plan, args)
        launch = systemd_command(
            plan, args, command, {"HTTPS_PROXY": "http://127.0.0.1:7897"}
        )
        self.assertIn("CONCURRENT_REQUESTS=2", command)
        self.assertIn("CONCURRENT_REQUESTS_PER_DOMAIN=2", command)
        self.assertIn("AUTOTHROTTLE_ENABLED=false", command)
        self.assertIn("--setenv=V2EX_COOKIES_FILE=/root/.v2", launch)
        self.assertIn("--setenv=HTTPS_PROXY=http://127.0.0.1:7897", launch)

    def test_report_retries_network_failures_and_invalid_200_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "test.sqlite"
            with sqlite3.connect(database) as conn:
                conn.executescript(
                    """
                    CREATE TABLE topic (
                        id INTEGER PRIMARY KEY, create_at INTEGER NOT NULL,
                        title TEXT NOT NULL, author TEXT NOT NULL,
                        node TEXT NOT NULL, clicks INTEGER NOT NULL,
                        reply_count INTEGER NOT NULL, favorite_count INTEGER NOT NULL,
                        thank_count INTEGER NOT NULL, votes INTEGER NOT NULL
                    );
                    CREATE TABLE comment (id INTEGER PRIMARY KEY, topic_id INTEGER NOT NULL);
                    CREATE TABLE member (uid INTEGER, username TEXT);
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
                    """
                )
                before = self.timestamp("2026-08-20T23:00:00+08:00")
                after = self.timestamp("2026-08-21T00:01:00+08:00")
                conn.executemany(
                    "INSERT INTO topic VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (10, before, "valid", "alice", "python", 10, 2, 1, 1, 0),
                        (11, 0, "", "", "", -1, -1, -1, -1, -1),
                        (12, 0, "", "", "", -1, -1, -1, -1, -1),
                        (14, after, "late", "bob", "qna", 5, 0, 0, 0, 0),
                    ],
                )
                conn.executemany(
                    "INSERT INTO topic_fetch_state VALUES (?, ?, ?)",
                    [
                        (10, 200, 100),
                        (11, 404, 100),
                        (12, 200, 100),
                        (13, -1, 100),
                        (14, 200, 100),
                    ],
                )
                conn.execute("INSERT INTO comment VALUES (1, 10)")
                conn.execute("INSERT INTO member VALUES (1, 'alice')")
                conn.execute(
                    "INSERT INTO crawl_run VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        1,
                        100,
                        110,
                        "finished",
                        5,
                        1,
                        json.dumps({"crawl_purpose": "incremental-through-2026-08-20"}),
                    ),
                )
            plan = {
                "through": "2026-08-20",
                "start_id": 10,
                "end_id": 14,
                "cutoff_timestamp": cutoff_timestamp(date(2026, 8, 20)),
                "baseline": {"topics": 0, "comments": 0, "members": 0},
                "created_at": 90,
                "crawl_purpose": "incremental-through-2026-08-20",
                "unit": None,
            }

            report = crawl_report(database, plan)

            self.assertEqual(report["topics"]["valid"], 2)
            self.assertEqual(report["topics"]["placeholders"], 2)
            self.assertEqual(report["topics"]["missing"], 1)
            self.assertEqual(report["topics"]["out_of_range"], 1)
            self.assertEqual(report["topics"]["unknown_interactions"], 2)
            self.assertEqual(report["fetch"]["retry_ids"], [12, 13])

            status = crawl_status(database, plan)
            self.assertEqual(status["tracked"], 5)
            self.assertEqual(status["valid_topics"], 2)
            self.assertEqual(status["placeholders"], 2)

    def test_report_does_not_retry_a_confirmed_404_without_a_topic_row(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "test.sqlite"
            with sqlite3.connect(database) as conn:
                conn.executescript(
                    """
                    CREATE TABLE topic (
                        id INTEGER PRIMARY KEY, create_at INTEGER NOT NULL,
                        title TEXT NOT NULL, author TEXT NOT NULL,
                        node TEXT NOT NULL, clicks INTEGER NOT NULL,
                        reply_count INTEGER NOT NULL, favorite_count INTEGER NOT NULL,
                        thank_count INTEGER NOT NULL, votes INTEGER NOT NULL
                    );
                    CREATE TABLE comment (id INTEGER PRIMARY KEY, topic_id INTEGER NOT NULL);
                    CREATE TABLE member (uid INTEGER, username TEXT);
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
                    INSERT INTO topic_fetch_state VALUES (10, 404, 100);
                    """
                )
            plan = {
                "through": "2026-08-20",
                "start_id": 10,
                "end_id": 10,
                "cutoff_timestamp": cutoff_timestamp(date(2026, 8, 20)),
                "baseline": {"topics": 0, "comments": 0, "members": 0},
                "created_at": 90,
                "crawl_purpose": "incremental-through-2026-08-20",
                "unit": None,
            }

            report = crawl_report(database, plan)

            self.assertEqual(report["topics"]["missing"], 1)
            self.assertEqual(report["fetch"]["retry_ids"], [])

    def test_report_retries_a_success_response_without_a_topic_row(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "test.sqlite"
            with sqlite3.connect(database) as conn:
                conn.executescript(
                    """
                    CREATE TABLE topic (
                        id INTEGER PRIMARY KEY, create_at INTEGER NOT NULL,
                        title TEXT NOT NULL, author TEXT NOT NULL,
                        node TEXT NOT NULL, clicks INTEGER NOT NULL,
                        reply_count INTEGER NOT NULL, favorite_count INTEGER NOT NULL,
                        thank_count INTEGER NOT NULL, votes INTEGER NOT NULL
                    );
                    CREATE TABLE comment (id INTEGER PRIMARY KEY, topic_id INTEGER NOT NULL);
                    CREATE TABLE member (uid INTEGER, username TEXT);
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
                    INSERT INTO topic_fetch_state VALUES (10, 200, 100);
                    """
                )
            plan = {
                "through": "2026-08-20",
                "start_id": 10,
                "end_id": 10,
                "cutoff_timestamp": cutoff_timestamp(date(2026, 8, 20)),
                "baseline": {"topics": 0, "comments": 0, "members": 0},
                "created_at": 90,
                "crawl_purpose": "incremental-through-2026-08-20",
                "unit": None,
            }

            report = crawl_report(database, plan)

            self.assertEqual(report["fetch"]["retry_ids"], [10])

    def test_ids_to_ranges_is_compact(self):
        self.assertEqual(ids_to_ranges([1, 2, 3, 6, 8, 9]), "1-3,6,8-9")


if __name__ == "__main__":
    unittest.main()
