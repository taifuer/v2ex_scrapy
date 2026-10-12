#!/usr/bin/env python3
"""Validate the exact local dist before any remote deployment operation."""

import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from v2ex_scrapy.change_tracking import read_change_tracking_state
from v2ex_scrapy.fetch_completion import collection_fingerprint


def assert_source_matches(manifest: dict, database: Path) -> None:
    if manifest.get("dataset_kind") == "synthetic":
        raise ValueError("Synthetic data must not be deployed")
    if not database.is_file():
        raise ValueError("Release verification requires the local source database; the server still receives dist only")
    with sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True) as conn:
        current = read_change_tracking_state(conn)
        collection = collection_fingerprint(conn)
    expected = manifest.get("full_build_state", {})
    if current is None or expected.get("tracking_database_id") != current["database_id"]:
        raise ValueError("Cannot verify analytics source identity; rebuild analytics locally")
    for component in ("topic", "comment", "member"):
        if expected.get(component) != current[component]:
            raise ValueError(f"Analytics are stale for {component}; rebuild before deployment")
    if expected.get("collection") != collection:
        raise ValueError("Analytics are stale for comment collection; rebuild before deployment")


def verify_release(dist: Path, database: Path) -> dict:
    manifest = json.loads((dist / "dynamic-manifest.json").read_text(encoding="utf-8"))
    assert_source_matches(manifest, database)
    subprocess.run([sys.executable, str(ROOT / "scripts/audit_source_quality.py"),
                    "--database", str(database), "--fail-on-regression"], check=True)
    subprocess.run([sys.executable, str(ROOT / "scripts/validate_analytics.py"),
                    "--public-dir", str(dist)], check=True)
    subprocess.run([sys.executable, str(ROOT / "scripts/audit_publication.py"),
                    "--public-dir", str(dist), "--source-db", str(database), "--for-deploy"], check=True)
    # Recheck after validation so a concurrent crawl cannot silently invalidate it.
    assert_source_matches(manifest, database)
    digest = hashlib.sha256()
    for path in sorted(dist.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(dist).as_posix().encode())
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return {"validated_dist_sha256": digest.hexdigest(), "source_database_id": manifest["full_build_state"]["tracking_database_id"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=ROOT / "analysis/v2ex-analysis/dist")
    parser.add_argument("--database", type=Path, default=ROOT / "v2ex.sqlite")
    args = parser.parse_args()
    print(json.dumps(verify_release(args.dist, args.database)))
