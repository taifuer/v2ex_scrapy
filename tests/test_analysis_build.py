import json
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
    _confirmed_detail_terms,
    _qualifying_detail_terms,
    _related_term_ranking,
    content_family_config,
    content_group_matches,
    expand_content_families,
    monthly_content_representative_limit,
    sync_title_token_cache,
)
from analysis.content_hotspot_audit import review_reasons

from analysis.build_analytics import (
    build_scale_distribution,
    build_monthly_comment_heaps,
    canonical_tag,
    build_member_comment_heaps,
    build_member_profile_candidates,
    build_member_rank_rows,
    build_monthly_summaries,
    build_search_suggestions,
    collect_topic_groups,
    comment_age_bucket,
    comment_text,
    content_display_terms,
    first_reply_bucket,
    group_tag_monthly_representative_posts,
    group_tag_representative_posts,
    load_content_period_summaries,
    matches_topic_group,
    matching_group_topics,
    member_comment_bucket,
    member_profile_bucket,
    node_monthly_representative_limit,
    node_period_post_bucket,
    normalize_tags,
    percent_change,
    period_end_timestamp,
    push_top,
    push_tag_monthly_representative_candidates,
    push_tag_representative_candidates,
    select_topic_tags,
    source_analysis_state,
    source_complete_through,
    tag_detail_bucket,
    tag_monthly_representative_limit,
    threshold_rows,
)


