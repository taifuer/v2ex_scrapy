import sqlite3
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import analysis.build_analytics as analytics_builder
from analysis.content_hotspots import (
    TitleTokenizer,
    _burst_score,
    _related_term_ranking,
    sync_title_token_cache,
)
from analysis.content_hotspot_audit import review_reasons

from analysis.build_analytics import (
    build_monthly_comment_heaps,
    canonical_tag,
    build_member_comment_heaps,
    build_member_profile_candidates,
    build_member_rank_rows,
    build_monthly_summaries,
    comment_age_bucket,
    comment_text,
    first_reply_bucket,
    load_content_period_summaries,
    matches_group,
    member_comment_bucket,
    member_profile_bucket,
    normalize_tags,
    percent_change,
    push_top,
    select_topic_tags,
    source_analysis_state,
    source_complete_through,
    tag_detail_bucket,
)


class AnalysisBuildTest(unittest.TestCase):
    def test_monthly_comment_rankings_exclude_incomplete_periods(self):
        source = sqlite3.connect(":memory:")
        source.executescript(
            """
            CREATE TABLE topic (id INTEGER PRIMARY KEY, title TEXT, clicks INTEGER);
            CREATE TABLE comment (
                id INTEGER PRIMARY KEY, topic_id INTEGER, commenter TEXT,
                thank_count INTEGER, no INTEGER, content TEXT, create_at INTEGER
            );
            INSERT INTO topic VALUES (1, 'July topic', 10), (2, 'August topic', 20);
            INSERT INTO comment VALUES
                (1, 1, 'alice', 2, 1, 'July', 1785427200),
                (2, 2, 'bob', 3, 1, 'August', 1788105600);
            """
        )

        heaps = build_monthly_comment_heaps(source, "2026-07")

        self.assertEqual(set(heaps), {"2026-07"})
        source.close()

    def test_source_complete_through_requires_month_end_or_later_data(self):
        def timestamp(value: str) -> int:
            from datetime import datetime
            from analysis.build_analytics import LOCAL_TIMEZONE

            return int(datetime.fromisoformat(value).replace(tzinfo=LOCAL_TIMEZONE).timestamp())

        latest = timestamp("2026-07-05T12:00:00")
        self.assertEqual(
            source_complete_through(latest, latest, "2026-08"),
            "2026-06",
        )
        month_end = timestamp("2026-07-31T23:49:42")
        self.assertEqual(
            source_complete_through(month_end, month_end, "2026-08"),
            "2026-07",
        )
        august_comment = timestamp("2026-08-01T00:08:58")
        self.assertEqual(
            source_complete_through(month_end, august_comment, "2026-08"),
            "2026-07",
        )
        current_topic = timestamp("2026-08-01T08:34:57")
        self.assertEqual(
            source_complete_through(current_topic, current_topic, "2026-08"),
            "2026-07",
        )

    def test_source_state_ignores_http_logs_but_detects_comment_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "source.sqlite"
            source = sqlite3.connect(source_path)
            source.executescript(
                """
                CREATE TABLE topic (
                    id INTEGER PRIMARY KEY, author TEXT, title TEXT, node TEXT,
                    tag TEXT, create_at INTEGER, clicks INTEGER, reply_count INTEGER,
                    favorite_count INTEGER, thank_count INTEGER, votes INTEGER
                );
                CREATE TABLE comment (
                    id INTEGER PRIMARY KEY, topic_id INTEGER, create_at INTEGER,
                    thank_count INTEGER, content TEXT, commenter TEXT
                );
                CREATE TABLE member (uid INTEGER, create_at INTEGER, username TEXT);
                CREATE TABLE log (id INTEGER PRIMARY KEY, url TEXT, status_code INTEGER, create_at INTEGER);
                INSERT INTO topic VALUES
                    (1, 'alice', 'AI 工具', 'qna', '[]', 1704067200, 10, 1, 2, 3, 4);
                INSERT INTO member VALUES (1, 1704067200, 'alice');
                """
            )
            source.commit()
            source.close()

            with patch.object(analytics_builder, "SOURCE_DB", source_path):
                analytics_builder._source_state_cache = None
                initial = source_analysis_state()
                source = sqlite3.connect(source_path)
                source.execute("INSERT INTO log VALUES (1, '/t/1', 200, 1704153600)")
                source.commit()
                source.close()
                after_log = source_analysis_state()
                source = sqlite3.connect(source_path)
                source.execute(
                    "INSERT INTO comment VALUES (1, 1, 1704153600, 1, '@alice', 'bob')"
                )
                source.commit()
                source.close()
                after_comment = source_analysis_state()
                analytics_builder._source_state_cache = None

            self.assertEqual(initial, after_log)
            self.assertNotEqual(after_log["comment"], after_comment["comment"])

    def test_content_tokenizer_keeps_specific_terms_and_drops_question_noise(self):
        tokenizer = TitleTokenizer(Path(__file__).resolve().parent.parent / "analysis")

        tokens = tokenizer.tokenize("请问 Codex 和 Claude Code 工具项目重置后无法连接 MCP，有什么解决办法？")

        self.assertTrue({"Codex", "Claude Code", "MCP", "重置"} <= tokens)
        self.assertFalse({"请问", "无法", "解决", "办法", "工具", "项目"} & tokens)

    def test_content_tokenizer_keeps_emerging_terms_and_merges_variants(self):
        tokenizer = TitleTokenizer(Path(__file__).resolve().parent.parent / "analysis")

        tokens = tokenizer.tokenize("AI coding skill 和 Agent Skills 的实践")

        self.assertTrue({"AI", "编程", "Skill", "Agent"} <= tokens)
        self.assertFalse({"Coding", "Skills"} & tokens)

    def test_content_tokenizer_normalizes_mixed_script_terms(self):
        tokenizer = TitleTokenizer(Path(__file__).resolve().parent.parent / "analysis")

        tokens = tokenizer.tokenize("A股、ETF、Deep Seek、双十一、Mac mini、iPad mini、MiniMax、m1、M4、php 和 ss 最近怎么样")

        self.assertTrue({"A股", "ETF", "DeepSeek", "双十一", "Mac mini", "iPad mini", "MiniMax", "M1", "M4", "PHP", "SS"} <= tokens)
        self.assertNotIn("Mini", tokens)

    def test_content_tokenizer_does_not_match_ai_inside_air(self):
        tokenizer = TitleTokenizer(Path(__file__).resolve().parent.parent / "analysis")

        tokens = tokenizer.tokenize("MacBook Air 对比 OpenAI 与 AI 工具")

        self.assertTrue({"MacBook", "Air", "OpenAI", "AI"} <= tokens)
        self.assertEqual(tokens & {"AI"}, {"AI"})
        self.assertNotIn("AI", tokenizer.tokenize("MacBook Air 出售"))

    def test_content_burst_score_compares_period_share(self):
        self.assertGreater(_burst_score(40, 1000, 10, 1000), 1)
        self.assertLess(_burst_score(5, 1000, 20, 1000), 0)
        self.assertEqual(_burst_score(5, 1000, 0, 0), 0)

    def test_related_content_ranking_is_clickable_deterministic_and_excludes_self(self):
        ranking = _related_term_ranking(
            Counter({"AI": 99, "Python": 12, "ChatGPT": 12, "未入选": 30}),
            {"AI", "Python", "ChatGPT"},
            "AI",
        )

        self.assertEqual(ranking, [("ChatGPT", 12), ("Python", 12)])

    def test_content_audit_flags_concentration_without_removing_terms(self):
        detail = {
            "total": 100,
            "authors": [["alice", 20]],
            "nodes": [["all4all", 80]],
        }

        self.assertEqual(
            review_reasons(detail),
            ["头部作者占比不低于 15%", "头部节点占比不低于 75%"],
        )

    def test_title_token_cache_only_updates_new_or_changed_titles(self):
        analysis_dir = Path(__file__).resolve().parent.parent / "analysis"
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "source.sqlite"
            cache_path = Path(directory) / "tokens.sqlite"
            source = sqlite3.connect(source_path)
            source.executescript(
                """
                CREATE TABLE topic (
                    id INTEGER PRIMARY KEY,
                    title TEXT,
                    clicks INTEGER,
                    create_at INTEGER
                );
                INSERT INTO topic VALUES
                    (1, 'AI 工具更新', 10, 1704067200),
                    (2, 'Python 项目实践', 20, 1704153600);
                """
            )
            source.commit()
            source.close()

            first = sync_title_token_cache(source_path, analysis_dir, 0, cache_path)
            second = sync_title_token_cache(source_path, analysis_dir, 0, cache_path)
            source = sqlite3.connect(source_path)
            source.execute("UPDATE topic SET title = 'Claude 工具更新' WHERE id = 1")
            source.commit()
            source.close()
            third = sync_title_token_cache(source_path, analysis_dir, 0, cache_path)

            self.assertEqual(first, {"updated": 2, "total": 2})
            self.assertEqual(second, {"updated": 0, "total": 2})
            self.assertEqual(third, {"updated": 1, "total": 2})

    def test_focused_topic_tags_replace_only_the_lowest_ranked_items(self):
        totals = {f"tag-{index}": 2000 - index for index in range(600)}
        totals.update({"投资": 10, "理财": 9, "股票": 8, "基金": 7})
        selected = select_topic_tags(totals, limit=500)
        names = {tag for tag, _ in selected}
        self.assertEqual(len(selected), 500)
        self.assertTrue({"投资", "理财", "股票", "基金"} <= names)
        self.assertIn("tag-495", names)
        self.assertNotIn("tag-499", names)

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
        self.assertNotIn("members", summaries["2024-01"])
        self.assertEqual(summaries["2024-01"]["content"], [])
        self.assertEqual(summaries["2024-01"]["activity"]["authors"], [10, 8, 6])

    def test_content_period_summaries_follow_monthly_and_annual_ranks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            public_dir = Path(temp_dir)
            (public_dir / "dynamic-content-hotspots-index.json").write_text(
                '{"year_shards":{"2024":"dynamic-content-hotspots-2024.json"}}',
                encoding="utf-8",
            )
            (public_dir / "dynamic-content-hotspots-2024.json").write_text(
                '{"rows":[["2024-01","AI",8,6,3,1,0,1,0,2,0,false],'
                '["2024-01","Python",12,8,4,1,0,2,0,1,0,false],'
                '["2024-01","低频词",2,1,1,1,0,0,0,0,0,false]],'
                '"annual_rows":[["2024","AI",80,50,8,1,0,2,0,1,0,false]]}',
                encoding="utf-8",
            )

            monthly, annual = load_content_period_summaries(public_dir)

        self.assertEqual(monthly["2024-01"], [
            {"name": "Python", "value": 12},
            {"name": "AI", "value": 8},
        ])
        self.assertEqual(annual["2024"], [{"name": "AI", "value": 80}])

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

    def test_member_comments_keep_only_top_thanked_accessible_items(self):
        source = sqlite3.connect(":memory:")
        source.executescript(
            """
            CREATE TABLE topic (id INTEGER, title TEXT, clicks INTEGER);
            CREATE TABLE comment (
                id INTEGER, topic_id INTEGER, commenter TEXT, thank_count INTEGER,
                no INTEGER, content TEXT, create_at INTEGER
            );
            INSERT INTO topic VALUES (1, '可访问主题', 10), (2, '不可访问主题', -1);
            INSERT INTO comment VALUES
                (1, 1, 'alice', 2, 1, '<div>两次感谢</div>', 1704067200),
                (2, 1, 'alice', 5, 2, '<div>五次感谢</div>', 1704153600),
                (3, 1, 'alice', 0, 3, '<div>没有感谢</div>', 1704240000),
                (4, 2, 'alice', 9, 1, '<div>不可访问</div>', 1704326400),
                (5, 1, 'usdc', 999, 4, '<div>异常值</div>', 1704412800);
            """
        )

        heaps = build_member_comment_heaps(source, ["alice", "usdc"], limit=2)
        comments = [item[2] for item in sorted(heaps["alice"], reverse=True)]

        self.assertEqual([comment["thank_count"] for comment in comments], [5, 2])
        self.assertEqual(comments[0]["content"], "五次感谢")
        self.assertNotIn("usdc", heaps)

    def test_tag_detail_bucket_is_stable_and_bounded(self):
        self.assertEqual(tag_detail_bucket("AI"), tag_detail_bucket("AI"))
        self.assertRegex(tag_detail_bucket("AI"), r"^[0-3][0-9a-f]$")
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
        self.assertRegex(member_profile_bucket("leader"), r"^[0-3][0-9a-f]$")
        self.assertRegex(member_comment_bucket("leader"), r"^[0-3][0-9a-f]$")


if __name__ == "__main__":
    unittest.main()
