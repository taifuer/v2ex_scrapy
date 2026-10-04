#!/usr/bin/env python3
"""Build isolated synthetic facts with the production aggregation pipeline."""

import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import analysis.build_analytics as builder
from sqlalchemy import create_engine
from v2ex_scrapy.items import Base


def create_facts(path: Path):
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    engine.dispose()
    zone = timezone(timedelta(hours=8))
    topics, comments, members = [], [], []
    nodes = ["qna", "programmer", "share", "python", "apple"]
    for i in range(30):
        members.append((i + 1, f"fixture_member_{i:02d}", "", int(datetime(2019, 1, i % 28 + 1, tzinfo=zone).timestamp()), "[]"))
    for year in range(2019, 2026):
        for month in range(1, 13):
            for i in range(30):
                topic_id = len(topics) + 1
                created = int(datetime(year, month, i % 27 + 1, 10, tzinfo=zone).timestamp())
                author = f"fixture_member_{i:02d}"
                topics.append((topic_id, author, f"AI Python Docker 开发经验 示例 {topic_id}", "<p>Synthetic fixture only.</p>", nodes[i % len(nodes)], json.dumps(["AI", "Python", "Docker"]), 1000 + i * 200, 0, created, i % 11, i % 13, 2))
                for no in (1, 2):
                    comments.append((len(comments) + 1, topic_id, f"fixture_member_{(i + no) % 30:02d}", "<div class='reply_content'>Synthetic comment for testing.</div>", no + i % 6, created + no * 600, no))
    with sqlite3.connect(path) as source:
        source.executemany("INSERT INTO member (uid,username,avatar_url,create_at,social_link) VALUES (?,?,?,?,?)", members)
        source.executemany("INSERT INTO topic (id,author,title,content,node,tag,clicks,votes,create_at,thank_count,favorite_count,reply_count) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", topics)
        source.executemany("INSERT INTO comment (id,topic_id,commenter,content,thank_count,create_at,no) VALUES (?,?,?,?,?,?,?)", comments)


def validate_fixture(public_dir: Path):
    load = lambda name: json.loads((public_dir / name).read_text(encoding="utf-8"))
    manifest = load("dynamic-manifest.json")
    assert manifest["schema_version"] == builder.ANALYTICS_SCHEMA_VERSION
    assert manifest["dataset_kind"] == "synthetic"
    for name, size in manifest["files"].items():
        assert Path(name).name == name
        assert (public_dir / name).stat().st_size == size, name
        load(name)
    overview = load("dynamic-overview.json")
    assert overview["periods"] and all(row["topic_count"] > 0 for row in overview["periods"])
    for index_name, key, pattern in [
        ("dynamic-tag-detail-index.json", "tags", "dynamic-tag-details-{}.json"),
        ("dynamic-content-hotspots-index.json", "terms", "dynamic-content-term-details-{}.json"),
        ("dynamic-node-detail-index.json", "nodes", "dynamic-node-details-{}.json"),
    ]:
        index = load(index_name)
        assert index[key], index_name
        for name, entry in index[key].items():
            if "bucket" in entry:
                shard = load(pattern.format(entry["bucket"]))
                assert name in shard["details"], (index_name, name)
    for name in load("dynamic-monthly-rankings-index.json")["periods"].values():
        ranking = load(name)["ranking"]
        for comment in ranking["comments"]:
            assert comment["thank_count"] >= 3
    print(f"Synthetic contract checks passed: {len(manifest['files'])} JSON files")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    if root.exists() and any(root.iterdir()):
        parser.error("Output must be a new or empty directory; existing data is never overwritten")
    root.mkdir(parents=True, exist_ok=True)
    analysis_dir = root / "analysis"
    analysis_dir.mkdir()
    for name in builder.ANALYSIS_CONFIG_FILES:
        shutil.copy2(ROOT / "analysis" / name, analysis_dir / name)
    source_db = root / "facts.sqlite"
    create_facts(source_db)
    builder.SOURCE_DB = source_db
    builder.ANALYSIS_DIR = analysis_dir
    builder.ANALYTICS_DB = analysis_dir / "analytics.sqlite"
    builder.PUBLIC_DIR = root / "public"
    builder._source_state_cache = None
    builder._source_tag_canonical_cache = None
    original_write = builder.write_json

    def isolated_write(path, payload):
        if not path.resolve().is_relative_to(root):
            raise ValueError(f"Fixture attempted to write outside its output directory: {path}")
        return original_write(path, payload)

    builder.write_json = isolated_write
    builder.build()
    manifest_path = builder.PUBLIC_DIR / "dynamic-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["dataset_kind"] = "synthetic"
    builder.write_json(manifest_path, manifest)
    for name in ("favicon.svg", "social-preview.png"):
        shutil.copy2(ROOT / "analysis/v2ex-analysis/public" / name, builder.PUBLIC_DIR / name)
    validate_fixture(builder.PUBLIC_DIR)
    print(f"Fixture public directory: {builder.PUBLIC_DIR}")


if __name__ == "__main__":
    main()
