#!/usr/bin/env python3
import argparse
import hashlib
import json
import shutil
import tarfile
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = ROOT / "analysis" / "v2ex-analysis" / "public"
PACKAGE_METADATA = "dashboard-data-package.json"


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_sidecar_checksum(archive_path: Path) -> None:
    sidecar = archive_path.with_suffix(f"{archive_path.suffix}.sha256")
    if not sidecar.exists():
        return
    fields = sidecar.read_text(encoding="ascii").strip().split()
    if not fields or fields[0].lower() != file_sha256(archive_path):
        raise ValueError("archive SHA-256 does not match its sidecar")


def install_dashboard_data(archive_path: Path, target: Path) -> dict:
    verify_sidecar_checksum(archive_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as directory:
        staging = Path(directory)
        with tarfile.open(archive_path, "r:gz") as archive:
            members = archive.getmembers()
            allowed = {
                member.name
                for member in members
                if member.isfile()
                and (
                    member.name == PACKAGE_METADATA
                    or (
                        member.name.startswith("dynamic-")
                        and member.name.endswith(".json")
                    )
                )
                and Path(member.name).name == member.name
            }
            if len(allowed) != len([member for member in members if member.isfile()]):
                raise ValueError("archive contains unsupported or unsafe paths")
            for member in members:
                if not member.isfile():
                    continue
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError(f"cannot read packaged file: {member.name}")
                with (staging / member.name).open("wb") as destination:
                    shutil.copyfileobj(source, destination)

        metadata = json.loads(
            (staging / PACKAGE_METADATA).read_text(encoding="utf-8")
        )
        files = metadata.get("files", {})
        if len(files) != int(metadata.get("file_count", -1)):
            raise ValueError("package file count does not match metadata")
        if set(allowed) != set(files) | {PACKAGE_METADATA}:
            raise ValueError("archive file list does not match package metadata")
        actual_total = 0
        for name, expected_size in files.items():
            path = staging / name
            if (
                Path(name).name != name
                or not name.startswith("dynamic-")
                or not name.endswith(".json")
                or not path.is_file()
                or path.stat().st_size != int(expected_size)
            ):
                raise ValueError(f"invalid packaged dashboard file: {name}")
            actual_total += path.stat().st_size
        if actual_total != int(metadata.get("total_bytes", -1)):
            raise ValueError("package byte count does not match metadata")

        target.mkdir(parents=True, exist_ok=True)
        for path in target.glob("dynamic-*.json"):
            path.unlink()
        for path in target.glob("dynamic-*.json.gz"):
            path.unlink()
        for name in files:
            shutil.move(staging / name, target / name)
        return metadata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--target", type=Path, default=PUBLIC_DIR)
    args = parser.parse_args()
    metadata = install_dashboard_data(args.archive, args.target)
    print(
        f"Installed {metadata['file_count']} dashboard files for "
        f"{metadata.get('complete_through') or 'unknown period'} into {args.target}"
    )


if __name__ == "__main__":
    main()
