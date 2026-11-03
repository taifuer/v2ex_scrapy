import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.audit_publication import audit_publication
from scripts.deploy_dashboard_remote import package_dist
from analysis.publication import connect_public_source
from analysis import build_analytics as analytics_builder

ROOT = Path(__file__).resolve().parent.parent


class FixturePipelineTest(unittest.TestCase):
    def test_full_pipeline_respects_exclusions_and_keeps_raw_facts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            policy = root / "policy.json"
            policy.write_text(json.dumps({"users": ["fixture_member_00"], "topic_ids": [2], "comment_ids": [13]}))
            destination = root / "fixture"
            with patch.dict(os.environ, {"V2EX_PUBLICATION_POLICY": str(policy)}):
                result = subprocess.run([
                    sys.executable, str(ROOT / "scripts/build_dashboard_fixture.py"),
                    "--output", str(destination),
                ], capture_output=True, text=True, timeout=120)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                report = audit_publication(destination / "public", destination / "facts.sqlite")
                self.assertEqual(report["violations"], [])
                self.assertGreater(report["checked_files"], 100)
                overview = json.loads((destination / "public/dynamic-overview.json").read_text())
                self.assertEqual(sum(row["topic_count"] for row in overview["periods"]), 2520 - 84 - 1)
                engagement_path = destination / "public/dynamic-engagement.json"
                full_rankings = json.loads(engagement_path.read_text())["top_posts"]
                with (
                    patch.object(analytics_builder, "PUBLIC_DIR", destination / "public"),
                    patch.object(analytics_builder, "SOURCE_DB", destination / "facts.sqlite"),
                    patch.object(analytics_builder, "write_manifest"),
                ):
                    analytics_builder.update_engagement_rankings()
                partial_rankings = json.loads(engagement_path.read_text())["top_posts"]
                self.assertEqual(set(full_rankings), set(analytics_builder.INTERACTION_POST_METRICS))
                for metric, posts in full_rankings.items():
                    self.assertEqual(
                        [(post["id"], post["value"]) for post in posts],
                        [(post["id"], post["value"]) for post in partial_rankings[metric]],
                    )
                source = connect_public_source(destination / "facts.sqlite")
                try:
                    profiles = [
                        profile
                        for path in (destination / "public").glob("dynamic-member-profiles-*.json")
                        for profile in json.loads(path.read_text()).get("profiles", {}).values()
                    ]
                    self.assertTrue(profiles)
                    for profile in profiles:
                        expected = source.execute(
                            "SELECT COUNT(*) FROM comment WHERE commenter = ?",
                            (profile["username"],),
                        ).fetchone()[0]
                        self.assertEqual(sum(row[2] for row in profile["periods"]), expected)
                finally:
                    source.close()
                with sqlite3.connect(destination / "facts.sqlite") as source:
                    self.assertEqual(source.execute("SELECT COUNT(*) FROM topic").fetchone()[0], 2520)
            (destination / "public/index.html").write_text("fixture")
            (destination / "public/assets").mkdir()
            with self.assertRaisesRegex(ValueError, "must not be deployed"):
                package_dist(destination / "public", root / "release.tar.gz")
            self.assertFalse((root / "release.tar.gz").exists())
