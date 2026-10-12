import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from scripts.verify_dashboard_release import assert_source_matches, verify_release


class ReleaseVerificationTest(unittest.TestCase):
    def test_refuses_synthetic_or_missing_database(self):
        with self.assertRaisesRegex(ValueError, "Synthetic"):
            assert_source_matches({"dataset_kind": "synthetic"}, Path("/does-not-exist"))
        with self.assertRaisesRegex(ValueError, "source database"):
            assert_source_matches({}, Path("/does-not-exist"))

    def test_refuses_stale_source_revisions(self):
        state = {"database_id": "db", "topic": {"revision": 1}, "comment": {"revision": 2}, "member": {"revision": 3}}
        manifest = {"full_build_state": {"tracking_database_id": "db", **{key: state[key] for key in ("topic", "comment", "member")}}}
        with patch.object(Path, "is_file", return_value=True), patch("scripts.verify_dashboard_release.sqlite3.connect"), patch("scripts.verify_dashboard_release.read_change_tracking_state", return_value=state), patch("scripts.verify_dashboard_release.collection_fingerprint", return_value=None):
            assert_source_matches(manifest, Path("test.sqlite"))
            manifest["full_build_state"]["comment"] = {"revision": 1}
            with self.assertRaisesRegex(ValueError, "stale for comment"):
                assert_source_matches(manifest, Path("test.sqlite"))

    def test_gate_checks_the_requested_dist_and_stops_at_failure(self):
        dist = MagicMock(spec=Path)
        dist.__str__.return_value = "/tmp/review-dist"
        (dist / "dynamic-manifest.json").read_text.return_value = "{}"
        with patch("scripts.verify_dashboard_release.assert_source_matches"), patch("scripts.verify_dashboard_release.subprocess.run", side_effect=RuntimeError("quality regression")) as run:
            with self.assertRaisesRegex(RuntimeError, "quality regression"):
                verify_release(dist, Path("test.sqlite"))
            self.assertEqual(run.call_count, 1)
            self.assertIn("--fail-on-regression", run.call_args.args[0])
