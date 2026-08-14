#!/usr/bin/env python3
import argparse
import hashlib
import json
import tarfile
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = ROOT / "analysis" / "v2ex-analysis" / "public"
ARTIFACT_DIR = ROOT / "dist"
PACKAGE_METADATA = "dashboard-data-package.json"


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def dashboard_files(public_dir: Path) -> list[Path]:
    return sorted(public_dir.glob("dynamic-*.json"), key=lambda path: path.name)


def validate_dashboard_files(public_dir: Path, files: list[Path]) -> dict:
    manifest_path = public_dir / "dynamic-manifest.json"
    if manifest_path not in files:
        raise ValueError("dynamic-manifest.json is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    declared = manifest.get("files", {})
    actual_names = {path.name for path in files}
    expected_names = set(declared) | {manifest_path.name}
    missing = set(declared) - actual_names
    if missing:
        raise ValueError(f"manifest files are missing: {sorted(missing)[:5]}")
    unexpected = actual_names - expected_names
    if unexpected:
        raise ValueError(f"files are absent from the manifest: {sorted(unexpected)[:5]}")
    mismatched = [
        path.name
        for path in files
        if path.name in declared and path.stat().st_size != int(declared[path.name])
    ]
    if mismatched:
        raise ValueError(f"manifest file sizes do not match: {mismatched[:5]}")
    return manifest


def package_dashboard_data(public_dir: Path, output: Path) -> dict:
    files = dashboard_files(public_dir)
    manifest = validate_dashboard_files(public_dir, files)
    metadata = {
        "schema_version": manifest["schema_version"],
        "generated_at": manifest["generated_at"],
        "complete_through": manifest.get("full_build_state", {})
        .get("analysis", {})
        .get("complete_through", ""),
        "file_count": len(files),
        "total_bytes": sum(path.stat().st_size for path in files),
        "files": {path.name: path.stat().st_size for path in files},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        metadata_path = Path(directory) / PACKAGE_METADATA
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        with tarfile.open(output, "w:gz", compresslevel=6) as archive:
            archive.add(metadata_path, arcname=PACKAGE_METADATA)
            for path in files:
                archive.add(path, arcname=path.name)
    digest = file_sha256(output)
    output.with_suffix(f"{output.suffix}.sha256").write_text(
        f"{digest}  {output.name}\n", encoding="ascii"
    )
    return {**metadata, "archive": str(output), "sha256": digest}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--public-dir", type=Path, default=PUBLIC_DIR)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    manifest = json.loads(
        (args.public_dir / "dynamic-manifest.json").read_text(encoding="utf-8")
    )
    complete_through = (
        manifest.get("full_build_state", {})
        .get("analysis", {})
        .get("complete_through", "unknown")
    )
    output = args.output or (
        ARTIFACT_DIR
        / f"v2ex-dashboard-data-{complete_through}-schema-v{manifest['schema_version']}.tar.gz"
    )
    result = package_dashboard_data(args.public_dir, output)
    print(
        f"Packaged {result['file_count']} files, {result['total_bytes']:,} bytes: "
        f"{result['archive']}\nSHA-256: {result['sha256']}"
    )


if __name__ == "__main__":
    main()
