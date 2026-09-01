import json
import tempfile
import unittest
from pathlib import Path

from scripts.audit_dashboard_data_duplication import audit_directory, file_group


class DashboardDuplicationAuditTest(unittest.TestCase):
    def test_audit_counts_repeated_stable_post_payloads(self):
        with tempfile.TemporaryDirectory() as directory:
            public = Path(directory)
            post = {
                "id": 10,
                "title": "A post",
                "node": "python",
                "author": "alice",
                "create_at": 100,
                "clicks": 20,
                "reply_count": 2,
                "favorite_count": 1,
                "thank_count": 0,
                "votes": 0,
                "score": 5,
            }
            (public / "dynamic-tag-period-posts-aa.json").write_text(
                json.dumps({"posts": {"Python": {"2026-01": [post]}}}),
                encoding="utf-8",
            )
            second = {**post, "score": 9, "period": "2026-01"}
            (public / "dynamic-content-period-posts-bb.json").write_text(
                json.dumps({"posts": {"开发": {"2026-01": [second]}}}),
                encoding="utf-8",
            )

            report = audit_directory(public)

            self.assertEqual(report["posts"]["occurrences"], 2)
            self.assertEqual(report["posts"]["unique_ids"], 1)
            self.assertEqual(report["posts"]["repeated_ids"], 1)
            self.assertGreater(
                report["posts"]["duplicated_stable_bytes_upper_bound"], 0
            )
            self.assertEqual(
                report["posts"][
                    "within_file_duplicated_stable_bytes_upper_bound"
                ],
                0,
            )
            self.assertEqual(report["posts"]["mismatched_stable_payload_ids"], [])

    def test_audit_counts_duplicates_within_one_file(self):
        with tempfile.TemporaryDirectory() as directory:
            public = Path(directory)
            post = {
                "id": 10,
                "title": "A post",
                "node": "python",
                "create_at": 100,
                "reply_count": 2,
            }
            (public / "dynamic-tag-period-posts-aa.json").write_text(
                json.dumps({"posts": {"Python": [post], "开发": [post]}}),
                encoding="utf-8",
            )

            report = audit_directory(public)

            self.assertGreater(
                report["posts"][
                    "within_file_duplicated_stable_bytes_upper_bound"
                ],
                0,
            )

    def test_audit_reports_conflicting_unknown_interaction_values(self):
        with tempfile.TemporaryDirectory() as directory:
            public = Path(directory)
            known = {
                "id": 10,
                "title": "A post",
                "node": "python",
                "create_at": 100,
                "reply_count": 2,
                "favorite_count": 0,
            }
            unknown = {**known, "favorite_count": -1}
            (public / "dynamic-tag-period-posts-aa.json").write_text(
                json.dumps({"posts": [known]}), encoding="utf-8"
            )
            (public / "dynamic-node-period-posts-aa.json").write_text(
                json.dumps({"posts": [unknown]}), encoding="utf-8"
            )

            report = audit_directory(public)

            self.assertEqual(
                report["posts"]["mismatched_stable_payload_ids"], [10]
            )

    def test_file_group_is_stable(self):
        self.assertEqual(
            file_group("dynamic-node-period-posts-aa.json"), "node-period-posts"
        )
        self.assertEqual(file_group("dynamic-overview.json"), "other")


if __name__ == "__main__":
    unittest.main()
