import unittest
from pathlib import Path

from analysis.content_hotspots import TitleTokenizer
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


if __name__ == "__main__":
    unittest.main()
