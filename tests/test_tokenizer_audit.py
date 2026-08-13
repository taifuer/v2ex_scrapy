import unittest
from pathlib import Path

from analysis.content_hotspots import TitleTokenizer
from scripts.audit_title_tokenizers import compare_backend


class TokenizerAuditTest(unittest.TestCase):
    def test_separates_missing_terms_from_current_stopwords(self):
        tokenizer = TitleTokenizer(Path(__file__).resolve().parent.parent / "analysis")
        rows = [{"id": 1, "title": "AI 工具加入新实体", "period": "2026-07"}]

        report = compare_backend(
            rows,
            [["人工智能", "工具", "加入", "新实体"]],
            tokenizer,
            minimum_count=1,
            candidate_limit=10,
        )

        candidates = {item["term"] for item in report["candidate_terms"]}
        filtered = {item["term"] for item in report["filtered_term_candidates"]}
        self.assertIn("新实体", candidates)
        self.assertIn("工具", filtered)
        self.assertNotIn("人工智能", candidates)


if __name__ == "__main__":
    unittest.main()
