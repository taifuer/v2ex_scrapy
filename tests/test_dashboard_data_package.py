import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
                "full_build_state": {
                    "analysis": {
                        "complete_through": "2026-07",
                        "config_hash": "abc123",
                    },
                    "topic": {"count": 120},
                    "comment": {"count": 340},
                    "member": {"count": 56},
                },
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
            self.assertEqual(result["analysis_config_hash"], "abc123")
            self.assertEqual(result["source_counts"]["comment"], 340)
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

    def test_restores_previous_files_when_install_move_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            public = root / "public"
            public.mkdir()
            payload = public / "dynamic-overview.json"
            payload.write_text('{"version":"new"}', encoding="utf-8")
            manifest = {
                "schema_version": 32,
                "generated_at": "2026-08-14T00:00:00+08:00",
                "files": {payload.name: payload.stat().st_size},
            }
            (public / "dynamic-manifest.json").write_text(
                json.dumps(manifest, separators=(",", ":")), encoding="utf-8"
            )
            archive = root / "dashboard-data.tar.gz"
            package_dashboard_data(public, archive)

            target = root / "installed"
            target.mkdir()
            previous = target / payload.name
            previous.write_text('{"version":"old"}', encoding="utf-8")
            real_move = shutil.move
            failed = False

            def fail_new_payload(source, destination):
                nonlocal failed
                source_path = Path(source)
                if source_path.name == payload.name and source_path.parent != target and not failed:
                    failed = True
                    raise OSError("simulated move failure")
                return real_move(source, destination)

            with patch(
                "scripts.install_dashboard_data.shutil.move",
                side_effect=fail_new_payload,
            ):
                with self.assertRaisesRegex(OSError, "simulated move failure"):
                    install_dashboard_data(archive, target)

            self.assertEqual(previous.read_text(encoding="utf-8"), '{"version":"old"}')

    def test_restores_files_when_backup_move_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            public = root / "public"
            public.mkdir()
            payload = public / "dynamic-overview.json"
            payload.write_text('{"version":"new"}', encoding="utf-8")
            manifest = {
                "schema_version": 32,
                "generated_at": "2026-08-14T00:00:00+08:00",
                "files": {payload.name: payload.stat().st_size},
            }
            (public / "dynamic-manifest.json").write_text(
                json.dumps(manifest, separators=(",", ":")), encoding="utf-8"
            )
            archive = root / "dashboard-data.tar.gz"
            package_dashboard_data(public, archive)

            target = root / "installed"
            target.mkdir()
            first = target / "dynamic-a.json"
            second = target / "dynamic-b.json"
            first.write_text("first", encoding="utf-8")
            second.write_text("second", encoding="utf-8")
            real_move = shutil.move

            def fail_second_backup(source, destination):
                source_path = Path(source)
                if source_path == second:
                    raise OSError("simulated backup failure")
                return real_move(source, destination)

            with patch(
                "scripts.install_dashboard_data.shutil.move",
                side_effect=fail_second_backup,
            ):
                with self.assertRaisesRegex(OSError, "simulated backup failure"):
                    install_dashboard_data(archive, target)

            self.assertEqual(first.read_text(encoding="utf-8"), "first")
            self.assertEqual(second.read_text(encoding="utf-8"), "second")


if __name__ == "__main__":
    unittest.main()
