import sqlite3
import unittest

from analysis.build_analytics import (
    canonical_tag,
    build_member_rank_rows,
    comment_age_bucket,
    comment_text,
    first_reply_bucket,
    matches_group,
    normalize_tags,
    tag_detail_bucket,
)


class AnalysisBuildTest(unittest.TestCase):
    def test_canonical_tag_is_case_insensitive(self):
        synonyms = {"chatgpt": "AI", "人工智能": "AI"}

        self.assertEqual(canonical_tag(" ChatGPT ", synonyms), "AI")
        self.assertEqual(canonical_tag("人工智能", synonyms), "AI")
        self.assertEqual(canonical_tag("SQLite", synonyms), "SQLite")

    def test_group_matches_node_tag_or_title(self):
        group = {"nodes": ["jobs"], "keywords": ["AI", "求职"]}

        self.assertTrue(matches_group("普通帖子", "jobs", set(), group))
        self.assertTrue(matches_group("模型更新", "qna", {"AI"}, group))
        self.assertTrue(matches_group("最近求职经历", "qna", set(), group))
        self.assertFalse(matches_group("数据库优化", "programmer", {"SQLite"}, group))

    def test_normalize_tags_merges_synonyms_and_removes_noise(self):
        synonyms = {"chatgpt": "AI"}
        stopwords = {"大佬", "请问"}

        self.assertEqual(
            normalize_tags([" ChatGPT ", "AI", "大佬", "请问"], synonyms, stopwords),
            {"AI"},
        )

    def test_lifecycle_buckets_have_stable_boundaries(self):
        self.assertEqual(first_reply_bucket(599), "10m")
        self.assertEqual(first_reply_bucket(600), "1h")
        self.assertEqual(first_reply_bucket(86400), "3d")
        self.assertEqual(first_reply_bucket(None), "none")
        self.assertEqual(comment_age_bucket(604799), "7d")
        self.assertIsNone(comment_age_bucket(604800))

    def test_comment_text_extracts_visible_content(self):
        content = '<div class="reply_content">第一行<br>第二行 &amp; <a href="/go/python">Python</a></div>'

        self.assertEqual(comment_text(content), "第一行\n第二行 & Python")
        self.assertEqual(comment_text(None), "")

    def test_member_rank_rows_are_ranked_by_month_and_year(self):
        source = sqlite3.connect(":memory:")
        source.executescript(
            """
            CREATE TABLE topic (author TEXT, create_at INTEGER, clicks INTEGER, thank_count INTEGER);
            CREATE TABLE comment (commenter TEXT, create_at INTEGER, thank_count INTEGER);
            INSERT INTO topic VALUES
                ('alice', 1704067200, 10, 2),
                ('alice', 1704153600, 10, 1),
                ('bob', 1704240000, 10, 8),
                ('bob', 1706745600, 10, 1);
            INSERT INTO comment VALUES
                ('alice', 1704067200, 3),
                ('alice', 1704153600, 0),
                ('bob', 1704240000, 2),
                ('usdc', 1704240000, 999);
            """
        )

        rows = build_member_rank_rows(source, 2)

        self.assertIn(["month", "2024-01", "topics", 1, "alice", 2], rows)
        self.assertIn(["month", "2024-01", "comments", 1, "alice", 2], rows)
        self.assertIn(["month", "2024-01", "thanks", 1, "bob", 10], rows)
        self.assertIn(["year", "2024", "topics", 1, "alice", 2], rows)
        self.assertFalse(any(row[2] == "thanks" and row[4] == "usdc" for row in rows))

    def test_tag_detail_bucket_is_stable_and_bounded(self):
        self.assertEqual(tag_detail_bucket("AI"), tag_detail_bucket("AI"))
        self.assertIn(tag_detail_bucket("AI"), "0123456789abcdef")
        self.assertNotEqual(tag_detail_bucket("AI"), tag_detail_bucket("Apple"))


if __name__ == "__main__":
    unittest.main()