class AnalysisBuildTest(unittest.TestCase):
    def test_scale_distribution_uses_complete_periods_and_omits_votes(self):
        source = sqlite3.connect(":memory:")
        source.executescript(
            """
            CREATE TABLE topic (
                id INTEGER PRIMARY KEY, author TEXT, create_at INTEGER, clicks INTEGER,
                favorite_count INTEGER, thank_count INTEGER
            );
            CREATE TABLE comment (
                id INTEGER PRIMARY KEY, commenter TEXT, create_at INTEGER,
                thank_count INTEGER
            );
            """
        )
        january = period_end_timestamp("2024-12") + 3600
        august = period_end_timestamp("2025-07") + 3600
        source.executemany(
            "INSERT INTO topic VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1, "alice", january, 10_000, 10, 20),
                (2, "usdc", january, 500_000, -1, -1),
                (3, "future", august, 9_000_000, 9_000, 9_000),
            ],
        )
        source.executemany(
            "INSERT INTO comment VALUES (?, ?, ?, ?)",
            [
                (1, "alice", january, 10),
                (2, "usdc", january, 20),
                (3, "future", august, 999),
            ],
        )

        result = build_scale_distribution(
            source,
            {
                ("2025-01", "AI"): [500, 0, 0],
                ("2025-08", "future"): [50_000, 0, 0],
            },
            {
                ("2025-01", "python"): [1_000, 0, 0],
                ("2025-08", "future"): [200_000, 0, 0],
            },
            "2025-07",
        )

        self.assertEqual(result["metadata"]["counts"]["posts"], 2)
        self.assertEqual(result["metadata"]["unknown_post_interactions"], 1)
        self.assertEqual(result["post_metrics"]["favorites"]["observed_count"], 1)
        self.assertEqual(result["post_metrics"]["favorites"]["rows"][-1]["count"], 1)
        self.assertEqual(result["post_metrics"]["favorites"]["rows"][-1]["threshold"], 5)
        self.assertEqual(result["post_metrics"]["clicks"]["rows"][0]["count"], 1)
        self.assertEqual(result["post_metrics"]["clicks"]["rows"][-1]["threshold"], 5_000)
        self.assertEqual(result["comment_thanks"]["rows"][0]["threshold"], 200)
        self.assertEqual(result["comment_thanks"]["rows"][-1]["threshold"], 5)
        self.assertEqual(result["comment_thanks"]["rows"][-1]["count"], 2)
        self.assertEqual(result["entity_metrics"]["topics"]["rows"][-1]["count"], 1)
        self.assertEqual(result["entity_metrics"]["nodes"]["rows"][-1]["count"], 1)
        self.assertEqual(result["member_metrics"]["topics"]["rows"][-1]["threshold"], 5)
        self.assertEqual(result["member_metrics"]["topics"]["rows"][-1]["count"], 0)
        self.assertEqual(result["member_metrics"]["comments"]["rows"][-1]["threshold"], 5)
        self.assertEqual(result["member_metrics"]["thanks"]["rows"][-1]["threshold"], 5)
        self.assertEqual(result["member_metrics"]["thanks"]["rows"][-1]["count"], 1)
        self.assertNotIn("vote", json.dumps(result))
        source.close()

    def test_threshold_rows_are_cumulative(self):
        self.assertEqual(
            threshold_rows([0, 10, 20, 20], (20, 10, 1)),
            [
                {"threshold": 20, "count": 2},
                {"threshold": 10, "count": 3},
                {"threshold": 1, "count": 3},
            ],
        )

    def test_active_topic_months_keep_more_representative_posts(self):
        self.assertEqual(tag_monthly_representative_limit(19), 3)
        self.assertEqual(tag_monthly_representative_limit(20), 5)
        self.assertEqual(tag_monthly_representative_limit(99), 5)
        self.assertEqual(tag_monthly_representative_limit(100), 10)
        self.assertEqual(monthly_content_representative_limit(19), 3)
        self.assertEqual(monthly_content_representative_limit(20), 5)
        self.assertEqual(monthly_content_representative_limit(99), 5)
        self.assertEqual(monthly_content_representative_limit(100), 10)
        self.assertEqual(node_monthly_representative_limit(19), 3)
        self.assertEqual(node_monthly_representative_limit(20), 5)
        self.assertEqual(node_monthly_representative_limit(99), 5)
        self.assertEqual(node_monthly_representative_limit(100), 10)

    def test_search_suggestions_use_recent_window_and_deduplicate_types(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            public_dir = Path(temp_dir)
            fixtures = {
                "dynamic-overview.json": {
                    "metadata": {"default_end_period": "2025-03"},
                },
                "dynamic-topics.json": {
                    "row_shards": {
                        "2024": "dynamic-topic-rows-2024.json",
                        "2025": "dynamic-topic-rows-2025.json",
                    },
                },
                "dynamic-topic-rows-2024.json": {
                    "rows": [
                        ["2024-03", "过期", 999, 0, 0],
                        ["2024-04", "AI", 20, 0, 0],
                        ["2024-05", "Python", 15, 0, 0],
                        ["2024-06", "Apple", 8, 0, 0],
                        ["2024-07", "Linux", 6, 0, 0],
                    ],
                },
                "dynamic-topic-rows-2025.json": {
                    "rows": [
                        ["2025-03", "AI", 10, 0, 0],
                        ["2025-03", "Python", 4, 0, 0],
                        ["2025-03", "Apple", 5, 0, 0],
                        ["2025-03", "Rust", 1, 0, 0],
                    ],
                },
                "dynamic-content-hotspots-index.json": {
                    "year_shards": {
                        "2024": "dynamic-content-hotspots-2024.json",
                        "2025": "dynamic-content-hotspots-2025.json",
                    },
                    "terms": {
                        "AI": {"ranked": True},
                        "Claude": {"ranked": True},
                        "Mac": {"ranked": True},
                        "设计": {"ranked": True},
                        "Docker": {"ranked": True},
                        "GitHub": {"ranked": True},
                        "忽略": {"ranked": False},
                    },
                },
                "dynamic-content-hotspots-2024.json": {
                    "rows": [
                        ["2024-04", "AI", 50],
                        ["2024-04", "Claude", 30],
                        ["2024-04", "Mac", 20],
                        ["2024-04", "设计", 10],
                        ["2024-05", "Docker", 9],
                        ["2024-06", "GitHub", 7],
                    ],
                },
                "dynamic-content-hotspots-2025.json": {
                    "rows": [
                        ["2025-03", "Claude", 5],
                        ["2025-03", "Mac", 4],
                        ["2025-03", "设计", 3],
                        ["2025-03", "忽略", 999],
                    ],
                },
            }
            for name, payload in fixtures.items():
                (public_dir / name).write_text(json.dumps(payload), encoding="utf-8")

            result = build_search_suggestions(public_dir)

            self.assertEqual(result["metadata"]["from_period"], "2024-04")
            self.assertEqual(result["metadata"]["limit_per_type"], 5)
            self.assertEqual([item["value"] for item in result["topics"]], ["AI", "Python", "Apple", "Linux", "Rust"])
            self.assertEqual([item["value"] for item in result["content"]], ["Claude", "Mac", "设计", "Docker", "GitHub"])
            self.assertTrue((public_dir / "dynamic-search-suggestions.json").exists())

    def test_topic_representative_posts_are_ranked_within_each_topic_year(self):
        heaps = {}
        candidates = [
            ({"id": 1, "period": "2024-06", "score": 5.0, "create_at": 1}, 5.0),
            ({"id": 2, "period": "2025-01", "score": 2.0, "create_at": 2}, 2.0),
            ({"id": 3, "period": "2025-02", "score": 8.0, "create_at": 3}, 8.0),
            ({"id": 4, "period": "2025-03", "score": 4.0, "create_at": 4}, 4.0),
        ]
        for post, score in candidates:
            push_tag_representative_candidates(
                heaps,
                {"AI", "Python"} if post["id"] == 3 else {"AI"},
                post,
                score,
                limit=2,
            )

        grouped = group_tag_representative_posts(heaps)

        self.assertEqual([post["id"] for post in grouped["AI"]], [3, 1, 4])
        self.assertEqual([post["id"] for post in grouped["Python"]], [3])

    def test_topic_monthly_representative_posts_keep_each_month_separate(self):
        heaps = {}
        candidates = [
            ({"id": 1, "period": "2025-01", "score": 3.0, "create_at": 1}, 3.0),
            ({"id": 2, "period": "2025-01", "score": 7.0, "create_at": 2}, 7.0),
            ({"id": 3, "period": "2025-01", "score": 5.0, "create_at": 3}, 5.0),
            ({"id": 4, "period": "2025-02", "score": 2.0, "create_at": 4}, 2.0),
        ]
        for post, score in candidates:
            push_tag_monthly_representative_candidates(
                heaps,
                {"AI", "Python"} if post["id"] == 4 else {"AI"},
                post,
                score,
                limit=2,
            )

        grouped = group_tag_monthly_representative_posts(heaps)

        self.assertEqual(
            [post["id"] for post in grouped["AI"]["2025-01"]],
            [2, 3],
        )
        self.assertEqual(
            [post["id"] for post in grouped["AI"]["2025-02"]],
            [4],
        )
        self.assertEqual(
            [post["id"] for post in grouped["Python"]["2025-02"]],
            [4],
        )

    def test_analytics_schema_persists_topic_group_topics(self):
        connection = sqlite3.connect(":memory:")

        analytics_builder.create_schema(connection)

        topic_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(topic_group_topic_period)")
        }
        self.assertEqual(topic_columns, {"period", "group_name", "topic", "topic_count"})
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        self.assertNotIn("topic_group_node_period", tables)
        self.assertNotIn("representative_post", tables)
        connection.close()

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
            self.assertRegex(initial["analysis"]["config_hash"], r"^[0-9a-f]{32}$")

    def test_unchanged_source_still_checks_analysis_rule_version(self):
        with tempfile.TemporaryDirectory() as directory:
            public_dir = Path(directory)
            manifest_path = public_dir / "dynamic-manifest.json"
            manifest = {
                "schema_version": analytics_builder.ANALYTICS_SCHEMA_VERSION,
                "full_build_source": {"size": 10, "mtime_ns": 20},
                "full_build_state": {
                    "version": analytics_builder.SOURCE_STATE_VERSION - 1,
                    "analysis": {"config_hash": analytics_builder.analysis_config_fingerprint()},
                },
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with (
                patch.object(analytics_builder, "PUBLIC_DIR", public_dir),
                patch.object(
                    analytics_builder,
                    "source_fingerprint",
                    return_value={"size": 10, "mtime_ns": 20},
                ),
            ):
                self.assertFalse(analytics_builder.source_unchanged_since_full_build())
                manifest["full_build_state"] = {
                    "version": analytics_builder.SOURCE_STATE_VERSION,
                    "analysis": {"config_hash": "stale-config"},
                }
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                self.assertFalse(analytics_builder.source_unchanged_since_full_build())

    def test_content_tokenizer_keeps_specific_terms_and_drops_question_noise(self):
        tokenizer = TitleTokenizer(Path(__file__).resolve().parent.parent / "analysis")

        tokens = tokenizer.tokenize("请问 Codex 和 Claude Code 工具项目重置后无法连接 MCP，有什么解决办法？")

        self.assertTrue({"Codex", "Claude Code", "MCP", "重置"} <= tokens)
        self.assertFalse({"请问", "无法", "解决", "办法", "工具", "项目"} & tokens)

    def test_content_tokenizer_keeps_subject_terms_and_drops_quantity_noise(self):
        tokenizer = TitleTokenizer(Path(__file__).resolve().parent.parent / "analysis")

        tokens = tokenizer.tokenize("家庭购买手机用于本地工作，免费用 AI 写代码，另送邀请码五枚")

        self.assertTrue(
            {"AI", "代码", "手机", "家庭", "购买", "工作", "本地", "免费", "邀请码"}
            <= tokens
        )
        self.assertNotIn("五枚", tokens)

    def test_content_group_terms_are_not_hidden_by_stopwords(self):
        analysis_dir = Path(__file__).resolve().parent.parent / "analysis"
        stopwords = {
            line.strip()
            for line in (analysis_dir / "content_stopwords.txt").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        groups = json.loads((analysis_dir / "content_groups.json").read_text(encoding="utf-8"))["groups"]
        conflicts = {
            term
            for group in groups
            for term in group.get("terms", [])
            if term in stopwords
        }

        self.assertEqual(conflicts, set())

    def test_content_tokenizer_keeps_emerging_terms_and_merges_variants(self):
        tokenizer = TitleTokenizer(Path(__file__).resolve().parent.parent / "analysis")

        tokens = tokenizer.tokenize(
            "AI coding skill、AI Agent、智能体、GitHub Copilot 和提示词的实践"
        )

        self.assertTrue(
            {"AI", "编程", "Skill", "AI Agent", "智能体", "Copilot", "提示词"}
            <= tokens
        )
        self.assertFalse({"Coding", "Skills", "Agent", "GitHub Copilot", "Prompt"} & tokens)

    def test_content_tokenizer_normalizes_mixed_script_terms(self):
        tokenizer = TitleTokenizer(Path(__file__).resolve().parent.parent / "analysis")

        tokens = tokenizer.tokenize("A股、ETF、Deep Seek、双十一、Mac mini、iPad mini、iCloud、MiniMax、m1、M4、php 和 ss 最近怎么样")

        self.assertTrue({"A股", "ETF", "DeepSeek", "双十一", "Mac mini", "iPad mini", "iCloud", "MiniMax", "M1", "M4", "PHP", "SS"} <= tokens)
        self.assertNotIn("Mini", tokens)

    def test_content_tokenizer_normalizes_confirmed_ai_entity_variants(self):
        tokenizer = TitleTokenizer(Path(__file__).resolve().parent.parent / "analysis")

        tokens = tokenizer.tokenize(
            "GLM-5.2、glm4.7、Claude Opus、Sonnet5、Fable5、OpenCode、opencode、"
            "Doubao、StepFun 和 GPT-5.6 Sol"
        )

        self.assertTrue(
            {"GLM", "Opus", "Sonnet", "Fable", "OpenCode", "豆包", "阶跃星辰", "GPT-5.6 Sol"}
            <= tokens
        )
        self.assertFalse({"Glm", "GLM-5.2", "Opencode", "Doubao", "Sol", "GPT"} & tokens)

    def test_content_tokenizer_preserves_gpt_versions_and_expands_the_family(self):
        tokenizer = TitleTokenizer(Path(__file__).resolve().parent.parent / "analysis")

        tokens = tokenizer.tokenize("GPT-4、GPT4、GPT-5 与 GPT-5.6 Sol 模型对比")
        _, member_families = content_family_config(
            Path(__file__).resolve().parent.parent / "analysis"
        )
        expanded = expand_content_families(tokens, member_families)

        self.assertTrue({"GPT-4", "GPT-5", "GPT-5.6 Sol"} <= tokens)
        self.assertNotIn("GPT", tokens)
        self.assertNotIn("GPT4", tokens)
        self.assertTrue({"GPT", "GPT-4", "GPT-5", "GPT-5.6 Sol"} <= expanded)

    def test_content_tokenizer_expands_agent_variants_to_agent_family(self):
        tokenizer = TitleTokenizer(Path(__file__).resolve().parent.parent / "analysis")

        tokens = tokenizer.tokenize("AI Agent 与智能体的工程实践")
        _, member_families = content_family_config(
            Path(__file__).resolve().parent.parent / "analysis"
        )
        expanded = expand_content_families(tokens, member_families)

        self.assertTrue({"AI Agent", "智能体"} <= tokens)
        self.assertNotIn("Agent", tokens)
        self.assertTrue({"Agent", "AI Agent", "智能体"} <= expanded)

    def test_content_tokenizer_filters_ambiguous_non_ai_contexts(self):
        tokenizer = TitleTokenizer(Path(__file__).resolve().parent.parent / "analysis")

        self.assertNotIn("GPT", tokenizer.tokenize("Windows 的 GPT 磁盘分区无法启动"))
        self.assertNotIn("GPT", tokenizer.tokenize("关于 GPT 下使用了 fdisk"))
        self.assertNotIn("Agent", tokenizer.tokenize("Safari 如何修改 User Agent"))
        self.assertNotIn("Agent", tokenizer.tokenize("Twitter Agent 登录后退出"))
        self.assertNotIn("Prompt", tokenizer.tokenize("oh-my-zsh 的 prompt 显示完整路径"))
        self.assertNotIn("Prompt", tokenizer.tokenize("Prompt 2 降价了"))
        self.assertNotIn("Prompt", tokenizer.tokenize("Prompt 出 2 了，扁平化很帅"))
        self.assertNotIn("Prompt", tokenizer.tokenize("来分享一下你的 prompt"))
        self.assertNotIn("智能体", tokenizer.tokenize("智能体脂秤是否准确"))
        self.assertIn("GPT", tokenizer.tokenize("GPT 大模型最近有什么进展"))
        self.assertIn("Prompt", tokenizer.tokenize("AI Prompt 工程实践"))

    def test_content_synonym_variants_have_one_canonical_owner(self):
        config_path = (
            Path(__file__).resolve().parent.parent / "analysis" / "content_synonyms.json"
        )
        config = json.loads(config_path.read_text(encoding="utf-8"))
        owners = {}

        for canonical, variants in config.items():
            for value in [canonical, *variants]:
                folded = str(value).casefold()
                previous = owners.setdefault(folded, canonical)
                self.assertEqual(
                    previous,
                    canonical,
                    f"content synonym {value!r} belongs to both {previous!r} and {canonical!r}",
                )

    def test_tag_synonym_variants_have_one_canonical_owner(self):
        config_path = (
            Path(__file__).resolve().parent.parent / "analysis" / "tag_synonyms.json"
        )
        config = json.loads(config_path.read_text(encoding="utf-8"))
        owners = {}

        for canonical, variants in config.items():
            for value in [canonical, *variants]:
                folded = str(value).casefold()
                previous = owners.setdefault(folded, canonical)
                self.assertEqual(
                    previous,
                    canonical,
                    f"tag synonym {value!r} belongs to both {previous!r} and {canonical!r}",
                )

    def test_content_display_terms_hide_family_members_but_keep_them_searchable(self):
        index = {
            "metadata": {"ranking_excluded_terms": ["GPT-4", "GPT-5"]},
            "terms": {"GPT": {}, "GPT-4": {}, "GPT-5": {}, "Claude": {}},
        }

        self.assertEqual(content_display_terms(index), {"GPT", "Claude"})

    def test_content_tokenizer_normalizes_platform_names_without_generic_fragments(self):
        tokenizer = TitleTokenizer(Path(__file__).resolve().parent.parent / "analysis")

        tokens = tokenizer.tokenize("字节跳动和谷歌都在更新，工资数字一直跳动")

        self.assertTrue({"字节跳动", "Google"} <= tokens)
        self.assertNotIn("跳动", tokens)

    def test_content_tokenizer_splits_unknown_mixed_script_segments(self):
        tokenizer = TitleTokenizer(Path(__file__).resolve().parent.parent / "analysis")

        tokens = tokenizer.tokenize("招聘PHP和Android开发，在mac上运行我的MacBook应用")

        self.assertTrue({"招聘", "PHP", "Android", "Mac", "MacBook"} <= tokens)
        self.assertFalse({"招聘PHP", "和Android", "在mac", "我的MacBook"} & tokens)

    def test_content_tokenizer_keeps_alphanumeric_entities_on_token_boundaries(self):
        tokenizer = TitleTokenizer(Path(__file__).resolve().parent.parent / "analysis")

        tokens = tokenizer.tokenize("M1 芯片和 M4 Pro，车型 M135i 与编号 M4394a")

        self.assertTrue({"M1", "M4"} <= tokens)
        self.assertNotIn("M1", tokenizer.tokenize("车型 M135i"))
        self.assertNotIn("M4", tokenizer.tokenize("编号 M4394a"))

    def test_content_tokenizer_normalizes_reviewed_platform_and_network_entities(self):
        tokenizer = TitleTokenizer(Path(__file__).resolve().parent.parent / "analysis")

        tokens = tokenizer.tokenize(
            "油管和 TG 都打不开，用 OpenWrt、WireGuard、Tailscale，团队改用 Lark 和 ReactNative 调用 api"
        )

        self.assertTrue(
            {"YouTube", "Telegram", "OpenWrt", "WireGuard", "Tailscale", "飞书", "React Native", "API"}
            <= tokens
        )
        self.assertNotIn("Api", tokens)

    def test_confirmed_content_terms_use_independent_detail_thresholds(self):
        analysis_dir = Path(__file__).resolve().parent.parent / "analysis"
        confirmed = _confirmed_detail_terms(analysis_dir)
        self.assertTrue(
            {
                "成都", "外包", "Bug", "UI", "部署", "蓝牙", "爬虫", "性能", "运维", "Offer", "Nginx",
                "OpenWrt", "Telegram", "YouTube", "Steam", "Notion", "飞书", "抖音", "小红书", "Tailscale",
            }
            <= confirmed
        )
        monthly_rows = {
            ("2026-07", "GLM"): ["GLM", 8, 5, 2],
            ("2026-07", "MiniMax"): ["MiniMax", 7, 7, 4],
            ("2026-07", "普通词"): ["普通词", 20, 18, 8],
        }
        annual_rows = {
            "2026": {
                "MiniMax": ["MiniMax", 30, 15, 2],
                "Qwen": ["Qwen", 30, 14, 5],
            }
        }

        selected = _qualifying_detail_terms(confirmed, monthly_rows, annual_rows)

        self.assertTrue({"GLM", "MiniMax"} <= selected)
        self.assertFalse({"普通词", "Qwen"} & selected)

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

    def test_content_groups_deduplicate_group_hits_and_keep_matching_terms(self):
        matches = content_group_matches(
            {"AI", "ChatGPT", "Python", "无关词"},
            {
                "AI": {"ai-models"},
                "ChatGPT": {"ai-models"},
                "Python": {"software-development"},
            },
        )

        self.assertEqual(matches["ai-models"], {"AI", "ChatGPT"})
        self.assertEqual(matches["software-development"], {"Python"})
        self.assertEqual(set(matches), {"ai-models", "software-development"})

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
        totals.update({"投资": 10, "理财": 9, "股票": 8, "基金": 7, "失业": 6})
        selected = select_topic_tags(
            totals,
            limit=500,
            focused_tags=frozenset({"投资", "理财", "股票", "基金", "失业"}),
        )
        names = {tag for tag, _ in selected}
        self.assertEqual(len(selected), 500)
        self.assertTrue({"投资", "理财", "股票", "基金", "失业"} <= names)
        self.assertIn("tag-494", names)
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

    def test_topic_group_names_define_canonical_tag_casing(self):
        synonyms = analytics_builder.synonym_map(include_source_tags=False)

        self.assertEqual(
            normalize_tags(
                ["agent", "Agent", "m1", "M1", "m4", "M4", "Nodejs", "node.js"],
                synonyms,
                set(),
            ),
            {"Agent", "M1", "M4", "Node.js"},
        )

    def test_source_tag_canonical_map_keeps_first_stable_casing(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "source.sqlite"
            source = sqlite3.connect(source_path)
            source.execute(
                """
                CREATE TABLE topic (
                    id INTEGER PRIMARY KEY, tag TEXT, create_at INTEGER, clicks INTEGER
                )
                """
            )
            source.executemany(
                "INSERT INTO topic VALUES (?, ?, ?, ?)",
                [
                    (1, '["opencode", "SEO"]', 1704067200, 10),
                    (2, '["OpenCode", "seo"]', 1704153600, 20),
                ],
            )
            source.commit()
            source.close()

            with patch.object(analytics_builder, "SOURCE_DB", source_path):
                analytics_builder._source_tag_canonical_cache = None
                canonical = analytics_builder.source_tag_canonical_map()
                analytics_builder._source_tag_canonical_cache = None

            self.assertEqual(canonical["opencode"], "opencode")
            self.assertEqual(canonical["seo"], "SEO")

    def test_topic_group_matches_only_nodes_or_original_topics(self):
        group = {"nodes": ["jobs"], "topics": ["AI", "求职"]}

        self.assertTrue(matches_topic_group("jobs", set(), group))
        self.assertTrue(matches_topic_group("qna", {"ai"}, group))
        self.assertFalse(matches_topic_group("qna", set(), group))
        self.assertFalse(matches_topic_group("programmer", {"SQLite"}, group))
        self.assertFalse(matches_topic_group("cosub", {"AI"}, group))
        self.assertEqual(matching_group_topics({"ai", "求职", "Python"}, group), {"AI", "求职"})

    def test_topic_group_collection_uses_nodes_but_exports_only_original_topics(self):
        source = sqlite3.connect(":memory:")
        source.executescript(
            """
            CREATE TABLE topic (
                id INTEGER PRIMARY KEY, title TEXT, node TEXT, tag TEXT,
                create_at INTEGER, reply_count INTEGER, clicks INTEGER
            );
            INSERT INTO topic VALUES
                (1, 'AI 编程工具', 'qna', '["AI", "Python", "低频"]', 1704067200, 4, 10),
                (2, '普通标题', 'ai', '["AirPods"]', 1704067200, 2, 10),
                (3, 'AI 服务拼车', 'cosub', '["AI"]', 1704067200, 1, 10);
            """
        )

        periods, group_topics = collect_topic_groups(
            source,
            {"ai": {"nodes": ["ai"], "topics": ["AI", "Python"]}},
            {},
            set(),
        )

        self.assertEqual(periods[("2024-01", "ai")], [2, 6, 1])
        self.assertEqual(group_topics, {
            ("2024-01", "ai", "AI"): 1,
            ("2024-01", "ai", "Python"): 1,
        })
        source.close()

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

    def test_node_period_post_bucket_is_stable_and_bounded(self):
        self.assertEqual(node_period_post_bucket("programmer"), node_period_post_bucket("programmer"))
        self.assertRegex(node_period_post_bucket("programmer"), r"^[0-9a-f]{2}$")

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
