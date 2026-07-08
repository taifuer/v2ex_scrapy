import unittest

from analysis.build_analytics import (
    canonical_tag,
    comment_age_bucket,
    comment_text,
    first_reply_bucket,
    matches_group,
    normalize_tags,
    title_tokens,
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

    def test_title_tokens_keep_technical_terms_and_filter_noise(self):
        synonyms = {
            "chatgpt": "ChatGPT",
            "claude code": "Claude Code",
            "人工智能": "AI",
        }
        stopwords = {"请问", "大佬", "有没有"}

        tokens = title_tokens("请问大佬 Claude Code 和 ChatGPT 做人工智能 Agent 有没有推荐？", synonyms, stopwords)

        self.assertIn("Claude Code", tokens)
        self.assertIn("ChatGPT", tokens)
        self.assertIn("AI", tokens)
        self.assertIn("Agent", tokens)
        self.assertNotIn("请问", tokens)
        self.assertNotIn("大佬", tokens)


if __name__ == "__main__":
    unittest.main()
