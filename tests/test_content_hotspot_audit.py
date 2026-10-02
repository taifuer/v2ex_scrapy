import json
import tempfile
import unittest
from pathlib import Path

from analysis.content_hotspot_audit import coverage_text, markdown_text


class ContentHotspotAuditTest(unittest.TestCase):
    def test_complete_and_legacy_coverage(self):
        metadata = {"default_end_period": "2026-08"}
        expected = "数据截至 2026-08，共审查 1 个标题关键词。"
        self.assertEqual(coverage_text(metadata, 1), expected)
        metadata["preview_end_period"] = "2026-08"
        self.assertEqual(coverage_text(metadata, 1), expected)

    def test_preview_coverage_matches_all_period_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            public = Path(directory)
            index = {
                "metadata": {
                    "default_end_period": "2026-08",
                    "preview_end_period": "2026-09",
                },
                "terms": {"工程师": {"bucket": "00"}},
            }
            detail = {
                "term": "工程师", "total": 168, "author_total": 100,
                "node_total": 3, "authors": [["example", 1]],
                "nodes": [["jobs", 150]], "posts": [],
                "rows": [["2026-08", "工程师", 100], ["2026-09", "工程师", 68]],
            }
            (public / "dynamic-content-hotspots-index.json").write_text(json.dumps(index))
            (public / "dynamic-content-term-details-00.json").write_text(
                json.dumps({"details": {"工程师": detail}})
            )
            report = markdown_text(public)
        self.assertIn("数据截至 2026-09（含未完整月份），默认完整月截至 2026-08", report)
        self.assertIn("| 工程师 | 168 |", report)
        self.assertNotIn("数据截至 2026-08，", report)


if __name__ == "__main__":
    unittest.main()
