import tarfile
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.deploy_dashboard_remote import RETAIN_ASSETS_SCRIPT, package_dist, validate_arguments


class RemoteDeployTest(unittest.TestCase):
    def test_keeps_only_previous_release_assets_without_overwriting_current_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / "dist" / "assets"
            new = root / "staging" / "dist" / "assets"
            old.mkdir(parents=True)
            new.mkdir(parents=True)
            for name in ("previous.js", "older.js", "shared.css", "app-release.json"):
                (old / name).write_text("previous", encoding="utf-8")
            (new / "shared.css").write_text("current", encoding="utf-8")
            (new / "app-release.json").write_text("current release", encoding="utf-8")
            (root / "dist" / "assets-current.txt").write_text(
                "assets/previous.js\nassets/shared.css\nassets/../../secret\nassets/app-release.json\n",
                encoding="utf-8",
            )
            subprocess.run(
                ["bash", "-eu", "-c", RETAIN_ASSETS_SCRIPT],
                env={"root": str(root), "staging": str(root / "staging"), "PS1": ""},
                check=True,
            )
            self.assertTrue((new / "previous.js").exists())
            self.assertFalse((new / "older.js").exists())
            self.assertEqual((new / "shared.css").read_text(), "current")
            self.assertEqual((new / "app-release.json").read_text(), "current release")

    def test_retains_assets_on_first_upgrade_from_legacy_dist(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "dist" / "assets").mkdir(parents=True)
            (root / "staging" / "dist" / "assets").mkdir(parents=True)
            (root / "dist" / "assets" / "old.js").write_text("old", encoding="utf-8")
            subprocess.run(
                ["bash", "-eu", "-c", RETAIN_ASSETS_SCRIPT],
                env={"root": str(root), "staging": str(root / "staging"), "PS1": ""},
                check=True,
            )
            self.assertTrue((root / "staging" / "dist" / "assets" / "old.js").exists())

    def test_packages_only_the_built_dist_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dist = root / "dist"
            (dist / "assets").mkdir(parents=True)
            (dist / "index.html").write_text("index", encoding="utf-8")
            (dist / "dynamic-manifest.json").write_text("{}", encoding="utf-8")
            (dist / "assets" / "app.js").write_text("app", encoding="utf-8")

            result = package_dist(dist, root / "bundle.tar.gz")

            self.assertEqual(len(result["sha256"]), 64)
            with tarfile.open(result["archive"], "r:gz") as archive:
                names = set(archive.getnames())
            self.assertIn("dist/index.html", names)
            self.assertIn("dist/dynamic-manifest.json", names)
            self.assertIn("dist/assets/app.js", names)

    def test_rejects_shell_metacharacters_in_remote_arguments(self):
        validate_arguments(
            "root@example.com",
            "/srv/v2ex-dashboard",
            "abc123",
            "docker-compose.override.yml",
        )
        with self.assertRaises(ValueError):
            validate_arguments(
                "root@example.com;false",
                "/srv/v2ex-dashboard",
                "abc123",
                "docker-compose.override.yml",
            )
        with self.assertRaises(ValueError):
            validate_arguments(
                "root@example.com",
                "/srv/../etc",
                "abc123",
                "docker-compose.override.yml",
            )
        with self.assertRaises(ValueError):
            validate_arguments(
                "root@example.com",
                "/srv/v2ex-dashboard",
                "abc123",
                "docker-compose.override.yml",
                "http://127.0.0.1:3090/;false",
            )


if __name__ == "__main__":
    unittest.main()
