import json
import sqlite3
import unittest
from datetime import datetime

from analysis.builders.common import LOCAL_TIMEZONE
from scripts.sample_ai_coding_study import (
    build_corpus, candidate_tools, inspect_text, stratified_sample, stratum_for, validate_review,
)


def timestamp(month="2026-08"):
    return int(datetime.fromisoformat(month + "-15").replace(tzinfo=LOCAL_TIMEZONE).timestamp())


class AICodingStudyTest(unittest.TestCase):
    def setUp(self):
        self.source = sqlite3.connect(":memory:")
        self.tokens = sqlite3.connect(":memory:")
        self.addCleanup(self.source.close)
        self.addCleanup(self.tokens.close)
        self.source.execute("""CREATE TABLE topic (
            id INTEGER PRIMARY KEY, title TEXT, node TEXT, author TEXT, create_at INTEGER,
            clicks INTEGER, reply_count INTEGER, favorite_count INTEGER, thank_count INTEGER, content TEXT)""")
        self.source.execute("""CREATE TABLE comment (
            id INTEGER PRIMARY KEY, topic_id INTEGER, commenter TEXT, content TEXT,
            thank_count INTEGER, create_at INTEGER, no INTEGER)""")
        self.source.execute("CREATE INDEX ix_comment_topic_id ON comment(topic_id)")
        self.tokens.execute("CREATE TABLE title_tokens (topic_id INTEGER PRIMARY KEY, title TEXT)")

    def add_post(self, topic_id, title="Cursor 的实际体验", node="programmer", replies=2, favorites=-1,
                 month="2026-08", clicks=1, content="<p>工作中用了两个月</p>"):
        self.source.execute("INSERT INTO topic VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (topic_id, title, node, "author", timestamp(month), clicks, replies, favorites, -1, content))
        self.tokens.execute("INSERT INTO title_tokens VALUES (?, ?)", (topic_id, title))

    def test_candidates_are_retrieval_not_sentiment_and_models_need_coding_context(self):
        self.assertEqual(candidate_tools("为什么 Claude-Code 改坏了我的代码？"), ["Claude Code"])
        self.assertEqual(candidate_tools("Claude 看图体验"), [])
        self.assertEqual(candidate_tools("用 DeepSeek 重构服务"), ["通用 AI 编程"])
        self.assertEqual(candidate_tools("Cursor 与 GitHub Copilot"), ["GitHub Copilot", "Cursor"])
        self.assertEqual(candidate_tools("precursor"), [])
        self.assertEqual(candidate_tools("MongoDB 的 cursor 怎么工作"), [])
        self.assertEqual(candidate_tools("Windows 11 的 Copilot 怎么用"), [])
        self.assertEqual(candidate_tools("开发了一个 ChatGPT 小程序"), [])
        self.assertEqual(candidate_tools("用 Claude 三天开发了一个应用"), ["通用 AI 编程"])
        self.assertEqual(candidate_tools("cursor 的 bug 导致光标乱跳"), ["Cursor"])
        self.assertEqual(candidate_tools("有用 M1 Macbook Air 做开发的吗"), [])
        self.assertEqual(candidate_tools("使用 wolai 搭建博客"), [])
        self.assertEqual(candidate_tools("用 tailwind 写一个页面"), [])

    def test_prose_audit_preserves_original_but_separates_media_quotes_and_code(self):
        audit = inspect_text('<blockquote>很好用</blockquote><pre><code>raise Error()</code></pre><p>实际还要检查</p><img src="x">')
        self.assertEqual(audit["prose"], "实际还要检查")
        self.assertIn("很好用", audit["text"])
        self.assertTrue(audit["quoted_or_code"])
        self.assertEqual(audit["media"], 1)
        self.assertFalse(inspect_text('<img src="x">')["has_prose"])
        self.assertFalse(inspect_text("[图片]")["has_prose"])
        self.assertEqual(inspect_text("<script>alert(1)</script>正文")["prose"], "正文")
        self.assertEqual(inspect_text("> 引用他人\n我不同意")["prose"], "我不同意")
        self.assertTrue(inspect_text("示例 ```print(1)```")["quoted_or_code"])
        self.assertTrue(inspect_text("以下为文章翻译")["attribution_hint"])
        self.assertTrue(inspect_text("https://example.com/article")["link_only"])
        self.assertFalse(inspect_text("https://example.com/article")["has_prose"])

    def test_review_quotes_must_match_the_correct_thread_and_comment(self):
        self.add_post(1)
        records = build_corpus(self.source, self.tokens)[1]
        review = {"codebook": {"workflow": "test"}, "evidence": [
            {"topic_id": 1, "unit": "body", "quote": "工作中用了两个月", "code": "workflow"}]}
        self.assertEqual(validate_review(records, review)["evidence_checked_threads"], 1)
        review["evidence"][0]["quote"] = "并未出现的主张"
        with self.assertRaises(ValueError):
            validate_review(records, review)
        review["evidence"][0].update(unit="comment", comment_id=123)
        with self.assertRaises(ValueError):
            validate_review(records, review)

    def test_sampling_is_reproducible_covers_strata_and_records_design_weights(self):
        candidates = [{"id": i, "stratum": str(i % 7)} for i in range(101)]
        sample, strata = stratified_sample(candidates, 20, 123)
        self.assertEqual(len(sample), 20)
        self.assertEqual(sample, stratified_sample(list(reversed(candidates)), 20, 123)[0])
        self.assertEqual(len({row["id"] for row in sample}), 20)
        self.assertTrue(all(row["sample"] > 0 for row in strata))
        self.assertAlmostEqual(sum(row["design_weight"] for row in sample), 101)
        self.assertNotEqual(sample, stratified_sample(candidates, 20, 456)[0])
        with self.assertRaises(ValueError):
            stratified_sample(candidates, 2, 123)
        self.assertEqual(stratified_sample([], 20, 1), ([], []))

    def test_unknown_replies_have_own_stratum(self):
        self.assertEqual(stratum_for({"period": "2026-08", "node": "programmer", "replies": None}),
                         "2026-Q3/coding/unknown")

    def test_source_cutoff_exclusions_and_comments_are_thread_scoped(self):
        self.add_post(1)
        self.add_post(2, node="promotions")
        self.add_post(3, month="2026-09")
        self.add_post(4, clicks=-1)
        self.add_post(5, title="Claude Code", content='<img src="x">')
        self.add_post(6)
        self.source.execute("UPDATE topic SET title = '已经改过的无关标题' WHERE id = 6")
        for comment_id, topic_id, content, month in (
            (1, 1, "<p>需要审查改动</p>", "2026-08"), (2, 1, '[图片]', "2026-08"),
            (3, 1, "很顺手", "2026-09"), (4, 2, "不属于样本", "2026-08"),
        ):
            self.source.execute("INSERT INTO comment VALUES (?, ?, ?, ?, ?, ?, ?)",
                                (comment_id, topic_id, "author", content, -1, timestamp(month), comment_id))
        queries = []
        self.source.set_trace_callback(queries.append)
        summary, records, cases, candidates = build_corpus(self.source, self.tokens)
        self.assertEqual({row["id"] for row in records}, {1, 5})
        self.assertEqual(summary["sample_comments"], 2)
        self.assertEqual(summary["comments_with_prose"], 1)
        self.assertEqual(summary["body_with_prose"], 1)
        self.assertEqual(summary["fully_annotated_threads"], 0)
        self.assertEqual(cases, [])
        first = next(row for row in records if row["id"] == 1)
        self.assertEqual(first["coverage"]["invalid_or_after_cutoff"], 1)
        self.assertIsNone(first["comments"][0]["thanks"])
        self.assertTrue(first["comments"][0]["is_op"])
        self.assertTrue(all("WHERE topic_id =" in sql for sql in queries if "FROM comment" in sql))
        old_digest = first["source_digest"]
        self.source.execute("UPDATE comment SET content = '后补内容' WHERE id = 1")
        updated = build_corpus(self.source, self.tokens)[1]
        self.assertNotEqual(old_digest, next(row for row in updated if row["id"] == 1)["source_digest"])
        json.dumps(summary, allow_nan=False)

    def test_interaction_cases_never_change_random_sample_or_its_denominator(self):
        for i in range(1, 31):
            self.add_post(i, favorites=i)
        summary, sample, cases, _ = build_corpus(self.source, self.tokens, sample_size=5)
        self.assertEqual(summary["sample_count"], 5)
        self.assertTrue(cases)
        self.assertFalse({row["id"] for row in sample} & {row["id"] for row in cases})
        self.assertTrue(all(row["selection"] == "high_interaction_case" for row in cases))
        self.assertEqual(summary["sample_comments"], sum(len(row["comments"]) for row in sample))

    def test_author_supplements_preserve_undated_context_without_inventing_dates(self):
        self.add_post(1)
        self.source.execute("CREATE TABLE topic_supplement (topic_id INTEGER, content TEXT, create_at INTEGER)")
        self.source.executemany("INSERT INTO topic_supplement VALUES (?, ?, ?)", [
            (1, "后续澄清", timestamp()), (1, "时间丢失的补充", 0), (1, "窗口之后的补充", timestamp("2026-09")),
        ])
        summary, records, _, _ = build_corpus(self.source, self.tokens)
        self.assertEqual(summary["supplements"], 2)
        self.assertEqual(summary["undated_supplements"], 1)
        self.assertEqual(records[0]["supplements"][0]["temporal_status"], "undated")
        self.assertIsNone(records[0]["supplements"][0]["date"])


if __name__ == "__main__":
    unittest.main()
