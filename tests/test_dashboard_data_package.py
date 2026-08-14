import json
import tempfile
import unittest
from pathlib import Path

from scripts.install_dashboard_data import install_dashboard_data
from scripts.package_dashboard_data import package_dashboard_data


class DashboardDataPackageTest(unittest.TestCase):
    def test_packages_and_installs_verified_dynamic_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            public = root / "public"
            public.mkdir()
            payload = public / "dynamic-overview.json"
            payload.write_text('{"periods":[]}', encoding="utf-8")
            manifest = {
                "schema_version": 32,
                "generated_at": "2026-08-14T00:00:00+08:00",
                "files": {payload.name: payload.stat().st_size},
                "full_build_state": {"analysis": {"complete_through": "2026-07"}},
            }
            manifest_path = public / "dynamic-manifest.json"
            manifest_path.write_text(
                json.dumps(manifest, separators=(",", ":")), encoding="utf-8"
            )

            archive = root / "dashboard-data.tar.gz"
            result = package_dashboard_data(public, archive)
            target = root / "installed"
            target.mkdir()
            stale_gzip = target / "dynamic-stale.json.gz"
            stale_gzip.write_bytes(b"old")
            installed = install_dashboard_data(archive, target)

            self.assertEqual(result["schema_version"], 32)
            self.assertEqual(installed["complete_through"], "2026-07")
            self.assertEqual(
                (target / payload.name).read_text(encoding="utf-8"),
                payload.read_text(encoding="utf-8"),
            )
            self.assertTrue(archive.with_suffix(".gz.sha256").exists())
            self.assertFalse(stale_gzip.exists())

            (public / "dynamic-stale.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "absent from the manifest"):
                package_dashboard_data(public, root / "stale.tar.gz")

            archive.with_suffix(".gz.sha256").write_text(
                f"{'0' * 64}  {archive.name}\n", encoding="ascii"
            )
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                install_dashboard_data(archive, target)


if __name__ == "__main__":
    unittest.main()
