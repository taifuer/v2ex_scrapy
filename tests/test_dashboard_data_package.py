import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.fetch_dashboard_data import (
    fetch_dashboard_data,
    installed_data_matches,
    load_release_lock,
    validate_package_against_lock,
)
from scripts.install_dashboard_data import install_dashboard_data
from scripts.package_dashboard_data import build_release_lock, package_dashboard_data


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

    def test_downloads_and_reuses_a_locked_release_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            public = root / "public"
            public.mkdir()
            payload = public / "dynamic-overview.json"
            payload.write_text('{"periods":[]}', encoding="utf-8")
            manifest = {
                "schema_version": 37,
                "generated_at": "2026-08-20T20:00:00+08:00",
                "files": {payload.name: payload.stat().st_size},
                "full_build_state": {
                    "analysis": {
                        "complete_through": "2026-07",
                        "config_hash": "config",
                    }
                },
            }
            (public / "dynamic-manifest.json").write_text(
                json.dumps(manifest, separators=(",", ":")), encoding="utf-8"
            )
            archive = root / "v2ex-dashboard-data.tar.gz"
            package = package_dashboard_data(public, archive)
            archive_bytes = archive.read_bytes()
            lock = build_release_lock(package, "dashboard-data-test")
            lock_path = root / "dashboard-data.lock.json"
            lock_path.write_text(json.dumps(lock), encoding="utf-8")
            archive.unlink()
            archive.with_suffix(".gz.sha256").unlink()

            target = root / "installed"
            cache = root / "cache"
            with patch(
                "scripts.fetch_dashboard_data.urllib.request.urlopen",
                return_value=io.BytesIO(archive_bytes),
            ) as download:
                result = fetch_dashboard_data(lock_path, target, cache)

            self.assertEqual(result["status"], "installed")
            self.assertTrue(installed_data_matches(target, lock))
            download.assert_called_once()

            with patch(
                "scripts.fetch_dashboard_data.urllib.request.urlopen"
            ) as download:
                result = fetch_dashboard_data(lock_path, target, cache)
            self.assertEqual(result["status"], "current")
            download.assert_not_called()

            loaded = load_release_lock(lock_path)
            loaded["url"] = "https://example.com/data.tar.gz"
            lock_path.write_text(json.dumps(loaded), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "trusted GitHub release"):
                load_release_lock(lock_path)

            bad_lock = {**lock, "schema_version": 38}
            with self.assertRaisesRegex(ValueError, "schema_version"):
                validate_package_against_lock(cache / lock["archive"], bad_lock)

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
