#!/usr/bin/env python3
"""Check all generated public files for explicitly excluded identities/content."""

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from analysis.publication import load_publication_policy, require_publication_rebuild


def audit_publication(public_dir: Path, source_db: Path, *, for_deploy: bool = False) -> dict:
    if for_deploy:
        manifest_path = public_dir / "dynamic-manifest.json"
        if not manifest_path.is_file():
            raise ValueError("Deployment requires an analytics manifest")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("dataset_kind") == "synthetic":
            raise ValueError("Synthetic data must not be deployed")
    require_publication_rebuild(public_dir)
    policy = load_publication_policy()
    if not policy.active:
        return {"active": False, "checked_files": 0, "violations": []}
    topic_ids = set(policy.topic_ids + policy.restricted_topic_ids)
    with sqlite3.connect(f"{source_db.resolve().as_uri()}?mode=ro", uri=True) as source:
        for user in policy.users:
            topic_ids.update(row[0] for row in source.execute(
                "SELECT id FROM topic WHERE author = ? COLLATE NOCASE", (user,)
            ))
    comments = set(policy.comment_ids)
    users = set(policy.users)
    violations = []

    def walk(value, filename, location="$", field=""):
        if isinstance(value, dict):
            if value.get("topic_id") in topic_ids or (
                value.get("id") in topic_ids and "title" in value and "commenter" not in value
            ):
                violations.append(f"{filename}:{location}: excluded topic")
            if value.get("comment_id") in comments or (
                value.get("id") in comments and ("commenter" in value or "topic_id" in value)
            ):
                violations.append(f"{filename}:{location}: excluded comment")
            for key, item in value.items():
                member_keys = field in {"members", "profiles"} or (
                    field == "comments" and filename.startswith("dynamic-member-comments-")
                )
                if member_keys and key.casefold() in users:
                    violations.append(f"{filename}:{location}: excluded member key")
                walk(item, filename, f"{location}.{key}", key)
        elif isinstance(value, list):
            if field == "rank_rows" and len(value) == 6 and isinstance(value[4], str) and value[4].casefold() in users:
                violations.append(f"{filename}:{location}: excluded ranked member")
            for index, item in enumerate(value):
                walk(item, filename, f"{location}[{index}]", field)
        elif isinstance(value, str):
            matched_user = (field in {"username", "author", "commenter", "default_member", "authors", "commenters"} and value.casefold() in users) or any(
                re.search(r"(?:@|/member/|[?&]member=)" + re.escape(user) + r"(?![A-Za-z0-9_-])", value, re.I)
                for user in users
            )
            linked_post = any(int(match) in topic_ids for match in re.findall(r"/t/(\d+)(?!\d)", value))
            linked_comment = any(int(match) in comments for match in re.findall(r"#r_(\d+)(?!\d)", value))
            if matched_user or linked_post or linked_comment:
                violations.append(f"{filename}:{location}: excluded reference; review embedded text/link")

    files = sorted(public_dir.glob("dynamic-*.json"))
    for path in files:
        walk(json.loads(path.read_text(encoding="utf-8")), path.name)
    return {"active": True, "checked_files": len(files), "violations": violations}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-dir", type=Path, default=ROOT / "analysis/v2ex-analysis/public")
    parser.add_argument("--source-db", type=Path, default=ROOT / "v2ex.sqlite")
    parser.add_argument("--for-deploy", action="store_true", help="Require a manifest and reject synthetic data")
    args = parser.parse_args()
    report = audit_publication(args.public_dir, args.source_db, for_deploy=args.for_deploy)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["violations"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
