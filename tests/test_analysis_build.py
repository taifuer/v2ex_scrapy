import sqlite3
import unittest

from analysis.build_analytics import (
    canonical_tag,
    build_member_profile_candidates,
    build_member_rank_rows,
    build_monthly_summaries,
    comment_age_bucket,
    comment_text,
    first_reply_bucket,
    matches_group,
    member_profile_bucket,
    normalize_tags,
    percent_change,
    push_top,
    tag_detail_bucket,
)


class AnalysisBuildTest(unittest.TestCase):
    def test_monthly_summaries_embed_rankings_and_activity_baselines(self):
        summaries = build_monthly_summaries(
            {"rows": [["2024-01", "AI", 8, 0, 0], ["2024-01", "Python", 5, 0, 0]]},
            {"rows": [["2024-01", "qna", 9, 0, 0], ["2024-01", "python", 4, 0, 0]]},
            {
                "rows": [["2023-01", 0, 6, 7], ["2023-12", 0, 8, 9], ["2024-01", 0, 10, 12]],
                "rank_rows": [["month", "2024-01", "topics", 1, "alice", 3]],
            },
        )

        self.assertEqual(summaries["2024-01"]["tags"][0], {"name": "AI", "value": 8})
        self.assertEqual(summaries["2024-01"]["nodes"][0], {"name": "qna", "value": 9})
        self.assertEqual(summaries["2024-01"]["members"], [{"name": "alice", "value": 3}])
        self.assertEqual(summaries["2024-01"]["activity"]["authors"], [10, 8, 6])

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

    def test_percent_change_handles_growth_decline_and_empty_baseline(self):
        self.assertEqual(percent_change(80, 100), -20)
        self.assertEqual(percent_change(125, 100), 25)
        self.assertEqual(percent_change(10, 0), 0)

    def test_comment_text_extracts_visible_content(self):
        content = '<div class="reply_content">第一行<br>第二行 &amp; <a href="/go/python">Python</a></div>'

        self.assertEqual(comment_text(content), "第一行\n第二行 & Python")
        self.assertEqual(comment_text(None), "")

    def test_push_top_keeps_the_highest_ranked_items(self):
        heap = []
        for value, item_id in ((3, 1), (9, 2), (5, 3), (9, 4)):
            push_top(heap, (value, item_id, {}), limit=3)

        self.assertEqual([(item[0], item[1]) for item in sorted(heap, reverse=True)], [(9, 4), (9, 2), (5, 3)])

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

    def test_member_profile_candidates_include_leaders_and_recurring_members(self):
        community = {
            "top_topic_authors": [{"username": "leader"}],
            "top_commenters": [{"username": "leader"}, {"username": "commenter"}],
            "top_thanked": [{"username": "usdc"}],
            "rank_rows": [
                ["year", "2022", "topics", 1, "recurring", 10],
                ["year", "2023", "comments", 2, "recurring", 20],
                ["year", "2024", "thanks", 3, "recurring", 30],
                ["year", "2024", "topics", 4, "occasional", 40],
                ["month", "2024-01", "topics", 1, "monthly", 50],
                ["month", "2024-02", "topics", 1, "outside", 60],
            ],
        }

        self.assertEqual(
            build_member_profile_candidates(
                community,
                limit=10,
                min_annual_appearances=3,
                default_periods={"2024-01"},
            ),
            ["leader", "commenter", "monthly", "recurring"],
        )
        self.assertIn(member_profile_bucket("leader"), "0123456789abcdef")


if __name__ == "__main__":
    unittest.main()
