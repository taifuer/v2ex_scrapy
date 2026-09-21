import unittest
from pathlib import Path

from analysis.content_hotspots import (
    TitleTokenizer,
    _content_group_config,
    _normalize_tags,
    _tag_config,
    content_group_matches,
)
from scripts.evaluate_title_keywords import evaluate, load_gold


ROOT = Path(__file__).resolve().parent.parent


class TitleKeywordQualityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tokenizer = TitleTokenizer(ROOT / "analysis")

    def test_reviewed_regression_corpus(self):
        report = evaluate(
            load_gold(ROOT / "analysis" / "title_keyword_gold.jsonl"),
            self.tokenizer,
        )

        self.assertGreaterEqual(report["precision"], 0.97)
        self.assertGreaterEqual(report["recall"], 0.95)
        self.assertGreaterEqual(report["exact_rate"], 0.90)
        self.assertEqual(report["constraint_pass_rate"], 1.0)

    def test_unicode_normalization_and_reviewed_phrase_protection(self):
        tokens = self.tokenizer.tokenize(
            "ＧＰＴ－４、模型上下文协议与向量数据库、创业板与科创板"
        )

        self.assertTrue(
            {"GPT-4", "模型上下文协议", "向量数据库", "创业板", "科创板"}
            <= tokens
        )

    def test_life_keywords_and_synonyms_are_recognized(self):
        cases = [
            ("相亲聊到彩礼、婚礼和婚姻", {"相亲", "彩礼", "婚礼", "婚姻"}),
            ("异地恋结婚后请月嫂，考虑学区房", {"异地恋", "结婚", "月嫂", "学区房"}),
            ("女朋友和女友、男朋友和男友都在谈恋爱", {"女友", "男友", "恋爱"}),
            ("公积金提前还贷还是提前还款", {"公积金", "提前还贷", "提前还款"}),
            ("焦虑、失眠和抑郁症的心理咨询", {"焦虑", "失眠", "抑郁症", "心理咨询"}),
        ]
        for title, required in cases:
            with self.subTest(title=title):
                self.assertTrue(required <= self.tokenizer.tokenize(title))

    def test_related_topics_use_selected_canonical_names_and_deduplicate(self):
        selected = {"Git", "offer", "女友"}
        synonyms, stopwords = _tag_config(ROOT / "analysis", selected)
        tags = _normalize_tags(
            '["git", "GIT", "Offer", "OFFER", "女朋友", "女友", "pro"]',
            synonyms,
            stopwords,
        )
        self.assertEqual(tags & selected, selected)
        self.assertEqual(len(tags), 3)

    def test_life_keywords_do_not_match_across_word_boundaries(self):
        cases = [
            ("新婚礼物怎么选？", {"婚礼"}),
            ("结婚礼金和新婚礼物", {"婚礼"}),
            ("部分手游登录失败", {"分手"}),
            ("区分手机和电脑的请求", {"分手"}),
            ("医保积分手册", {"分手"}),
            ("能不能利用 12306 给人代买车票来牟利", {"买车"}),
            ("光环新网机房租用一个机柜", {"房租"}),
            ("国际宠物业高峰论坛", {"物业"}),
        ]
        for title, forbidden in cases:
            with self.subTest(title=title):
                self.assertFalse(forbidden & self.tokenizer.tokenize(title))
        self.assertIn("分手", self.tokenizer.tokenize("分手了，部分手游也不想玩了"))

    def test_ambiguous_words_do_not_trigger_life_content_groups(self):
        _, term_groups = _content_group_config(ROOT / "analysis")
        for title in ["对象存储", "Mac 睡眠后无法唤醒", "旧显卡退休", "软件项目烂尾", "AI 伴侣"]:
            with self.subTest(title=title):
                groups = content_group_matches(self.tokenizer.tokenize(title), term_groups)
                self.assertNotIn("relationships-family", groups)
                self.assertNotIn("health-wellbeing", groups)

    def test_marriage_and_health_concepts_remain_distinct(self):
        self.assertEqual(
            self.tokenizer.tokenize("彩礼 婚礼 婚姻 结婚"),
            {"彩礼", "婚礼", "婚姻", "结婚"},
        )
        self.assertEqual(self.tokenizer.tokenize("抑郁 抑郁症"), {"抑郁", "抑郁症"})
        for compound, broader in [
            ("跑步机", "跑步"), ("焦虑症", "焦虑"),
            ("前女友", "女友"), ("前男友", "男友"),
            ("单身公寓", "单身"),
        ]:
            with self.subTest(compound=compound):
                tokens = self.tokenizer.tokenize(compound)
                self.assertIn(compound, tokens)
                self.assertNotIn(broader, tokens)


if __name__ == "__main__":
    unittest.main()
