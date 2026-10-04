import json
import tempfile
import unittest
from pathlib import Path

from scripts.audit_public_access import classify
from scripts.compare_keyword_exports import compare
from scripts.evaluate_title_keywords import load_holdout
from scripts.sample_title_keyword_gold import append_approved, build_review_rows


class ReviewToolsTest(unittest.TestCase):
    def test_anonymous_access_does_not_confuse_errors_with_private_content(self):
        page = '<div class="header"><h1>Example</h1><a href="/go/qna">QNA</a></div><div class="topic_content">Hello</div>'
        self.assertEqual(classify(200, "https://www.v2ex.com/t/1", page), "anonymous_readable")
        self.assertEqual(classify(200, "https://www.v2ex.com/signin", '<form action="/signin"></form>'), "login_required")
        self.assertEqual(classify(403, "https://www.v2ex.com/t/1", page), "blocked_or_rate_limited")
        self.assertEqual(classify(404, "https://www.v2ex.com/t/1", ""), "unknown")
        self.assertEqual(classify(200, "https://www.v2ex.com/t/1", '<a href="/signin">Login</a>'), "unknown")

    def test_blind_holdout_requires_approval_and_cannot_be_used_for_tuning(self):
        rows = build_review_rows([{"title": "new title", "topic_id": 1}], None, holdout=True)
        self.assertIsNone(rows[0]["suggested"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gold, review = root / "gold.jsonl", root / "holdout.jsonl"
            gold.write_text(json.dumps({"title": "existing", "expected": []}) + "\n")
            review.write_text(json.dumps(rows[0]) + "\n")
            with self.assertRaises(ValueError):
                load_holdout(review, gold)
            rows[0].update(review_status="approved", expected=["AI"])
            review.write_text(json.dumps(rows[0]) + "\n")
            self.assertEqual(len(load_holdout(review, gold)), 1)
            with self.assertRaisesRegex(ValueError, "separate"):
                append_approved(review, gold)
            rows[0]["title"] = "existing"
            review.write_text(json.dumps(rows[0]) + "\n")
            with self.assertRaisesRegex(ValueError, "overlaps"):
                load_holdout(review, gold)

    def test_export_diff_separates_additions_removals_and_count_changes(self):
        before = {"metadata": {}, "period_totals": {"2024-01": 20}, "terms": {"AI": {"total": 10}, "old": {"total": 3}}}
        after = {"metadata": {}, "period_totals": {"2024-01": 25}, "terms": {"AI": {"total": 15}, "new": {"total": 4}}}
        report = compare(before, after)
        self.assertFalse(report["same_population"])
        self.assertEqual(report["added"], {"new": 4})
        self.assertEqual(report["removed"], {"old": 3})
        self.assertEqual(report["changed"][0]["delta"], 5)
