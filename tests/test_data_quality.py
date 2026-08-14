import sqlite3
import unittest

from v2ex_scrapy.data_quality import (
    CommentGap,
    crawl_tracking_summary,
    filter_severe_comment_gaps,
    quality_metrics,
    quality_regressions,
    source_quality_summary,
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

        self.assertEqual(summary["topics"]["empty_author"], 1)
        self.assertEqual(summary["comments"]["invalid_commenter"], 1)
        self.assertEqual(summary["comments"]["invalid_number"], 1)

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
