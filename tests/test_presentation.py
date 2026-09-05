import copy
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from analysis.builders.common import LOCAL_TIMEZONE
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

    def build(self, source=None):
        return build_presentation(self.overview, self.topics, self.nodes, self.lifecycle,
                                  self.engagement, self.content_rows,
                                  self.source if source is None else source, self.public_dir)

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

    def test_twenty_ordered_slides_and_chart_contract(self):
        result = self.build()
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
        self.assertEqual(len(result["slides"][18]["takeaways"]), 3)
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
        self.assertEqual(len(queries), 1)
        self.assertIn("FROM topic WHERE id IN (", queries[0])
        self.assertNotIn("GROUP BY", queries[0])
        self.assertNotIn("JOIN", queries[0])
        self.assertNotIn("966243", queries[0])
        self.assertNotIn("1197162", queries[0])

    def test_finance_cases_must_match_existing_group_definition(self):
        self.add_post(969697, node="qna", tags=["基金"], content="可是波段做 T 的话，需要 1.5%的手续费； 显然不适合频繁买卖；")
        self.add_post(1117738, node="invest", content="还是专业的事交给专业的人, 抄作业得了")
        posts = self.build()["slides"][10]["posts"]
        self.assertEqual([post["id"] for post in posts], [969697, 1117738])
        self.assertIn("原始话题 基金", posts[0]["note"])
        self.assertIn("节点 invest", posts[1]["note"])
        self.source.execute("UPDATE topic SET node = ?, tag = ?", ("programmer", "[]"))
        self.assertEqual(self.build()["slides"][10]["posts"], [])
        self.source.execute("UPDATE topic SET node = ?, tag = ?", ("promotions", '["基金"]'))
        self.assertEqual(self.build()["slides"][10]["posts"], [])

    def test_codex_cooccurrence_is_whole_period_not_recent_or_a_union(self):
        self.write_codex_detail([["2025-01", "Codex", 10], ["2026-08", "Codex", 20]])
        slide = self.build()["slides"][8]
        self.assertEqual([metric["value"] for metric in slide["metrics"]], ["7", "5"])
        self.assertTrue(all("全期 30" in metric["detail"] for metric in slide["metrics"]))
        self.assertIn("未计算", slide["note"])
        self.assertEqual(len(list(self.public_dir.glob("*.json"))), 2)

    def test_cooccurrence_outside_window_or_inconsistent_total_is_not_relabelled(self):
        for rows, total in (([["2026-08", "Codex", 20], ["2026-09", "Codex", 999]], None),
                            ([["2010-03", "Codex", 10], ["2026-08", "Codex", 20]], None),
                            ([["2026-08", "Codex", 20]], 999)):
            with self.subTest(rows=rows, total=total):
                self.write_codex_detail(rows, total)
                slide = self.build()["slides"][8]
                self.assertEqual(slide["metrics"], [])
                self.assertIn("未展示", slide["note"])

    def test_selected_comment_requires_verified_prose_and_an_in_scope_date(self):
        self.engagement["top_comments"] = [{
            "id": 5432223, "topic_id": 437760, "commenter": "liuweisj",
            "create_at": timestamp("2018-03"), "thank_count": 306,
            "content": "我相信大多数 v 友遇到这种情况都会和我一样的做法 。谢谢大家。",
        }]
        comments = self.build()["slides"][16]["comments"]
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["thanks"], 306)
        self.assertEqual(comments[0]["url"], "https://www.v2ex.com/t/437760#r_5432223")
        self.assertEqual(comments[0]["date"], "2018-03-15")
        for changes in ({"content": "[图片]"}, {"create_at": timestamp("2026-09")}, {"thank_count": -1}):
            with self.subTest(changes=changes):
                original = self.engagement["top_comments"][0].copy()
                self.engagement["top_comments"][0].update(changes)
                self.assertEqual(self.build()["slides"][16]["comments"], [])
                self.engagement["top_comments"][0] = original

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
        metric = self.build()["slides"][2]["metrics"][0]
        self.assertEqual(metric["value"], "2,000")
        self.assertEqual(metric["detail"], "2018 全年")

    def test_overview_peak_uses_unrounded_monthly_average(self):
        for row in self.overview["periods"]:
            if row["period"] == "2018-01":
                row["topic_count"] += 1
        metric = self.build()["slides"][2]["metrics"][0]
        self.assertEqual(metric["value"], "1,000")
        self.assertEqual(metric["detail"], "2018 全年")

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
        self.assertEqual(result["slides"][15]["metrics"][0]["value"], "6 / 20")
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
                                             self.engagement, self.content_rows, builder.SOURCE_DB, builder.PUBLIC_DIR)
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
        }
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
        manifest.assert_not_called()


if __name__ == "__main__":
    unittest.main()
