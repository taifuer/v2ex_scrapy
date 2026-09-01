#!/usr/bin/env python3
"""Measure repeated representative-post payloads in generated dashboard JSON."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = ROOT / "analysis" / "v2ex-analysis" / "public"
DEFAULT_OUTPUT = ROOT / "analysis" / "data_audits" / "dashboard-duplication.json"
STABLE_POST_FIELDS = (
    "id",
    "title",
    "node",
    "author",
    "create_at",
    "clicks",
    "reply_count",
    "favorite_count",
    "thank_count",
    "votes",
)


def encoded_size(value) -> int:
    return len(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )


def is_post(value: dict) -> bool:
    return (
        isinstance(value.get("id"), int)
        and isinstance(value.get("title"), str)
        and isinstance(value.get("node"), str)
        and isinstance(value.get("create_at"), int)
        and "reply_count" in value
    )


def walk_posts(value):
    if isinstance(value, dict):
        if is_post(value):
            yield value
        for child in value.values():
            yield from walk_posts(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_posts(child)


def file_group(name: str) -> str:
    prefixes = (
        "dynamic-tag-period-posts-",
        "dynamic-content-period-posts-",
        "dynamic-node-period-posts-",
        "dynamic-tag-details-",
        "dynamic-content-term-details-",
        "dynamic-node-details-",
        "dynamic-member-profiles-",
        "dynamic-monthly-ranking-",
        "dynamic-annual-ranking-",
    )
    for prefix in prefixes:
        if name.startswith(prefix):
            return prefix.removeprefix("dynamic-").removesuffix("-")
    return "other"


def merge_stable_payload(
    target: dict,
    candidate: dict,
    post_id: int,
    mismatched_ids: set[int],
) -> None:
    for field, value in candidate.items():
        if field in target and target[field] != value:
            mismatched_ids.add(post_id)
            continue
        target[field] = value


def audit_directory(public_dir: Path) -> dict:
    occurrences = Counter()
    stable_payloads: dict[int, dict] = {}
    mismatched_ids = set()
    groups: dict[str, Counter] = {}
    files_scanned = 0
    json_bytes = 0
    post_occurrences = 0
    stable_occurrence_bytes = 0
    within_file_duplicated_bytes = 0

    for path in sorted(public_dir.glob("dynamic-*.json")):
        files_scanned += 1
        file_bytes = path.stat().st_size
        json_bytes += file_bytes
        payload = json.loads(path.read_text(encoding="utf-8"))
        group = file_group(path.name)
        group_stats = groups.setdefault(group, Counter())
        group_stats["files"] += 1
        group_stats["json_bytes"] += file_bytes
        file_occurrence_bytes = 0
        file_stable_payloads: dict[int, dict] = {}
        for post in walk_posts(payload):
            post_id = int(post["id"])
            stable = {
                field: post[field]
                for field in STABLE_POST_FIELDS
                if field in post
            }
            size = encoded_size(stable)
            post_occurrences += 1
            stable_occurrence_bytes += size
            file_occurrence_bytes += size
            occurrences[post_id] += 1
            group_stats["post_occurrences"] += 1
            group_stats["stable_occurrence_bytes"] += size
            if post_id not in stable_payloads:
                stable_payloads[post_id] = stable
            else:
                merge_stable_payload(
                    stable_payloads[post_id], stable, post_id, mismatched_ids
                )
            if post_id not in file_stable_payloads:
                file_stable_payloads[post_id] = stable.copy()
            else:
                merge_stable_payload(
                    file_stable_payloads[post_id], stable, post_id, mismatched_ids
                )
        file_unique_bytes = sum(
            encoded_size(stable) for stable in file_stable_payloads.values()
        )
        file_duplicate_bytes = max(0, file_occurrence_bytes - file_unique_bytes)
        within_file_duplicated_bytes += file_duplicate_bytes
        group_stats["within_file_duplicated_stable_bytes_upper_bound"] += (
            file_duplicate_bytes
        )

    stable_sizes = {
        post_id: encoded_size(stable) for post_id, stable in stable_payloads.items()
    }
    unique_stable_bytes = sum(stable_sizes.values())
    duplicated_stable_bytes = max(0, stable_occurrence_bytes - unique_stable_bytes)
    repeated_ids = {post_id: count for post_id, count in occurrences.items() if count > 1}
    top_repeated = sorted(
        repeated_ids.items(), key=lambda item: (-item[1], item[0])
    )[:30]
    return {
        "metadata": {
            "files_scanned": files_scanned,
            "json_bytes": json_bytes,
            "scope": "dynamic-*.json",
            "stable_post_fields": list(STABLE_POST_FIELDS),
        },
        "posts": {
            "occurrences": post_occurrences,
            "unique_ids": len(occurrences),
            "repeated_ids": len(repeated_ids),
            "average_occurrences_per_id": round(
                post_occurrences / max(1, len(occurrences)), 3
            ),
            "stable_occurrence_bytes": stable_occurrence_bytes,
            "unique_stable_bytes": unique_stable_bytes,
            "duplicated_stable_bytes_upper_bound": duplicated_stable_bytes,
            "duplicated_share_of_all_json": round(
                duplicated_stable_bytes / max(1, json_bytes), 4
            ),
            "within_file_duplicated_stable_bytes_upper_bound": (
                within_file_duplicated_bytes
            ),
            "within_file_duplicated_share_of_all_json": round(
                within_file_duplicated_bytes / max(1, json_bytes), 4
            ),
            "mismatched_stable_payload_ids": sorted(mismatched_ids),
            "top_repeated": [
                {"id": post_id, "occurrences": count}
                for post_id, count in top_repeated
            ],
        },
        "groups": {
            name: dict(values)
            for name, values in sorted(
                groups.items(),
                key=lambda item: (-item[1]["json_bytes"], item[0]),
            )
        },
        "interpretation": {
            "duplicated_bytes_are_upper_bound": True,
            "notes": (
                "Global duplication is the cross-file theoretical ceiling. Within-file "
                "duplication is the safer ceiling for a one-request entity-plus-reference "
                "format. Neither estimate includes reference/index overhead or gzip effects."
            ),
        },
    }


def write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit duplicate representative-post payloads in dashboard JSON."
    )
    parser.add_argument("--public-dir", type=Path, default=PUBLIC_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = audit_directory(args.public_dir)
    write_report(args.output, report)
    posts = report["posts"]
    metadata = report["metadata"]
    print(
        f"Scanned {metadata['files_scanned']:,} files "
        f"({metadata['json_bytes'] / 1024 / 1024:.1f} MiB)."
    )
    print(
        f"Found {posts['occurrences']:,} post occurrences for "
        f"{posts['unique_ids']:,} IDs; upper-bound duplicated stable payload "
        f"{posts['duplicated_stable_bytes_upper_bound'] / 1024 / 1024:.1f} MiB "
        f"({posts['duplicated_share_of_all_json']:.1%} of JSON)."
    )
    print(
        "Within-file upper bound without extra requests: "
        f"{posts['within_file_duplicated_stable_bytes_upper_bound'] / 1024 / 1024:.1f} MiB "
        f"({posts['within_file_duplicated_share_of_all_json']:.1%} of JSON)."
    )
    print(f"Report written to {args.output}")


if __name__ == "__main__":
    main()
