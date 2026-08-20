#!/usr/bin/env python3
import argparse
import json
import re
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOCK = ROOT / "analysis" / "dashboard-data.lock.json"
DEFAULT_TARGET = ROOT / "analysis" / "v2ex-analysis" / "public"
DEFAULT_CACHE = ROOT / "dist" / "dashboard-data"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.install_dashboard_data import (
    PACKAGE_METADATA,
    file_sha256,
    install_dashboard_data,
)


def load_release_lock(path: Path) -> dict:
    lock = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "format_version",
        "repository",
        "release_tag",
        "archive",
        "url",
        "sha256",
        "archive_bytes",
        "schema_version",
        "generated_at",
        "complete_through",
        "file_count",
        "total_bytes",
    }
    missing = required - set(lock)
    if missing:
        raise ValueError(f"dashboard data lock is missing fields: {sorted(missing)}")
    if int(lock["format_version"]) != 1:
        raise ValueError("unsupported dashboard data lock format")
    archive = str(lock["archive"])
    if Path(archive).name != archive or not archive.endswith(".tar.gz"):
        raise ValueError("invalid dashboard data archive name")
    digest = str(lock["sha256"]).lower()
    if not SHA256_RE.fullmatch(digest):
        raise ValueError("invalid dashboard data SHA-256")
    repository = str(lock["repository"])
    parsed = urlparse(str(lock["url"]))
    expected_prefix = f"/{repository}/releases/download/"
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or not parsed.path.startswith(expected_prefix)
        or not parsed.path.endswith(f"/{archive}")
    ):
        raise ValueError("dashboard data URL is not a trusted GitHub release asset")
    for field in ("archive_bytes", "schema_version", "file_count", "total_bytes"):
        if int(lock[field]) <= 0:
            raise ValueError(f"invalid dashboard data lock value: {field}")
    lock["sha256"] = digest
    return lock


def installed_data_matches(target: Path, lock: dict) -> bool:
    manifest_path = target / "dynamic-manifest.json"
    if not manifest_path.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    analysis_state = manifest.get("full_build_state", {}).get("analysis", {})
    if (
        int(manifest.get("schema_version", -1)) != int(lock["schema_version"])
        or manifest.get("generated_at") != lock["generated_at"]
        or analysis_state.get("complete_through") != lock["complete_through"]
    ):
        return False
    files = manifest.get("files", {})
    if len(files) + 1 != int(lock["file_count"]):
        return False
    return all(
        (target / name).is_file()
        and (target / name).stat().st_size == int(expected_size)
        for name, expected_size in files.items()
    )


def valid_cached_archive(path: Path, lock: dict) -> bool:
    return (
        path.is_file()
        and path.stat().st_size == int(lock["archive_bytes"])
        and file_sha256(path) == lock["sha256"]
    )


def read_package_metadata(path: Path) -> dict:
    with tarfile.open(path, "r:gz") as archive:
        member = archive.getmember(PACKAGE_METADATA)
        source = archive.extractfile(member)
        if source is None:
            raise ValueError("dashboard data package metadata is unreadable")
        return json.loads(source.read().decode("utf-8"))


def validate_package_against_lock(path: Path, lock: dict) -> None:
    metadata = read_package_metadata(path)
    for field in (
        "schema_version",
        "generated_at",
        "complete_through",
        "analysis_config_hash",
        "source_counts",
        "file_count",
        "total_bytes",
    ):
        if metadata.get(field) != lock.get(field):
            raise ValueError(f"dashboard data package does not match lock field: {field}")


def download_archive(url: str, destination: Path, expected_bytes: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "V2EX-Dashboard-Data-Installer/1.0"},
    )
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb", dir=destination.parent, prefix=f".{destination.name}.", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            with urllib.request.urlopen(request, timeout=120) as response:
                while chunk := response.read(1024 * 1024):
                    temporary.write(chunk)
        if temporary_path.stat().st_size != expected_bytes:
            raise ValueError("downloaded dashboard data archive has an unexpected size")
        temporary_path.replace(destination)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def fetch_dashboard_data(
    lock_path: Path,
    target: Path,
    cache_dir: Path,
    *,
    force: bool = False,
    offline: bool = False,
) -> dict:
    lock = load_release_lock(lock_path)
    if not force and installed_data_matches(target, lock):
        return {"status": "current", **lock}

    archive = cache_dir / lock["archive"]
    if not valid_cached_archive(archive, lock):
        archive.unlink(missing_ok=True)
        if offline:
            raise FileNotFoundError("verified dashboard data archive is not cached")
        download_archive(lock["url"], archive, int(lock["archive_bytes"]))
        if not valid_cached_archive(archive, lock):
            archive.unlink(missing_ok=True)
            raise ValueError("downloaded dashboard data archive failed SHA-256 verification")

    archive.with_suffix(f"{archive.suffix}.sha256").write_text(
        f"{lock['sha256']}  {archive.name}\n", encoding="ascii"
    )
    validate_package_against_lock(archive, lock)
    install_dashboard_data(archive, target)
    if not installed_data_matches(target, lock):
        raise ValueError("installed dashboard data is incomplete")
    return {"status": "installed", **lock}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    lock = load_release_lock(args.lock)
    if args.check:
        if not installed_data_matches(args.target, lock):
            raise SystemExit("Dashboard data is missing or does not match the lock.")
        print(
            f"Dashboard data is current: {lock['complete_through']}, "
            f"schema v{lock['schema_version']}"
        )
        return

    result = fetch_dashboard_data(
        args.lock,
        args.target,
        args.cache_dir,
        force=args.force,
        offline=args.offline,
    )
    print(
        f"Dashboard data {result['status']}: {result['complete_through']}, "
        f"schema v{result['schema_version']}, {result['file_count']} files"
    )


if __name__ == "__main__":
    main()
