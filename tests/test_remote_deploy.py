import tarfile
import tempfile
import unittest
from pathlib import Path

from scripts.deploy_dashboard_remote import package_dist, validate_arguments


class RemoteDeployTest(unittest.TestCase):
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
