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
    "cover", "scope", "overview", "members", "topic-structure", "keyword-timeline",
    "ai-topics", "ai-tools", "ai-practice", "career", "finance", "housing",
    "subscriptions", "node-totals", "node-evolution", "favorites", "thanks",
    "rhythm", "conclusion", "explore",
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
                 "疫情", "M1", "MacBook", "远程", "ChatGPT", "OpenAI", "API", "模型", "额度")
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
        types = {"cover", "facts", "chart", "timeline", "posts", "conclusion", "explore"}
        chart_keys = set()
        for slide in result["slides"]:
            with self.subTest(slide=slide["id"]):
                self.assertIn(slide["type"], types)
                for key in ("chapter", "eyebrow", "title", "summary", "note"):
                    self.assertTrue(slide[key])
                self.assertLessEqual(len(slide.get("metrics", [])), 6 if slide["id"] == "scope" else 3)
                self.assertLessEqual(len(slide.get("posts", [])), 3 if slide["type"] == "posts" else 2)
                if slide["type"] == "chart":
                    chart_keys.add(slide["chart"])
                chart_keys.update(item["chart"] for item in slide.get("takeaways", []) if "chart" in item)
                chart_keys.update(item["chart"] for item in slide.get("panels", []))
        self.assertEqual(chart_keys, set(result["charts"]))
        for key, chart in result["charts"].items():
            with self.subTest(chart=key):
                self.assertIn(chart["kind"], {"line", "small_multiples", "grouped_bar", "horizontal_bar"})
                self.assertTrue(all(isinstance(category, str) for category in chart["categories"]))
                self.assertTrue(set(chart["partial"]) <= set(chart["categories"]))
                self.assertTrue(all(item["category"] in chart["categories"] for item in chart["annotations"]))
                for series in chart["series"]:
                    self.assertEqual(len(series["values"]), len(chart["categories"]))
                    self.assertTrue(all(isinstance(value, (float, int)) for value in series["values"]))
        self.assertEqual(result["charts"]["node_totals"]["category_kind"], "node")
        self.assertEqual(result["charts"]["node_evolution"]["series_kind"], "node")
        self.assertEqual(len(result["charts"]["topic_comparison"]["categories"]), 6)
        self.assertEqual(result["slides"][0]["title"], "V2EX 看板")
        self.assertEqual(len(result["slides"][19]["takeaways"]), 3)
        self.assertNotIn("chips", result["slides"][19])
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
        for key in ("overview", "career", "finance", "housing", "subscriptions", "node_evolution"):
            chart = result["charts"][key]
            self.assertEqual(chart["partial"], ["2010", "2026"])
            self.assertIn({"category": "2026", "label": "2026 年 1-2 月"}, chart["annotations"])
        self.assertEqual(result["charts"]["ai_tools"]["categories"][-1], "2026-02")
        codex = result["slides"][7]["metrics"][0]
        self.assertEqual(codex["value"], "4")
        self.assertEqual(codex["detail"], "2026 年 1-2 月")
        self.assertEqual(result["slides"][5]["milestones"][-1]["period"], "2026-01 至 2026-02")
        self.assertNotIn("截至 8 月", json.dumps(result, ensure_ascii=False))
        self.overview["metadata"]["default_end_period"] = "2025-12"
        self.assertEqual(self.build()["charts"]["overview"]["partial"], ["2010"])

    def test_explicit_incomplete_month_is_excluded_inside_cutoff(self):
        self.overview["metadata"]["incomplete_periods"].append("2026-07")
        result = self.build()
        self.assertNotIn("2026-07", result["charts"]["ai_tools"]["categories"])
        self.assertEqual(result["scope"]["topics"], result["scope"]["complete_months"] * 1000)
        self.assertEqual(result["slides"][7]["metrics"][0]["value"], "14")
        self.assertEqual(result["slides"][7]["metrics"][0]["detail"], "2026 年 7 个完整月份")

    def test_unknown_post_interactions_remain_null_and_zero_remains_zero(self):
        self.add_post(920519, content="<p>群里有大佬基于新的 API 搞了个网站</p>", thanks=0)
        self.add_post(1022439, clicks=0, favorites=12, thanks=3, replies=4)
        posts = self.build()["slides"][8]["posts"]
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
        self.assertEqual([post["id"] for post in self.build()["slides"][15]["posts"]], [931949])

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

    def test_finance_cases_must_match_existing_group_definition(self):
        self.add_post(969697, node="qna", tags=["基金"], content="可是波段做 T 的话，需要 1.5%的手续费； 显然不适合频繁买卖；")
        self.add_post(1117738, node="invest", content="还是专业的事交给专业的人, 抄作业得了")
        posts = self.build()["slides"][10]["posts"]
        self.assertEqual([post["id"] for post in posts], [1117738])
        self.assertIn("节点 invest", posts[0]["note"])
        self.source.execute("UPDATE topic SET node = 'qna', tag = '[\"基金\"]' WHERE id=1117738")
        self.assertIn("原始话题 基金", self.build()["slides"][10]["posts"][0]["note"])
        self.source.execute("UPDATE topic SET node = ?, tag = ?", ("programmer", "[]"))
        self.assertEqual(self.build()["slides"][10]["posts"], [])
        self.source.execute("UPDATE topic SET node = ?, tag = ?", ("promotions", '["基金"]'))
        self.assertEqual(self.build()["slides"][10]["posts"], [])

    def test_codex_cooccurrence_is_whole_period_not_recent_or_a_union(self):
        self.write_codex_detail([["2025-01", "Codex", 10], ["2026-08", "Codex", 20]])
        slide = self.build()["slides"][8]
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
                slide = self.build()["slides"][8]
                self.assertNotIn("metrics", slide)
                self.assertNotIn("共现", slide["summary"])
                self.assertIn("未展示", slide["note"])

    def test_selected_comment_requires_verified_prose_and_an_in_scope_date(self):
        self.add_post(437760, period="2018-03")
        self.add_comment(5432223, 437760, "我相信大多数 v 友遇到这种情况都会和我一样的做法 。谢谢大家。",
                         period="2018-03", thanks=306)
        comments = self.build()["slides"][16]["comments"]
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["thanks"], 306)
        self.assertEqual(comments[0]["url"], "https://www.v2ex.com/t/437760#r_5432223")
        self.assertEqual(comments[0]["date"], "2018-03-15")
        for column, value in (("content", "[图片]"), ("create_at", timestamp("2026-09")), ("topic_id", 999)):
            with self.subTest(column=column):
                original = self.source.execute(f"SELECT {column} FROM comment").fetchone()[0]
                self.source.execute(f"UPDATE comment SET {column}=?", (value,))
                self.assertEqual(self.build()["slides"][16]["comments"], [])
                self.source.execute(f"UPDATE comment SET {column}=?", (original,))
        self.source.execute("UPDATE comment SET thank_count=-1")
        self.assertIsNone(self.build()["slides"][16]["comments"][0]["thanks"])

    def test_annual_rates_and_timeline_counts_use_filtered_months(self):
        result = self.build()
        self.assertEqual(result["charts"]["career"]["series"][0]["values"][-1], 100)
        self.assertEqual(result["charts"]["finance"]["series"][0]["values"][-1], 2)
        self.assertEqual(result["charts"]["node_evolution"]["series"][0]["values"][-1], 30)
        milestones = result["slides"][5]["milestones"]
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
        def post(topic_id, period="2025-01", value=1):
            return {"id": topic_id, "period": period, "value": value, "title": "Post"}

        self.engagement["top_posts"] = {
            "favorite_count": [post(999, "2026-09"), post(998, value=-1)] +
                              [post(topic_id) for topic_id in range(1, 26)],
            "thank_count": [post(999, "2026-09")] +
                           [post(topic_id) for topic_id in range(15, 35)],
        }
        result = self.build()
        self.assertEqual(result["interaction"]["overlap"], 6)
        self.assertIn("Top 20 重合 6 帖", result["slides"][15]["summary"])
        self.assertEqual(result["slides"][19]["takeaways"][2]["value"], "6 / 20")
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
        slide = self.build()["slides"][3]
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
        self.assertEqual(result["slides"][1]["panels"][0]["chart"], "favorite_scale")
        self.assertEqual(result["slides"][1]["title"], "数据概览")
        self.assertEqual(result["slides"][18]["chart"], "commenter_scale")
        self.assertEqual(result["charts"]["favorite_scale"]["categories"],
                         [">=5 次", ">=20 次", ">=100 次", ">=500 次"])
        self.assertEqual(result["charts"]["favorite_scale"]["series"][0]["values"], [1000, 500, 100, 10])
        self.assertEqual(result["charts"]["commenter_scale"]["categories"],
                         [">=5 条评论", ">=100 条评论", ">=1,000 条评论", ">=10,000 条评论"])
        self.assertEqual(result["charts"]["commenter_scale"]["series"][0]["values"], [200, 50, 10, 1])
        self.assertIn("196,985", result["slides"][1]["panels"][0]["detail"])
        self.assertIn("450 位用户参与评论", result["slides"][1]["summary"])
        self.assertIn("450", result["slides"][18]["note"])
        self.assertIn("2.22%", result["slides"][18]["summary"])
        for index in (1, 18):
            self.assertLessEqual(len(result["slides"][index].get("metrics", [])), 2)
            self.assertNotIn("findings", result["slides"][index])

    def test_scale_is_loaded_read_only_from_public_json_or_explicit_input(self):
        path = self.public_dir / "dynamic-scale-distribution.json"
        path.write_text(json.dumps(self.scale), encoding="utf-8")
        before = path.read_bytes()
        original = copy.deepcopy(self.scale)
        self.assertEqual(self.build(), self.build(scale=self.scale))
        self.assertEqual(self.scale, original)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.build(scale={})["slides"][1]["type"], "facts")

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
                for index, chart in ((1, "favorite_scale"), (18, "commenter_scale")):
                    self.assertEqual(result["slides"][index]["type"], "facts")
                    self.assertIn("没有匹配", result["slides"][index]["summary"])
                    self.assertNotIn(chart, result["charts"])
                    self.assertNotIn("chart", result["slides"][index])
                    self.assertNotIn("metrics", result["slides"][index])

    def test_scale_cutoff_and_start_changes_cannot_relabel_full_history(self):
        for start, end in (("2010-04", "2026-07"), ("2016-09", "2026-08")):
            with self.subTest(start=start, end=end):
                self.overview["metadata"].update(start_period=start, default_end_period=end)
                self.assertEqual(self.build(scale=self.scale)["slides"][1]["type"], "facts")
                matching = copy.deepcopy(self.scale)
                matching["metadata"].update(start_period=start, end_period=end)
                included = [row for row in self.overview["periods"] if start <= row["period"] <= end]
                matching["metadata"]["counts"] = {"posts": len(included) * 1000, "comments": len(included) * 2000}
                matching["post_metrics"]["favorites"]["observed_count"] = len(included) * 1000 - 15
                result = self.build(scale=matching)
                self.assertTrue(result["slides"][1]["panels"])
                self.assertEqual(result["slides"][18]["type"], "chart")

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
                self.assertEqual(result["slides"][1]["type"], "facts")
                self.assertEqual(result["slides"][18]["type"], "facts")
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
                self.assertEqual(result["slides"][1]["type"], "facts")
                self.assertNotIn("panels", result["slides"][1])
                self.assertEqual(result["slides"][18]["type"], "chart")
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
        scope = result["slides"][1]
        self.assertEqual([item["title"] for item in scope["panels"]], ["帖子浏览", "帖子收藏", "帖子感谢", "评论感谢"])
        self.assertIn("200 位用户发过帖", scope["summary"])
        self.assertIn("50 个节点", scope["summary"])
        self.assertEqual(result["charts"]["view_scale"]["series"][0]["values"], [500, 80, 7, 1])
        self.assertEqual(result["charts"]["comment_thanks_scale"]["unit"], "条评论")
        self.assertIn("394,000 条评论", scope["panels"][3]["detail"])
        self.scale["comment_thanks"]["observed_count"] += 1
        invalid = self.build(scale=self.scale)
        self.assertEqual(len(invalid["slides"][1]["panels"]), 3)
        self.assertNotIn("comment_thanks_scale", invalid["charts"])

    def test_chart_cases_require_a_direct_excerpt_and_stay_single_and_short(self):
        expected = {9: (1052339, "但至少让孩子可以不当留守儿童"),
                    10: (1117738, "还是专业的事交给专业的人, 抄作业得了"),
                    11: (985269, "25 号转完浮动调成 4.2 ，月省 1000")}
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
        for index in (8, 15, 16):
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
        posts = [post for index in (8, 15, 16) for post in result["slides"][index]["posts"]]
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
                post = self.build()["slides"][15]["posts"][0]
                self.assertEqual(post["excerpt"], excerpt)
                self.assertEqual(post.get("evidence"), expected)

    def test_post_evidence_skips_duplicates_and_over_budget_paragraphs_without_truncation(self):
        topic_id = 920519
        excerpt = presentation_builder._POST_CASES[topic_id][2]
        paragraphs = (excerpt, "长" * 101, "独立细节甲。", "独立细节甲。", "独立细节乙。", "独立细节丙。")
        self.add_post(topic_id, content="<p>" + "\n".join((excerpt, *paragraphs)) + "</p>")
        with patch.dict(presentation_builder._POST_EVIDENCE, {topic_id: paragraphs}):
            post = self.build()["slides"][8]["posts"][0]
        self.assertEqual(post["evidence"], ["独立细节甲。", "独立细节乙。"])

    def test_post_evidence_does_not_leak_through_missing_source_or_cutoff(self):
        topic_id = 1022439
        excerpt = presentation_builder._POST_CASES[topic_id][2]
        evidence = presentation_builder._POST_EVIDENCE[topic_id][0]
        self.add_post(topic_id, period="2026-08", content=f"<p>{excerpt}</p><p>{evidence}</p>")
        self.assertTrue(self.build()["slides"][8]["posts"][0]["evidence"])
        self.overview["metadata"]["default_end_period"] = "2026-07"
        self.assertEqual(self.build()["slides"][8]["posts"], [])
        self.overview["metadata"]["default_end_period"] = "2026-08"
        self.overview["metadata"]["incomplete_periods"].append("2026-08")
        self.assertEqual(self.build()["slides"][8]["posts"], [])
        self.overview["metadata"]["incomplete_periods"].remove("2026-08")
        self.source.execute("UPDATE topic SET content=?", (evidence,))
        self.assertNotIn("evidence", self.build()["slides"][8]["posts"][0])
        missing = self.public_dir / "missing-evidence.sqlite"
        self.assertEqual(self.build(source=missing)["slides"][8]["posts"], [])
        self.assertFalse(missing.exists())

    def test_apple_joke_requires_verified_linux_counterexample(self):
        self.add_post(335687, period="2017-01")
        self.add_comment(3972029, 335687, "<div>什么?v2 还有不用 Mac 的人?</div>", period="2017-01", thanks=-1)
        self.assertEqual(self.build()["slides"][4]["comments"], [])
        self.add_comment(3972054, 335687, "平时用 linux ，偶尔才会切到 Windows 打把游戏放松下", period="2017-01")
        comment = self.build()["slides"][4]["comments"][0]
        self.assertEqual(comment["label"], "调侃")
        self.assertIn("Linux", comment["note"])
        self.assertIn("设备持有率", comment["note"])
        self.assertIsNone(comment["thanks"])
        self.assertEqual(comment["date"], "2017-01-15")
        self.assertEqual(comment["url"], "https://www.v2ex.com/t/335687#r_3972029")
        self.source.execute("UPDATE comment SET content='not verified' WHERE id=3972054")
        self.assertEqual(self.build()["slides"][4]["comments"], [])

    def test_comment_requires_expected_topic_parent_and_both_dates_in_window(self):
        excerpt = "刷五六分钟之后就开始干活，然后干活间隙再逛逛"
        self.add_post(1105715)
        self.add_post(999)
        self.add_comment(15806661, 1105715, f"<p>{excerpt}</p>")
        comment = self.build()["slides"][17]["comments"][0]
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
                self.assertEqual(self.build()["slides"][17]["comments"], [])
                self.source.execute(f"UPDATE {table} SET {column}=? WHERE id=?", (old, row_id))
        self.overview["metadata"]["incomplete_periods"].append("2025-01")
        self.assertEqual(self.build()["slides"][17]["comments"], [])
        self.overview["metadata"]["incomplete_periods"].remove("2025-01")
        self.overview["metadata"]["default_end_period"] = "2024-12"
        self.assertEqual(self.build()["slides"][17]["comments"], [])

    def test_missing_comment_or_topic_tables_and_source_path_are_safe(self):
        self.source.execute("DROP TABLE comment")
        self.add_post(920519, content="群里有大佬基于新的 API 搞了个网站")
        result = self.build()
        self.assertTrue(result["slides"][8]["posts"])
        for index in (4, 16, 17):
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
        slide = result["slides"][17]
        self.assertEqual(slide["metrics"][0]["value"], "50.0%")
        self.assertIn("09:00–18:00", slide["summary"])
        self.assertNotIn("首回", json.dumps(slide, ensure_ascii=False))
        self.assertNotIn("超过一半", result["slides"][19]["takeaways"][1]["text"])
        self.overview["activity"] = []
        result = self.build()
        self.assertIsNone(result["rhythm"]["workday_comment_share"])
        self.assertEqual(result["slides"][17]["type"], "facts")
        self.assertEqual(result["slides"][19]["takeaways"][1]["value"], "未提供")

    def test_explore_takeaways_merge_dynamic_findings_with_existing_routes(self):
        for row in self.topics["group_rows"]:
            if row[1] == "apple" and row[0] >= "2021-09":
                row[2] = 40
        slide = self.build()["slides"][19]
        self.assertNotIn("metrics", slide)
        self.assertNotIn("chips", slide)
        self.assertEqual(slide["title"], "熟悉的社区印象，也能回到数据里看")
        items = slide["takeaways"]
        self.assertEqual([item["number"] for item in items], ["01", "02", "03"])
        self.assertEqual([item["value"] for item in items], ["3.00%", "60.0%", "未提供"])
        self.assertIn("2.00%→4.00%", items[0]["text"])
        for item, tab in zip(items, ("content", "overview", "engagement")):
            self.assertEqual(set(item) - {"chart"}, {"number", "title", "text", "value", "href", "link"})
            query = parse_qs(urlsplit(item["href"]).query)
            self.assertEqual(query["tab"], [tab])
            self.assertEqual(query["to"], ["2026-08"])
            self.assertIn("from", query)
        self.assertEqual(urlsplit(items[1]["href"]).fragment, "activity-heatmap")
        self.assertEqual(urlsplit(items[2]["href"]).fragment, "engagement-posts")
        self.overview["metadata"]["default_end_period"] = "2015-12"
        text = self.build()["slides"][19]["takeaways"][0]["text"]
        self.assertNotIn("前后五年", text)

    def test_takeaway_charts_use_existing_windowed_rates_and_top_twenty_sets(self):
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
        self.assertEqual([item["chart"] for item in result["slides"][19]["takeaways"]],
                         ["takeaway_apple", "takeaway_daytime", "takeaway_overlap"])
        for key, values in (("takeaway_apple", [2, 4]), ("takeaway_daytime", [60, 40]),
                            ("takeaway_overlap", [15, 5, 15])):
            with self.subTest(chart=key):
                chart = result["charts"][key]
                self.assertEqual(chart["kind"], "horizontal_bar")
                self.assertEqual(chart["series"][0]["values"], values)
                self.assertEqual(len(chart["categories"]), len(values))
        chart = result["charts"]["takeaway_overlap"]
        self.assertEqual(chart["categories"], ["仅收藏榜", "两榜重合", "仅感谢榜"])
        self.assertEqual(chart["unit"], "帖")
        self.assertEqual(sum(chart["series"][0]["values"]), 35)
        self.overview["metadata"]["default_end_period"] = "2024-12"
        result = self.build()
        self.assertNotIn("takeaway_overlap", result["charts"])
        self.assertNotIn("chart", result["slides"][19]["takeaways"][2])
        self.assertLess(result["charts"]["takeaway_apple"]["series"][0]["values"][1], 4)

    def test_takeaway_charts_omit_incomplete_windows_and_missing_or_duplicate_rankings(self):
        self.overview["metadata"]["incomplete_periods"].append("2026-07")
        self.overview["activity"] = []
        duplicate_posts = [{"id": 1, "period": "2025-01", "value": 10}] * 20
        self.engagement["top_posts"] = {"favorite_count": duplicate_posts, "thank_count": duplicate_posts}
        result = self.build()
        self.assertTrue(all("chart" not in item for item in result["slides"][19]["takeaways"]))
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
        self.assertEqual(output["presentation"]["slides"][1]["panels"][0]["chart"], "favorite_scale")
        manifest.assert_not_called()


if __name__ == "__main__":
    unittest.main()
