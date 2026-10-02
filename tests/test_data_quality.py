import sqlite3
import unittest

from v2ex_scrapy.data_quality import (
    CommentGap,
    crawl_tracking_summary,
    filter_severe_comment_gaps,
    quality_metrics,
    quality_regressions,
    source_quality_summary,
    quality_anomalies,
    anomaly_regressions,
    supplement_quality_summary,
)


class DataQualityTest(unittest.TestCase):
    def test_source_summary_reports_parser_quality_fields(self):
        with sqlite3.connect(":memory:") as conn:
            conn.executescript(
                """
                CREATE TABLE topic (
                    id INTEGER PRIMARY KEY, author TEXT, title TEXT, node TEXT,
                    tag TEXT, create_at INTEGER, thank_count INTEGER,
                    favorite_count INTEGER, reply_count INTEGER
                );
                CREATE TABLE comment (
                    id INTEGER PRIMARY KEY, topic_id INTEGER, commenter TEXT,
                    content TEXT, no INTEGER, create_at INTEGER,
                    thank_count INTEGER
                );
                CREATE TABLE member (
                    uid INTEGER, username TEXT, create_at INTEGER
                );
                INSERT INTO topic VALUES (1, '', 'title', 'node', '[]', 1, 0, 0, 1);
                INSERT INTO comment VALUES (1, 1, '-1', '', -1, 1, 0);
                INSERT INTO member VALUES (1, 'alice', 1);
                """
            )

            summary = source_quality_summary(conn, comment_gaps=[])
            anomalies = quality_anomalies(conn, summary, [])

        self.assertEqual(summary["topics"]["empty_author"], 1)
        self.assertEqual(summary["comments"]["invalid_commenter"], 1)
        self.assertEqual(summary["comments"]["invalid_number"], 1)
        self.assertEqual(anomalies["topics.empty_author"], {"1": 1})
        self.assertEqual(anomalies["comments.empty_content"], {"1": 1})
        self.assertEqual(anomalies["comments.invalid_time"], {})

    def test_identity_gate_detects_replaced_and_worsening_anomalies(self):
        baseline = {"topics.empty_title": {"1": 1}, "severe_comment_gaps": {"10": 120}}
        current = {"topics.empty_title": {"2": 1}, "severe_comment_gaps": {"10": 121}}
        regressions = anomaly_regressions(current, baseline)
        self.assertEqual([item["id"] for item in regressions], [2, 10])
        self.assertEqual(anomaly_regressions({"severe_comment_gaps": {"10": 100}}, baseline), [])

    def test_supplement_audit_does_not_invent_dates(self):
        with sqlite3.connect(":memory:") as conn:
            self.assertFalse(supplement_quality_summary(conn)["available"])
            conn.executescript("""
                CREATE TABLE topic (id INTEGER PRIMARY KEY, create_at INTEGER);
                CREATE TABLE topic_supplement (topic_id INTEGER, create_at INTEGER);
                INSERT INTO topic VALUES (1, 100);
                INSERT INTO topic_supplement VALUES (1, 0), (1, 50), (1, 120);
            """)
            report = supplement_quality_summary(conn)
            self.assertEqual(report["total"], 3)
            self.assertEqual(report["unknown_time"], 1)
            self.assertEqual(report["before_topic_time"], 1)

    def test_reports_only_metrics_above_the_baseline(self):
        summary = {
            "topics": {
                "empty_title": 2,
                "empty_author": 0,
                "empty_node": 1,
                "unknown_thanks": 0,
                "unknown_favorites": 0,
            },
            "comments": {
                "empty_content": 0,
                "invalid_commenter": 0,
                "invalid_number": 0,
                "invalid_time": 0,
                "unknown_thanks": 0,
            },
        }
        metrics = quality_metrics(summary, [CommentGap(10, 220, 100)])
        regressions = quality_regressions(
            metrics,
            {
                "topics.empty_title": 1,
                "topics.empty_node": 1,
                "severe_comment_gaps.comments": 100,
            },
        )

        self.assertEqual(
            [item["metric"] for item in regressions],
            ["topics.empty_title", "severe_comment_gaps.comments"],
        )

    def test_crawl_tracking_is_optional_for_older_databases(self):
        with sqlite3.connect(":memory:") as conn:
            self.assertEqual(crawl_tracking_summary(conn)["tracked_topics"], 0)

    def test_severe_gap_filter_includes_first_page_shortfalls(self):
        gaps = [
            CommentGap(1, 150, 100),
            CommentGap(2, 220, 110),
            CommentGap(3, 10, 9),
        ]

        self.assertEqual(
            [item.topic_id for item in filter_severe_comment_gaps(gaps)],
            [1, 2],
        )


if __name__ == "__main__":
    unittest.main()
