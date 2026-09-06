import ast
import copy
import inspect
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from analysis.builders.common import LOCAL_TIMEZONE
from analysis.builders import presentation as presentation_builder
from analysis.builders.presentation import build_presentation


SLIDE_IDS = [
    "cover", "scope", "overview", "node-evolution", "members", "rhythm",
    "topic-structure", "keyword-timeline", "ai-topics", "ai-tools", "career",
    "cities", "housing", "finance", "creation", "favorites", "thanks",
    "comment-thanks", "summary", "explore",
]


def timestamp(period):
    return int(datetime.fromisoformat(f"{period}-15").replace(tzinfo=LOCAL_TIMEZONE).timestamp())


class PresentationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.public_dir = Path(temporary.name)
        self.source = sqlite3.connect(":memory:")
        self.addCleanup(self.source.close)
        self.source.execute(
            """CREATE TABLE topic (
                id INTEGER PRIMARY KEY, title TEXT, node TEXT, tag TEXT,
                content TEXT, create_at INTEGER, clicks INTEGER,
                favorite_count INTEGER, thank_count INTEGER, reply_count INTEGER
            )"""
        )
        self.source.execute(
            """CREATE TABLE comment (
                id INTEGER PRIMARY KEY, topic_id INTEGER, commenter TEXT,
                content TEXT, create_at INTEGER, thank_count INTEGER
            )"""
        )
        periods = [f"{year}-{month:02d}" for year in range(2010, 2027) for month in range(1, 13)
                   if "2010-04" <= f"{year}-{month:02d}" <= "2026-09"]
        self.overview = {
            "metadata": {"start_period": "2010-04", "default_end_period": "2026-08",
                         "end_period": "2026-09", "incomplete_periods": ["2026-09"],
                         "participant_count": 500, "analysis_coverage": {"topics": 500, "nodes": 443}},
            "periods": [{"period": period, "topic_count": 1000, "comment_count": 2000,
                         "member_count": 100} for period in periods],
            "activity": [[period, weekday, hour, posts, comments]
                         for period in periods
                         for weekday, hour, posts, comments in ((0, 10, 30, 60), (6, 22, 70, 40))],
        }
        groups = ("apple", "engineering", "ai", "home", "career", "creation", "finance", "crypto")
        tags = ("ChatGPT", "AI", "模型", "Python", "Java", "招聘", "面试", "裁员", "失业",
                "买房", "房价", "房贷", "租房", "拼车", "88vip", "订阅")
        self.topics = {
            "rows": [[period, tag, 10] for period in periods for tag in tags],
            "group_rows": [[period, group, 20] for period in periods for group in groups],
            "groups": [{"name": group, "label": group, "topics": ["基金"] if group == "finance" else [],
                        "nodes": ["invest"] if group == "finance" else []} for group in groups],
        }
        self.nodes = {"rows": [[period, node, value] for period in periods for node, value in
                               (("qna", 300), ("all4all", 150), ("jobs", 80), ("create", 50),
                                ("life", 70), ("programmer", 100))]}
        terms = ("Codex", "Agent", "Claude Code", "Cursor", "DeepSeek", "iOS", "Android", "工程师", "招聘",
                 "疫情", "M1", "MacBook", "远程", "ChatGPT", "OpenAI", "API", "模型", "额度",
                 "北京", "上海", "深圳", "杭州", "广州", "开源", "Java", "Python")
        self.content_rows = [[period, term, 2] for period in periods for term in terms]
        self.lifecycle = {
            "metadata": {"first_reply_complete_through": "2026-07", "long_tail_complete_through": "2026-07"},
            "first_reply_rows": [[period, bucket, value] for period in periods
                                 for bucket, value in (("10m", 40), ("1h", 20), ("6h", 15), ("24h", 5), ("none", 20))],
            "long_tail_rows": [[period, 500, 100, 10, 100] for period in periods],
        }
        self.engagement = {"top_posts": {"favorite_count": [], "thank_count": []}, "top_comments": []}
        self.scale = {
            "metadata": {"start_period": "2010-04", "end_period": "2026-08",
                         "scope": "complete_history", "counts": {"posts": 197000, "comments": 394000}},
            "post_metrics": {"favorites": {
                "observed_count": 196985,
                "rows": [{"threshold": t, "count": c} for t, c in ((500, 10), (100, 100), (20, 500), (5, 1000))],
            }},
            "member_metrics": {"comments": {
                "observed_count": 450,
                "rows": [{"threshold": t, "count": c} for t, c in ((10000, 1), (1000, 10), (100, 50), (5, 200))],
            }},
        }

    def build(self, source=None, scale=None):
        return build_presentation(self.overview, self.topics, self.nodes, self.lifecycle,
                                  self.engagement, self.content_rows,
                                  self.source if source is None else source, self.public_dir, scale=scale)

    def add_post(self, topic_id, *, period="2025-01", node="programmer", tags=(), content="",
                 clicks=-1, favorites=-1, thanks=-1, replies=-1):
        self.source.execute("INSERT INTO topic VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (topic_id, f"Post {topic_id}", node, json.dumps(tags), content,
                             timestamp(period), clicks, favorites, thanks, replies))

    def write_codex_detail(self, rows, total=None):
        index = {"terms": {"Codex": {"bucket": "08"}}}
        detail = {"details": {"Codex": {"rows": rows, "total": sum(row[2] for row in rows) if total is None else total,
                                         "related_terms": [["额度", 7], ["重置", 5]]}}}
        (self.public_dir / "dynamic-content-hotspots-index.json").write_text(json.dumps(index), encoding="utf-8")
        (self.public_dir / "dynamic-content-term-details-08.json").write_text(json.dumps(detail), encoding="utf-8")

    def add_comment(self, comment_id, topic_id, content, *, period="2025-01", thanks=0):
        self.source.execute("INSERT INTO comment VALUES (?, ?, ?, ?, ?, ?)",
                            (comment_id, topic_id, "reader", content, timestamp(period), thanks))

    def test_twenty_ordered_slides_and_chart_contract(self):
        result = self.build(scale=self.scale)
        self.assertEqual([slide["id"] for slide in result["slides"]], SLIDE_IDS)
        types = {"cover", "facts", "chart", "timeline", "posts", "summary", "explore"}
        chart_keys = set()
        for slide in result["slides"]:
            with self.subTest(slide=slide["id"]):
                self.assertIn(slide["type"], types)
                for key in ("chapter", "eyebrow", "title", "summary", "note"):
                    self.assertTrue(slide[key])
                self.assertLessEqual(len(slide.get("metrics", [])), 6 if slide["id"] == "scope" else 3)
                self.assertLessEqual(len(slide.get("posts", [])), 3 if slide["type"] == "posts" or slide.get("post_layout") == "strip" else 2)
                if slide["type"] == "chart":
                    chart_keys.add(slide["chart"])
                chart_keys.update(item["chart"] for item in slide.get("takeaways", []) if "chart" in item)
                chart_keys.update(item["chart"] for item in slide.get("panels", []))
        self.assertEqual(chart_keys, set(result["charts"]))
        for key, chart in result["charts"].items():
            with self.subTest(chart=key):
                self.assertIn(chart["kind"], {"line", "small_multiples", "grouped_bar", "horizontal_bar", "hourly_bars"})
                self.assertTrue(all(isinstance(category, str) for category in chart["categories"]))
                self.assertTrue(set(chart["partial"]) <= set(chart["categories"]))
                self.assertTrue(all(item["category"] in chart["categories"] for item in chart["annotations"]))
                for series in chart["series"]:
                    self.assertEqual(len(series["values"]), len(chart["categories"]))
                    self.assertTrue(all(isinstance(value, (float, int)) for value in series["values"]))
        self.assertEqual(result["charts"]["node_totals"]["category_kind"], "node")
        self.assertEqual(result["charts"]["node_evolution"]["series_kind"], "node")
        self.assertEqual(len(result["charts"]["topic_comparison"]["categories"]), 6)
        self.assertEqual(result["slides"][SLIDE_IDS.index("cover")]["title"], "V2EX 看板")
        self.assertEqual(len(result["slides"][SLIDE_IDS.index("summary")]["takeaways"]), 3)
        self.assertNotIn("chips", result["slides"][SLIDE_IDS.index("summary")])
        json.dumps(result, allow_nan=False)

    def test_excluded_months_cannot_change_any_numerator_or_denominator(self):
        baseline = self.build()
        for row in self.overview["periods"]:
            if row["period"] == "2026-09":
                row.update(topic_count=10**9, comment_count=10**9, member_count=10**9)
        for rows in (self.topics["rows"], self.topics["group_rows"], self.nodes["rows"], self.content_rows):
            for row in rows:
                if row[0] == "2026-09":
                    row[2] = 10**9
        self.overview["activity"].append(["2026-09", 0, 0, 10**9, 10**9])
        self.lifecycle["first_reply_rows"].append(["2026-09", "10m", 10**9])
        self.lifecycle["long_tail_rows"].append(["2026-09", 10**9, 0, 10**9, 10**9])
        future = {"id": 999, "period": "2026-09", "value": 10**9, "node": "life"}
        self.engagement["top_posts"]["favorite_count"].append(future)
        self.engagement["top_posts"]["thank_count"].append(future)
        self.engagement["top_comments"].append({"id": 999, "create_at": timestamp("2026-09"), "thank_count": 10**9})
        self.add_post(920519, period="2026-09", favorites=10**9)
        self.assertEqual(baseline, self.build())

    def test_overview_follows_members_posts_comments_order_and_highlights_valid_points(self):
        result = self.build()
        expected = ["新增成员", "帖子", "评论"]
        self.assertEqual([item["name"] for item in result["charts"]["overview"]["series"]], expected)
        slide = next(slide for slide in result["slides"] if slide["id"] == "overview")
        self.assertNotIn("metrics", slide)
        self.assertNotIn("findings", slide)
        for chart in result["charts"].values():
            for series in chart["series"]:
                if highlight := series.get("highlight"):
                    self.assertIn(highlight["category"], chart["categories"])
                    if chart["kind"] != "small_multiples":
                        self.assertNotIn(highlight["category"], chart["partial"])
                    self.assertTrue(highlight["label"])

    def test_partial_years_cutoff_and_month_labels_are_dynamic(self):
        self.overview["metadata"]["default_end_period"] = "2026-02"
        result = self.build()
        for key in ("overview", "career", "finance", "housing", "creation", "finance_terms", "node_evolution"):
            chart = result["charts"][key]
            self.assertEqual(chart["partial"], ["2010", "2026"])
            self.assertIn({"category": "2026", "label": "2026 年 1-2 月"}, chart["annotations"])
        self.assertEqual(result["charts"]["ai_tools"]["categories"][-1], "2026-02")
        codex = next(item for item in result["charts"]["ai_tools"]["series"] if item["name"] == "Codex")
        self.assertEqual(sum(value for period, value in zip(result["charts"]["ai_tools"]["categories"], codex["values"]) if period.startswith("2026")), 4)
        self.assertEqual(result["slides"][SLIDE_IDS.index("keyword-timeline")]["milestones"][-1]["period"], "2026-01 至 2026-02")
        self.assertNotIn("截至 8 月", json.dumps(result, ensure_ascii=False))
        self.overview["metadata"]["default_end_period"] = "2025-12"
        self.assertEqual(self.build()["charts"]["overview"]["partial"], ["2010"])

    def test_explicit_incomplete_month_is_excluded_inside_cutoff(self):
        self.overview["metadata"]["incomplete_periods"].append("2026-07")
        result = self.build()
        self.assertNotIn("2026-07", result["charts"]["ai_tools"]["categories"])
        self.assertEqual(result["scope"]["topics"], result["scope"]["complete_months"] * 1000)
        chart = result["charts"]["ai_tools"]
        codex = next(item for item in chart["series"] if item["name"] == "Codex")
        self.assertEqual(sum(value for period, value in zip(chart["categories"], codex["values"]) if period.startswith("2026")), 14)

    def test_unknown_post_interactions_remain_null_and_zero_remains_zero(self):
        self.add_post(920519, content="<p>群里有大佬基于新的 API 搞了个网站</p>", thanks=0)
        self.add_post(1022439, clicks=0, favorites=12, thanks=3, replies=4)
        posts = self.build()["slides"][SLIDE_IDS.index("ai-tools")]["posts"]
        self.assertEqual(len(posts), 2)
        self.assertIsNone(posts[0]["clicks"])
        self.assertIsNone(posts[0]["favorites"])
        self.assertIsNone(posts[0]["replies"])
        self.assertEqual(posts[0]["thanks"], 0)
        self.assertEqual(posts[1]["clicks"], 0)
        self.assertEqual(posts[1]["favorites"], 12)
        self.assertEqual(posts[0]["selection"], "人工选取")
        self.assertIn("excerpt", posts[0])
        self.assertNotIn("excerpt", posts[1])
        self.assertIn("未能核实", posts[1]["note"])

    def test_missing_cases_and_database_do_not_create_files_or_placeholders(self):
        missing = self.public_dir / "absent.sqlite"
        for source in (self.source, missing):
            result = self.build(source)
            self.assertEqual(len(result["slides"]), 20)
            self.assertTrue(all(not slide.get("posts") for slide in result["slides"]))
        self.assertFalse(missing.exists())
        self.add_post(931949, content="我自己在日常会整理、收藏一些比较有质量的课程")
        self.assertEqual(self.build()["slides"][SLIDE_IDS.index("favorites")]["posts"], [])
        self.engagement["top_posts"]["favorite_count"] = [{"id": 931949, "period": "2025-01", "value": 10}]
        self.assertEqual([post["id"] for post in self.build()["slides"][SLIDE_IDS.index("favorites")]["posts"]], [931949])

    def test_source_reads_are_only_a_bounded_primary_key_query(self):
        queries = []
        self.source.set_trace_callback(queries.append)
        self.build()
        self.assertEqual(len(queries), 2)
        self.assertIn("FROM topic WHERE id IN (", queries[0])
        self.assertNotIn("GROUP BY", queries[0])
        self.assertNotIn("JOIN", queries[0])
        self.assertNotIn("966243", queries[0])
        self.assertNotIn("1197162", queries[0])
        self.assertIn("WHERE c.id IN (", queries[1])
        self.assertNotIn("GROUP BY", queries[1])
        plan = self.source.execute("EXPLAIN QUERY PLAN " + queries[1]).fetchall()
        self.assertTrue(all("SEARCH" in row[3] and "INTEGER PRIMARY KEY" in row[3] for row in plan))

    def test_rankings_use_actual_top_three_not_curated_case_membership(self):
        self.engagement["top_posts"]["favorite_count"] = [
            {"id": i, "period": period, "favorite_count": value, "title": f"Case {i}"}
            for i, period, value in ((1, "2025-01", 40), (2, "2025-01", 100),
                                     (3, "2026-09", 999), (4, "2025-01", -1),
                                     (5, "2025-01", 60), (6, "2025-01", 0))
        ]
        posts = self.build()["slides"][SLIDE_IDS.index("favorites")]["posts"]
        self.assertEqual([post["id"] for post in posts], [2, 5, 1])
        self.assertEqual([post["favorites"] for post in posts], [100, 60, 40])
        self.assertEqual([post["rank"] for post in posts], [1, 2, 3])
        self.assertTrue(all(post["ranking_metric"] == "favorites" for post in posts))

    def test_comment_ranking_keeps_context_and_filters_unknown_future_and_anomalous_rows(self):
        self.engagement["top_comments"] = [
            {"id": i, "topic_id": 10, "commenter": user, "create_at": timestamp(period),
             "thank_count": value, "content": content, "topic_title": "原帖标题"}
            for i, user, period, value, content in (
                (1, "a", "2025-01", 100, "一句回应"), (2, "USDC", "2025-01", 1000, "排除"),
                (3, "b", "2026-09", 999, "未来"), (4, "c", "2025-01", -1, "未知"),
                (5, "d", "2025-01", 50, "[图片]"), (6, "e", "2025-01", 80, "另一回应"),
            )
        ]
        queries = []
        self.source.set_trace_callback(queries.append)
        comments = self.build()["slides"][SLIDE_IDS.index("comment-thanks")]["comments"]
        self.assertEqual([comment["id"] for comment in comments], [1, 6, 5])
        self.assertIn("原文未收录", comments[-1]["text"])
        self.assertEqual(comments[0]["topic_title"], "原帖标题")
        self.assertEqual(len(queries), 3)
        self.assertIn("WHERE c.id IN (", queries[-1])

    def test_finance_objects_use_title_keywords_not_topic_label_history(self):
        self.content_rows.extend([["2019-01", "黄金", 25], ["2026-09", "黄金", 999]])
        chart = self.build()["charts"]["finance_terms"]
        series = next(row for row in chart["series"] if row["name"] == "黄金")
        self.assertEqual(series["values"][chart["categories"].index("2019")], round(25 / 12000 * 10000, 1))
        self.assertEqual(series["values"][-1], 0)

    def test_finance_cases_must_match_existing_group_definition(self):
        self.add_post(1117738, node="invest", content="还是专业的事交给专业的人, 抄作业得了")
        groups = {group["name"]: group for group in self.topics["groups"]}
        def selected():
            return presentation_builder._load_posts(self.source, {"2025-01"}, groups)
        self.assertIn("节点 invest", selected()[1117738]["note"])
        self.source.execute("UPDATE topic SET node = ?, tag = ?", ("qna", json.dumps(["基金"])))
        self.assertIn("原始话题 基金", selected()[1117738]["note"])
        for node in ("programmer", "promotions"):
            self.source.execute("UPDATE topic SET node = ?, tag = ?", (node, "[]"))
            self.assertNotIn(1117738, selected())

    def test_codex_cooccurrence_is_whole_period_not_recent_or_a_union(self):
        self.write_codex_detail([["2025-01", "Codex", 10], ["2026-08", "Codex", 20]])
        slide = self.build()["slides"][SLIDE_IDS.index("ai-tools")]
        self.assertNotIn("metrics", slide)
        self.assertIn("全期 30", slide["summary"])
        self.assertIn("7 个提到额度、5 个提到重置", slide["summary"])
        self.assertIn("未计算", slide["note"])
        self.assertEqual(len(list(self.public_dir.glob("*.json"))), 2)

    def test_cooccurrence_outside_window_or_inconsistent_total_is_not_relabelled(self):
        for rows, total in (([["2026-08", "Codex", 20], ["2026-09", "Codex", 999]], None),
                            ([["2010-03", "Codex", 10], ["2026-08", "Codex", 20]], None),
                            ([["2026-08", "Codex", 20]], 999)):
            with self.subTest(rows=rows, total=total):
                self.write_codex_detail(rows, total)
                slide = self.build()["slides"][SLIDE_IDS.index("ai-tools")]
                self.assertNotIn("metrics", slide)
                self.assertNotIn("共现", slide["summary"])
                self.assertIn("未展示", slide["note"])

    def test_selected_comment_requires_verified_prose_and_an_in_scope_date(self):
        self.add_post(437760, period="2018-03")
        self.add_comment(5432223, 437760, "我相信大多数 v 友遇到这种情况都会和我一样的做法 。谢谢大家。",
                         period="2018-03", thanks=306)
        comments = list(presentation_builder._load_comments(self.source, {"2018-03"}).values())
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["thanks"], 306)
        self.assertEqual(comments[0]["url"], "https://www.v2ex.com/t/437760#r_5432223")
        self.assertEqual(comments[0]["date"], "2018-03-15")
        for column, value in (("content", "[图片]"), ("create_at", timestamp("2026-09")), ("topic_id", 999)):
            with self.subTest(column=column):
                original = self.source.execute(f"SELECT {column} FROM comment").fetchone()[0]
                self.source.execute(f"UPDATE comment SET {column}=?", (value,))
                self.assertEqual(presentation_builder._load_comments(self.source, {"2018-03"}), {})
                self.source.execute(f"UPDATE comment SET {column}=?", (original,))
        self.source.execute("UPDATE comment SET thank_count=-1")
        self.assertIsNone(presentation_builder._load_comments(self.source, {"2018-03"})[5432223]["thanks"])

    def test_annual_rates_and_timeline_counts_use_filtered_months(self):
        result = self.build()
        self.assertEqual(result["charts"]["career"]["series"][0]["values"][-1], 100)
        self.assertEqual(result["charts"]["finance"]["series"][0]["values"][-1], 2)
        self.assertEqual(result["charts"]["node_evolution"]["series"][0]["values"][-1], 30)
        milestones = result["slides"][SLIDE_IDS.index("keyword-timeline")]["milestones"]
        self.assertEqual(len(milestones), 5)
        self.assertTrue(all(len(milestone["items"]) == 4 for milestone in milestones))
        self.assertEqual(milestones[0]["items"][0], {"label": "iOS", "count": 24})
        self.assertEqual(milestones[-1]["items"][0], {"label": "Codex", "count": 16})
        self.assertEqual(result["charts"]["topic_comparison"]["series"][0]["values"], [2] * 6)

    def test_peaks_are_calculated_instead_of_assuming_2019(self):
        for row in self.overview["periods"]:
            if row["period"].startswith("2018"):
                row["topic_count"] = 2000
        series = next(item for item in self.build()["charts"]["overview"]["series"] if item["name"] == "帖子")
        self.assertEqual(series["highlight"], {"category": "2018", "label": "2018 · 2,000/月"})

    def test_overview_peak_uses_unrounded_monthly_average(self):
        for row in self.overview["periods"]:
            if row["period"] == "2018-01":
                row["topic_count"] += 1
        series = next(item for item in self.build()["charts"]["overview"]["series"] if item["name"] == "帖子")
        self.assertEqual(series["highlight"]["category"], "2018")

    def test_top_twenty_overlap_is_dynamic_and_filters_before_limiting(self):
        def post(topic_id, period="2025-01", value=None):
            return {"id": topic_id, "period": period, "value": 1000 - topic_id if value is None else value, "title": "Post"}

        self.engagement["top_posts"] = {
            "favorite_count": [post(999, "2026-09"), post(998, value=-1)] +
                              [post(topic_id) for topic_id in range(1, 26)],
            "thank_count": [post(999, "2026-09")] +
                           [post(topic_id) for topic_id in range(15, 35)],
        }
        result = self.build()
        self.assertEqual(result["interaction"]["overlap"], 6)
        self.assertEqual(result["slides"][SLIDE_IDS.index("summary")]["takeaways"][2]["value"], "6 / 20")
        self.assertEqual(result["interaction"]["favorite_post"]["id"], 1)
        self.engagement["top_posts"]["thank_count"] = [post(topic_id) for topic_id in range(30, 50)]
        self.assertEqual(self.build()["interaction"]["overlap"], 0)

    def test_lifecycle_cutoff_and_hourly_denominators_are_independent(self):
        baseline = self.build()
        self.lifecycle["first_reply_rows"].append(["2026-08", "10m", 10**9])
        self.lifecycle["long_tail_rows"].append(["2026-08", 10**9, 0, 10**9, 10**9])
        result = self.build()
        self.assertEqual(result["rhythm"], baseline["rhythm"])
        self.assertEqual(result["rhythm"]["within_1h_share"], 60)
        self.assertEqual(result["rhythm"]["within_24h_share"], 80)
        chart = result["charts"]["activity"]
        self.assertEqual(chart["categories"], [f"{hour:02d}:00" for hour in range(24)])
        self.assertEqual(chart["series"][0]["values"][10], 30)
        self.assertEqual(chart["series"][1]["values"][10], 60)
        self.assertTrue(all(sum(series["values"]) == 100 for series in chart["series"]))

    def test_inputs_are_not_mutated(self):
        inputs = (self.overview, self.topics, self.nodes, self.lifecycle, self.engagement, self.content_rows)
        original = copy.deepcopy(inputs)
        self.build()
        self.assertEqual(inputs, original)

    def test_equal_member_windows_when_latest_window_is_short(self):
        self.overview["metadata"]["default_end_period"] = "2024-07"
        slide = self.build()["slides"][SLIDE_IDS.index("members")]
        self.assertEqual(len(slide["metrics"]), 3)
        self.assertTrue(all("各 3 个完整月份" in metric["detail"] for metric in slide["metrics"]))
        self.assertIn("2024-02 至 2024-04", slide["note"])
        self.assertIn("2024-05 至 2024-07", slide["note"])

    def test_sparse_history_and_empty_rankings_do_not_crash(self):
        self.overview["periods"] = [self.overview["periods"][-2]]
        self.overview["activity"] = []
        self.lifecycle = {}
        result = self.build()
        self.assertEqual(len(result["slides"]), 20)
        self.assertEqual(result["interaction"]["favorite_post"], {})
        self.assertIsNone(result["interaction"]["comment_top_thanks"])
        self.overview["periods"] = []
        with self.assertRaisesRegex(ValueError, "complete month"):
            self.build()

    def test_scale_charts_use_existing_thresholds_and_known_denominators(self):
        result = self.build(scale=self.scale)
        self.assertEqual(result["slides"][SLIDE_IDS.index("scope")]["panels"][0]["chart"], "favorite_scale")
        self.assertEqual(result["slides"][SLIDE_IDS.index("scope")]["title"], "浏览、收藏与感谢的规模分布")
        self.assertNotIn("commenter_scale", result["charts"])
        self.assertNotIn("conclusion", [slide["id"] for slide in result["slides"]])
        self.assertEqual(result["charts"]["favorite_scale"]["categories"],
                         [">=5 次", ">=20 次", ">=100 次", ">=500 次"])
        self.assertEqual(result["charts"]["favorite_scale"]["series"][0]["values"], [1000, 500, 100, 10])
        self.assertIn("196,985", result["slides"][SLIDE_IDS.index("scope")]["panels"][0]["detail"])
        self.assertIn("450 位用户参与评论", result["slides"][SLIDE_IDS.index("scope")]["summary"])
        for index in (SLIDE_IDS.index("scope"),):
            self.assertLessEqual(len(result["slides"][index].get("metrics", [])), 2)
            self.assertNotIn("findings", result["slides"][index])

    def test_city_counts_and_latest_order_use_complete_months_only(self):
        for row in self.content_rows:
            if row[1] == "北京" and row[0] < "2026-01":
                row[2] = 5
            if row[1] == "上海" and row[0].startswith("2026-"):
                row[2] = 10
        result = self.build()
        chart = result["charts"]["city_totals"]
        self.assertEqual(chart["categories"][:2], ["北京", "上海"])
        self.assertEqual(chart["series"][0]["values"][:2], [189 * 5 + 8 * 2, 189 * 2 + 8 * 10])
        city = result["slides"][SLIDE_IDS.index("cities")]
        self.assertIn("2026 年 1-8 月，上海 80 帖", city["summary"])
        self.assertIn("不代表用户所在地", city["note"])
        trend = result["charts"]["city_evolution"]
        self.assertEqual(trend["unit"], "帖/万帖")
        self.assertEqual(trend["series"][0]["values"][-1], 20)
        self.assertEqual(trend["series"][1]["values"][-1], 100)
        self.assertIn("2026", trend["partial"])

    def write_keyword_context(self, names):
        details = {}
        for name in names:
            rows = [row for row in self.content_rows if row[1] == name and row[0] <= "2026-08"]
            total = sum(row[2] for row in rows)
            details[name] = {"rows": rows, "total": total, "nodes": [["jobs", 197]]}
        (self.public_dir / "dynamic-content-hotspots-index.json").write_text(
            json.dumps({"terms": {name: {"bucket": "01"} for name in names}}), encoding="utf-8")
        path = self.public_dir / "dynamic-content-term-details-01.json"
        path.write_text(json.dumps({"details": details}), encoding="utf-8")
        return path, details

    def test_recruitment_context_requires_exact_scope_and_valid_node_counts(self):
        path, details = self.write_keyword_context(("北京", "工程师", "Java", "Python"))
        result = self.build()
        self.assertIn("北京 50.0%", result["slides"][SLIDE_IDS.index("cities")]["findings"][0]["text"])
        self.assertIn("工程师 50.0%", result["slides"][SLIDE_IDS.index("keyword-timeline")]["findings"][0]["text"])
        self.assertIn("Java 50.0%、Python 50.0%", result["slides"][SLIDE_IDS.index("keyword-timeline")]["findings"][0]["text"])
        for mode in ("future", "wrong_month", "negative", "too_many", "wrong_total", "missing_jobs"):
            with self.subTest(mode=mode):
                altered = copy.deepcopy(details)
                for detail in altered.values():
                    if mode == "future":
                        detail["rows"].append(["2026-09", "北京", 2])
                        detail["total"] += 2
                    elif mode == "wrong_month":
                        detail["rows"][0][0] = "2009-01"
                    elif mode == "negative":
                        detail["nodes"] = [["jobs", -1]]
                    elif mode == "too_many":
                        detail["nodes"] = [["jobs", 197], ["qna", 300]]
                    elif mode == "wrong_total":
                        detail["total"] += 1
                    else:
                        detail["nodes"] = [["qna", 197]]
                path.write_text(json.dumps({"details": altered}), encoding="utf-8")
                result = self.build()
                self.assertEqual(result["slides"][SLIDE_IDS.index("cities")]["findings"], [])
                self.assertEqual(result["slides"][SLIDE_IDS.index("keyword-timeline")]["findings"], [])
        path.write_text(json.dumps({"details": details}), encoding="utf-8")
        self.overview["metadata"]["default_end_period"] = "2026-07"
        self.assertEqual(self.build()["slides"][SLIDE_IDS.index("cities")]["findings"], [])

    def test_open_source_comparison_matches_months_and_handles_missing_baseline(self):
        for row in self.content_rows:
            if row[1] == "开源" and row[0].startswith("2026-"):
                row[2] = 4
        result = self.build()
        text = result["slides"][SLIDE_IDS.index("creation")]["summary"]
        self.assertIn("16→32 帖", text)
        self.assertIn("每万帖 20.0→40.0", text)
        self.assertIn("不能直接归因于 AI", text)
        self.overview["periods"] = [row for row in self.overview["periods"] if row["period"] != "2025-03"]
        self.assertNotIn("同月比较", self.build()["slides"][SLIDE_IDS.index("creation")]["summary"])

    def test_missing_city_keywords_do_not_produce_zero_rankings(self):
        names = {"北京", "上海", "深圳", "杭州", "广州"}
        self.content_rows = [row for row in self.content_rows if row[1] not in names]
        result = self.build()
        self.assertNotIn("city_totals", result["charts"])
        self.assertNotIn("city_evolution", result["charts"])
        self.assertNotIn("panels", result["slides"][SLIDE_IDS.index("cities")])
        self.assertIn("暂不展示排名", result["slides"][SLIDE_IDS.index("cities")]["summary"])

    def test_scale_is_loaded_read_only_from_public_json_or_explicit_input(self):
        path = self.public_dir / "dynamic-scale-distribution.json"
        path.write_text(json.dumps(self.scale), encoding="utf-8")
        before = path.read_bytes()
        original = copy.deepcopy(self.scale)
        self.assertEqual(self.build(), self.build(scale=self.scale))
        self.assertEqual(self.scale, original)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.build(scale={})["slides"][SLIDE_IDS.index("scope")]["type"], "facts")

    def test_scale_missing_or_mismatched_snapshots_fall_back_without_zero_charts(self):
        snapshots = [{}, {**self.scale, "metadata": {}}]
        for key, value in (("start_period", "2010-05"), ("end_period", "2026-07"),
                           ("scope", "recent_history")):
            scale = copy.deepcopy(self.scale)
            scale["metadata"][key] = value
            snapshots.append(scale)
        for key in ("posts", "comments"):
            scale = copy.deepcopy(self.scale)
            scale["metadata"]["counts"][key] += 1
            snapshots.append(scale)
        for scale in snapshots:
            with self.subTest(metadata=scale.get("metadata")):
                result = self.build(scale=scale)
                for index, chart in ((SLIDE_IDS.index("scope"), "favorite_scale"),):
                    self.assertEqual(result["slides"][index]["type"], "facts")
                    self.assertIn("没有匹配", result["slides"][index]["summary"])
                    self.assertNotIn(chart, result["charts"])
                    self.assertNotIn("chart", result["slides"][index])
                    self.assertNotIn("metrics", result["slides"][index])

    def test_scale_cutoff_and_start_changes_cannot_relabel_full_history(self):
        for start, end in (("2010-04", "2026-07"), ("2016-09", "2026-08")):
            with self.subTest(start=start, end=end):
                self.overview["metadata"].update(start_period=start, default_end_period=end)
                self.assertEqual(self.build(scale=self.scale)["slides"][SLIDE_IDS.index("scope")]["type"], "facts")
                matching = copy.deepcopy(self.scale)
                matching["metadata"].update(start_period=start, end_period=end)
                included = [row for row in self.overview["periods"] if start <= row["period"] <= end]
                matching["metadata"]["counts"] = {"posts": len(included) * 1000, "comments": len(included) * 2000}
                matching["post_metrics"]["favorites"]["observed_count"] = len(included) * 1000 - 15
                result = self.build(scale=matching)
                self.assertTrue(result["slides"][SLIDE_IDS.index("scope")]["panels"])
                self.assertEqual(result["slides"][SLIDE_IDS.index("cities")]["panels"][0]["chart"], "city_totals")

    def test_scale_rejects_missing_or_incomplete_months_even_when_counts_match(self):
        for mode in ("gap", "incomplete", "last_incomplete"):
            with self.subTest(mode=mode):
                original = copy.deepcopy(self.overview)
                period = "2026-08" if mode == "last_incomplete" else "2026-07"
                if mode == "gap":
                    self.overview["periods"] = [row for row in self.overview["periods"] if row["period"] != period]
                else:
                    self.overview["metadata"]["incomplete_periods"].append(period)
                scale = copy.deepcopy(self.scale)
                scale["metadata"]["counts"] = {"posts": 196000, "comments": 392000}
                scale["post_metrics"]["favorites"]["observed_count"] = 195985
                result = self.build(scale=scale)
                self.assertEqual(result["slides"][SLIDE_IDS.index("scope")]["type"], "facts")
                self.assertIn("city_totals", result["charts"])
                self.overview = original

    def test_scale_does_not_fabricate_missing_thresholds_or_unknown_observations(self):
        for change in ("missing_threshold", "unknown_count", "too_many", "nonmonotone", "unknown_observed"):
            with self.subTest(change=change):
                scale = copy.deepcopy(self.scale)
                metric = scale["post_metrics"]["favorites"]
                if change == "missing_threshold":
                    metric["rows"].pop()
                elif change == "unknown_count":
                    metric["rows"][0]["count"] = -1
                elif change == "too_many":
                    metric["rows"][0]["count"] = metric["observed_count"] + 1
                elif change == "nonmonotone":
                    metric["rows"][0]["count"] = 200
                else:
                    metric["observed_count"] = None
                result = self.build(scale=scale)
                self.assertEqual(result["slides"][SLIDE_IDS.index("scope")]["type"], "facts")
                self.assertNotIn("panels", result["slides"][SLIDE_IDS.index("scope")])
                self.assertIn("city_totals", result["charts"])
        scale = copy.deepcopy(self.scale)
        for row in scale["post_metrics"]["favorites"]["rows"]:
            row["count"] = 0
        self.assertEqual(self.build(scale=scale)["charts"]["favorite_scale"]["series"][0]["values"], [0] * 4)

    def test_overview_distributions_keep_distinct_units_and_do_not_invent_missing_metrics(self):
        self.scale["post_metrics"]["clicks"] = {
            "observed_count": 197000,
            "rows": [{"threshold": t, "count": c} for t, c in ((5000, 500), (10000, 80), (50000, 7), (100000, 1))],
        }
        self.scale["post_metrics"]["thanks"] = copy.deepcopy(self.scale["post_metrics"]["favorites"])
        self.scale["comment_thanks"] = {
            "observed_count": 394000,
            "rows": [{"threshold": t, "count": c} for t, c in ((5, 300), (20, 50), (100, 10), (200, 2))],
        }
        self.scale["member_metrics"]["topics"] = {"observed_count": 200}
        self.scale["metadata"]["counts"]["nodes"] = 50
        result = self.build(scale=self.scale)
        scope = result["slides"][SLIDE_IDS.index("scope")]
        self.assertEqual([item["title"] for item in scope["panels"]], ["帖子浏览", "帖子收藏", "帖子感谢", "评论感谢"])
        self.assertIn("200 位用户发过帖", scope["summary"])
        self.assertIn("50 个节点", scope["summary"])
        self.assertEqual(result["charts"]["view_scale"]["series"][0]["values"], [500, 80, 7, 1])
        self.assertEqual(result["charts"]["comment_thanks_scale"]["unit"], "条评论")
        self.assertIn("394,000 条评论", scope["panels"][3]["detail"])
        self.scale["comment_thanks"]["observed_count"] += 1
        invalid = self.build(scale=self.scale)
        self.assertEqual(len(invalid["slides"][SLIDE_IDS.index("scope")]["panels"]), 3)
        self.assertNotIn("comment_thanks_scale", invalid["charts"])

    def test_chart_cases_require_a_direct_excerpt_and_stay_single_and_short(self):
        expected = {SLIDE_IDS.index("career"): (1052339, "但至少让孩子可以不当留守儿童"),
                    SLIDE_IDS.index("housing"): (985269, "25 号转完浮动调成 4.2 ，月省 1000")}
        for index, (topic_id, excerpt) in expected.items():
            self.add_post(topic_id, node="invest", content=f"<p>{excerpt}</p>")
        result = self.build()
        for index, (topic_id, excerpt) in expected.items():
            slide = result["slides"][index]
            self.assertEqual([post["id"] for post in slide["posts"]], [topic_id])
            self.assertEqual(slide["posts"][0]["excerpt"], excerpt)
            self.assertLessEqual(len(slide["posts"][0]["note"]), 40)
            self.assertNotIn("findings", slide)
        self.source.execute("UPDATE topic SET content='<p>unverified</p>'")
        self.assertTrue(all(not self.build()["slides"][index]["posts"] for index in expected))

    def test_posts_pages_have_no_extra_metric_or_finding_rows(self):
        self.write_codex_detail([["2025-01", "Codex", 20]])
        for index in map(SLIDE_IDS.index, ("favorites", "thanks")):
            slide = self.build()["slides"][index]
            self.assertEqual(slide["type"], "posts")
            self.assertNotIn("metrics", slide)
            self.assertNotIn("findings", slide)

    def test_post_evidence_preserves_verified_contiguous_text_and_existing_excerpt(self):
        expected = presentation_builder._POST_EVIDENCE
        for topic_id, paragraphs in expected.items():
            excerpt = presentation_builder._POST_CASES[topic_id][2]
            self.add_post(topic_id, content="<p>" + excerpt + "</p>"
                          + "".join(f"<p>{paragraph}</p>" for paragraph in paragraphs))
        result = self.build()
        posts = list(presentation_builder._load_posts(self.source, {"2025-01"}, {}).values())
        self.assertEqual({post["id"] for post in posts}, set(expected))
        for post in posts:
            self.assertEqual(post["excerpt"], presentation_builder._POST_CASES[post["id"]][2])
            self.assertEqual(post["evidence"], list(expected[post["id"]]))
            self.assertLessEqual(len(post["evidence"]), 2)
            self.assertLessEqual(len(post["excerpt"]) + sum(map(len, post["evidence"])), 100)
            self.assertIsNone(post["favorites"])
        self.assertEqual([slide["id"] for slide in result["slides"]], SLIDE_IDS)

    def test_post_evidence_is_verified_per_paragraph_without_fuzzy_or_cross_gap_matching(self):
        topic_id = 1031215
        excerpt = presentation_builder._POST_CASES[topic_id][2]
        first, second = presentation_builder._POST_EVIDENCE[topic_id]
        self.add_post(topic_id, content=f"<p>{excerpt}</p><p>{first}</p><p>{second}</p>")
        for body, expected in (
            (first, [first]),
            (first.replace("光纤盒", "光纤箱") + second, [second]),
            (first.replace("宽带", "宽 带"), None),
            (first[:10] + "<img src='photo.png'>" + first[10:], None),
            (f'<img alt="{first}">', None),
        ):
            with self.subTest(body=body):
                self.source.execute("UPDATE topic SET content=? WHERE id=?", (f"<p>{excerpt}</p><p>{body}</p>", topic_id))
                post = presentation_builder._load_posts(self.source, {"2025-01"}, {})[topic_id]
                self.assertEqual(post["excerpt"], excerpt)
                self.assertEqual(post.get("evidence"), expected)

    def test_post_evidence_skips_duplicates_and_over_budget_paragraphs_without_truncation(self):
        topic_id = 920519
        excerpt = presentation_builder._POST_CASES[topic_id][2]
        paragraphs = (excerpt, "长" * 101, "独立细节甲。", "独立细节甲。", "独立细节乙。", "独立细节丙。")
        self.add_post(topic_id, content="<p>" + "\n".join((excerpt, *paragraphs)) + "</p>")
        with patch.dict(presentation_builder._POST_EVIDENCE, {topic_id: paragraphs}):
            post = self.build()["slides"][SLIDE_IDS.index("ai-tools")]["posts"][0]
        self.assertEqual(post["evidence"], ["独立细节甲。", "独立细节乙。"])

    def test_post_evidence_does_not_leak_through_missing_source_or_cutoff(self):
        topic_id = 1022439
        excerpt = presentation_builder._POST_CASES[topic_id][2]
        evidence = presentation_builder._POST_EVIDENCE[topic_id][0]
        self.add_post(topic_id, period="2026-08", content=f"<p>{excerpt}</p><p>{evidence}</p>")
        self.assertTrue(self.build()["slides"][SLIDE_IDS.index("ai-tools")]["posts"][0]["evidence"])
        self.overview["metadata"]["default_end_period"] = "2026-07"
        self.assertEqual(self.build()["slides"][SLIDE_IDS.index("ai-tools")]["posts"], [])
        self.overview["metadata"]["default_end_period"] = "2026-08"
        self.overview["metadata"]["incomplete_periods"].append("2026-08")
        self.assertEqual(self.build()["slides"][SLIDE_IDS.index("ai-tools")]["posts"], [])
        self.overview["metadata"]["incomplete_periods"].remove("2026-08")
        self.source.execute("UPDATE topic SET content=?", (evidence,))
        self.assertNotIn("evidence", self.build()["slides"][SLIDE_IDS.index("ai-tools")]["posts"][0])
        missing = self.public_dir / "missing-evidence.sqlite"
        self.assertEqual(self.build(source=missing)["slides"][SLIDE_IDS.index("ai-tools")]["posts"], [])
        self.assertFalse(missing.exists())

    def test_apple_joke_requires_verified_linux_counterexample(self):
        self.add_post(335687, period="2017-01")
        self.add_comment(3972029, 335687, "<div>什么?v2 还有不用 Mac 的人?</div>", period="2017-01", thanks=-1)
        self.assertEqual(self.build()["slides"][SLIDE_IDS.index("topic-structure")]["comments"], [])
        self.add_comment(3972054, 335687, "平时用 linux ，偶尔才会切到 Windows 打把游戏放松下", period="2017-01")
        comment = self.build()["slides"][SLIDE_IDS.index("topic-structure")]["comments"][0]
        self.assertEqual(comment["label"], "调侃")
        self.assertIn("Linux", comment["note"])
        self.assertIn("设备持有率", comment["note"])
        self.assertIsNone(comment["thanks"])
        self.assertEqual(comment["date"], "2017-01-15")
        self.assertEqual(comment["url"], "https://www.v2ex.com/t/335687#r_3972029")
        self.source.execute("UPDATE comment SET content='not verified' WHERE id=3972054")
        self.assertEqual(self.build()["slides"][SLIDE_IDS.index("topic-structure")]["comments"], [])

    def test_comment_requires_expected_topic_parent_and_both_dates_in_window(self):
        excerpt = "刷五六分钟之后就开始干活，然后干活间隙再逛逛"
        self.add_post(1105715)
        self.add_post(999)
        self.add_comment(15806661, 1105715, f"<p>{excerpt}</p>")
        def selected():
            end = self.overview["metadata"]["default_end_period"]
            excluded = self.overview["metadata"]["incomplete_periods"]
            periods = {row["period"] for row in self.overview["periods"] if row["period"] <= end and row["period"] not in excluded}
            return presentation_builder._load_comments(self.source, periods)
        comment = selected()[15806661]
        self.assertEqual(comment["text"], excerpt)
        self.assertEqual(comment["thanks"], 0)
        for table, column, value, row_id in (
            ("comment", "topic_id", 999, 15806661),
            ("comment", "create_at", timestamp("2026-09"), 15806661),
            ("comment", "content", "[图片]", 15806661),
            ("topic", "create_at", timestamp("2026-09"), 1105715),
        ):
            with self.subTest(table=table, column=column):
                old = self.source.execute(f"SELECT {column} FROM {table} WHERE id=?", (row_id,)).fetchone()[0]
                self.source.execute(f"UPDATE {table} SET {column}=? WHERE id=?", (value, row_id))
                self.assertNotIn(15806661, selected())
                self.source.execute(f"UPDATE {table} SET {column}=? WHERE id=?", (old, row_id))
        self.overview["metadata"]["incomplete_periods"].append("2025-01")
        self.assertNotIn(15806661, selected())
        self.overview["metadata"]["incomplete_periods"].remove("2025-01")
        self.overview["metadata"]["default_end_period"] = "2024-12"
        self.assertNotIn(15806661, selected())

    def test_missing_comment_or_topic_tables_and_source_path_are_safe(self):
        self.source.execute("DROP TABLE comment")
        self.add_post(920519, content="群里有大佬基于新的 API 搞了个网站")
        result = self.build()
        self.assertTrue(result["slides"][SLIDE_IDS.index("ai-tools")]["posts"])
        for index in map(SLIDE_IDS.index, ("topic-structure", "comment-thanks")):
            self.assertEqual(result["slides"][index]["comments"], [])
        self.source.execute("DROP TABLE topic")
        self.assertEqual(len(self.build()["slides"]), 20)
        missing = self.public_dir / "missing-source.sqlite"
        result = self.build(source=missing)
        self.assertTrue(all(not slide.get("comments") for slide in result["slides"]))
        self.assertFalse(missing.exists())

    def test_rhythm_window_includes_17_but_not_18_and_excludes_weekends(self):
        self.overview["activity"] = [["2025-01", weekday, hour, 1, count] for weekday, hour, count in
                                     ((0, 8, 10), (0, 9, 20), (4, 17, 30), (4, 18, 10), (5, 10, 30))]
        result = self.build()
        self.assertEqual(result["rhythm"]["workday_comment_share"], 50)
        slide = result["slides"][SLIDE_IDS.index("rhythm")]
        self.assertNotIn("metrics", slide)
        self.assertEqual(result["charts"]["activity"]["kind"], "hourly_bars")
        self.assertIn("10:00–11:00", slide["summary"])
        self.assertNotIn("首回", json.dumps(slide, ensure_ascii=False))
        self.assertNotIn("超过一半", result["slides"][SLIDE_IDS.index("summary")]["takeaways"][1]["text"])
        self.overview["activity"] = []
        result = self.build()
        self.assertIsNone(result["rhythm"]["workday_comment_share"])
        self.assertEqual(result["slides"][SLIDE_IDS.index("rhythm")]["type"], "facts")
        self.assertNotIn("chart", result["slides"][SLIDE_IDS.index("rhythm")])

    def test_explore_takeaways_merge_dynamic_findings_with_existing_routes(self):
        for row in self.topics["group_rows"]:
            if row[1] == "apple" and row[0] >= "2021-09":
                row[2] = 40
        slide = self.build()["slides"][SLIDE_IDS.index("summary")]
        self.assertNotIn("metrics", slide)
        self.assertNotIn("chips", slide)
        self.assertEqual(slide["title"], "规模、关注点与互动，构成三条不同的线索")
        items = slide["takeaways"]
        self.assertEqual([item["number"] for item in items], ["01", "02", "03"])
        self.assertEqual([items[0]["value"], items[2]["value"]], ["3.00%", "未提供"])
        self.assertIn("2.00%→4.00%", items[0]["text"])
        for item, tab in zip(items, ("content", "overview", "engagement")):
            self.assertTrue({"number", "title", "text", "href", "link"} <= set(item))
            query = parse_qs(urlsplit(item["href"]).query)
            self.assertEqual(query["tab"], [tab])
            self.assertEqual(query["to"], ["2026-08"])
            self.assertIn("from", query)
        self.assertEqual(urlsplit(items[1]["href"]).fragment, "")
        self.assertEqual(urlsplit(items[2]["href"]).fragment, "engagement-posts")
        self.overview["metadata"]["default_end_period"] = "2015-12"
        text = self.build()["slides"][SLIDE_IDS.index("summary")]["takeaways"][0]["text"]
        self.assertNotIn("前后五年", text)

    def test_takeaways_keep_windowed_findings_without_repeating_charts(self):
        for row in self.topics["group_rows"]:
            if row[1] == "apple" and row[0] >= "2021-09":
                row[2] = 40
        self.engagement["top_posts"] = {
            "favorite_count": [{"id": i, "period": "2025-01", "value": 10} for i in range(20)],
            "thank_count": [{"id": i, "period": "2025-01", "value": 10} for i in range(15, 35)],
        }
        queries = []
        self.source.set_trace_callback(queries.append)
        result = self.build()
        self.assertEqual(len(queries), 2)
        items = result["slides"][SLIDE_IDS.index("summary")]["takeaways"]
        self.assertTrue(all("chart" not in item for item in items))
        self.assertIn("2.00%→4.00%", items[0]["text"])
        self.assertIn("邀请码公布前后", items[1]["text"])
        self.assertEqual(items[2]["value"], "5 / 20")
        self.overview["metadata"]["default_end_period"] = "2024-12"
        result = self.build()
        self.assertNotIn("takeaway_overlap", result["charts"])
        self.assertNotIn("chart", result["slides"][SLIDE_IDS.index("summary")]["takeaways"][2])
        self.assertEqual(result["slides"][SLIDE_IDS.index("summary")]["takeaways"][2]["value"], "未提供")

    def test_takeaway_charts_omit_incomplete_windows_and_missing_or_duplicate_rankings(self):
        self.overview["metadata"]["incomplete_periods"].append("2026-07")
        self.overview["activity"] = []
        duplicate_posts = [{"id": 1, "period": "2025-01", "value": 10}] * 20
        self.engagement["top_posts"] = {"favorite_count": duplicate_posts, "thank_count": duplicate_posts}
        result = self.build()
        self.assertTrue(all("chart" not in item for item in result["slides"][SLIDE_IDS.index("summary")]["takeaways"]))
        self.assertFalse(any(key.startswith("takeaway_") for key in result["charts"]))
        self.overview["metadata"]["default_end_period"] = "2015-12"
        self.assertNotIn("takeaway_apple", self.build()["charts"])
        self.overview["metadata"]["default_end_period"] = "2026-08"
        self.overview["metadata"]["incomplete_periods"].remove("2026-07")
        for length in (0, 19):
            self.engagement["top_posts"] = {
                "favorite_count": [{"id": i, "period": "2025-01", "value": 10} for i in range(length)],
                "thank_count": [{"id": i, "period": "2025-01", "value": 10} for i in range(20)],
            }
            self.assertNotIn("takeaway_overlap", self.build()["charts"])

    def test_new_story_structure_and_exploration_routes(self):
        result = self.build()
        finance = result["slides"][SLIDE_IDS.index("finance")]
        self.assertEqual([panel["chart"] for panel in finance["panels"]], ["finance", "finance_terms"])
        self.assertNotIn("加密", json.dumps(finance, ensure_ascii=False))
        self.assertEqual(len(result["charts"]["finance"]["series"]), 1)
        self.assertEqual(result["slides"][SLIDE_IDS.index("ai-tools")]["post_layout"], "strip")
        self.assertNotIn("posts", finance)
        explore = result["slides"][-1]
        self.assertEqual(explore["id"], "explore")
        for item, tab in zip(explore["takeaways"], ("content", "content", "engagement")):
            self.assertEqual(parse_qs(urlsplit(item["href"]).query)["tab"], [tab])
            self.assertNotIn("value", item)
        self.assertEqual(result["charts"]["activity"]["categories"], [f"{hour:02d}:00" for hour in range(24)])

    def test_full_build_publishes_scale_before_refreshing_observations(self):
        import analysis.build_analytics as builder

        tree = ast.parse(inspect.getsource(builder.build))
        publish = next(node for node in ast.walk(tree) if isinstance(node, ast.For)
                       and any(isinstance(item, ast.Constant) and item.value == "dynamic-scale-distribution.json"
                               for item in ast.walk(node.iter)))
        refresh = next(node for node in ast.walk(tree) if isinstance(node, ast.Call)
                       and isinstance(node.func, ast.Name) and node.func.id == "update_observations")
        self.assertLess(publish.end_lineno, refresh.lineno)

    def test_observation_output_calls_new_builder_with_six_existing_inputs(self):
        import analysis.build_analytics as builder

        self.engagement["top_posts"]["thank_count"] = [{
            "id": 473163, "title": "Survey", "value": 9, "node": "life", "create_at": timestamp("2025-01"),
        }]
        self.engagement["top_comments"] = [{"id": 1, "content": "A comment", "thank_count": 3}]
        with patch.object(builder, "build_presentation", return_value={"slides": []}) as presentation:
            result = builder.build_observation_output(self.overview, self.topics, self.nodes,
                                                      self.lifecycle, self.engagement, self.content_rows)
        presentation.assert_called_once_with(self.overview, self.topics, self.nodes, self.lifecycle,
                                             self.engagement, self.content_rows, builder.SOURCE_DB, builder.PUBLIC_DIR,
                                             scale=None)
        self.assertEqual(result["presentation"], {"slides": []})
        self.assertEqual(len(result["observations"]), 10)

    def test_update_observations_keeps_dynamic_json_export(self):
        import analysis.build_analytics as builder

        self.engagement["top_posts"]["thank_count"] = [{
            "id": 473163, "title": "Survey", "value": 9,
            "node": "life", "create_at": timestamp("2025-01"),
        }]
        self.engagement["top_comments"] = [{"id": 1, "content": "A comment", "thank_count": 3}]
        inputs = {
            "dynamic-overview.json": self.overview,
            "dynamic-lifecycle.json": self.lifecycle,
            "dynamic-engagement.json": self.engagement,
            "dynamic-scale-distribution.json": self.scale,
        }
        (self.public_dir / "dynamic-scale-distribution.json").write_text(json.dumps(self.scale), encoding="utf-8")
        with (
            patch.object(builder, "PUBLIC_DIR", self.public_dir),
            patch.object(builder, "SOURCE_DB", self.source),
            patch.object(builder, "load_json", side_effect=lambda path: inputs[path.name]),
            patch.object(builder, "load_dynamic_overview_activity", return_value={"rows": self.overview["activity"]}),
            patch.object(builder, "load_dynamic_topics", return_value=self.topics),
            patch.object(builder, "load_dynamic_nodes", return_value=self.nodes),
            patch.object(builder, "load_content_hotspot_rows", return_value=self.content_rows),
            patch.object(builder, "write_json") as write_json,
            patch.object(builder, "update_events"),
            patch.object(builder, "write_manifest") as manifest,
            patch("builtins.print"),
        ):
            builder.update_observations(write_component=False)
        write_json.assert_called_once()
        path, output = write_json.call_args.args
        self.assertEqual(path, self.public_dir / "dynamic-observations.json")
        self.assertEqual([slide["id"] for slide in output["presentation"]["slides"]], SLIDE_IDS)
        self.assertEqual(len(output["observations"]), 10)
        self.assertEqual(output["presentation"]["slides"][SLIDE_IDS.index("scope")]["panels"][0]["chart"], "favorite_scale")
        manifest.assert_not_called()


if __name__ == "__main__":
    unittest.main()
