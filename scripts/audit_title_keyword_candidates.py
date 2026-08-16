#!/usr/bin/env python3
import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from analysis.content_hotspots import (  # noqa: E402
    EXCLUDED_NODES,
    _configured_content_terms,
    cached_title_tokens,
    sync_title_token_cache,
)


ANALYSIS_DIR = ROOT / "analysis"
SOURCE_DB = ROOT / "v2ex.sqlite"
PUBLIC_DIR = ANALYSIS_DIR / "v2ex-analysis" / "public"
DEFAULT_OUTPUT = ANALYSIS_DIR / "tokenizer_audits" / "candidates.json"
LOCAL_TIMEZONE = timezone(timedelta(hours=8))
MIN_VALID_CREATE_AT = 1262304000


def period_of(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, LOCAL_TIMEZONE).strftime("%Y-%m")


def previous_period(period: str, months: int) -> str:
    year, month = map(int, period.split("-"))
    absolute = year * 12 + month - 1 - months
    return f"{absolute // 12:04d}-{absolute % 12 + 1:02d}"


def collect_candidates(
    source_db: Path,
    token_cache: Path,
    indexed_terms: set[str],
    configured_terms: set[str],
    default_end_period: str,
    min_count: int,
    min_authors: int,
    min_nodes: int,
    limit: int,
) -> list[dict]:
    current_start = previous_period(default_end_period, 11)
    previous_start = previous_period(default_end_period, 23)
    previous_end = previous_period(default_end_period, 12)
    source = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    source.execute(
        "ATTACH DATABASE ? AS token_cache", (f"file:{token_cache}?mode=ro",)
    )
    query = """
        SELECT topic.id, topic.author, topic.title, topic.node, topic.create_at,
               cached.tokens AS cached_tokens
        FROM topic
        JOIN token_cache.title_tokens AS cached ON cached.topic_id = topic.id
        WHERE topic.clicks >= 0 AND topic.create_at >= ? AND topic.title != ''
        ORDER BY topic.id
    """
    counts = Counter()
    current_counts = Counter()
    previous_counts = Counter()
    for row in source.execute(query, (MIN_VALID_CREATE_AT,)):
        period = period_of(row["create_at"])
        if period > default_end_period or (row["node"] or "").casefold() in EXCLUDED_NODES:
            continue
        terms = cached_title_tokens(row) - indexed_terms
        counts.update(terms)
        if current_start <= period <= default_end_period:
            current_counts.update(terms)
        elif previous_start <= period <= previous_end:
            previous_counts.update(terms)

    eligible = {term for term, count in counts.items() if count >= min_count}
    authors: dict[str, set[str]] = defaultdict(set)
    nodes: dict[str, set[str]] = defaultdict(set)
    examples: dict[str, deque] = defaultdict(lambda: deque(maxlen=3))
    for row in source.execute(query, (MIN_VALID_CREATE_AT,)):
        period = period_of(row["create_at"])
        if period > default_end_period or (row["node"] or "").casefold() in EXCLUDED_NODES:
            continue
        for term in cached_title_tokens(row) & eligible:
            if row["author"]:
                authors[term].add(row["author"])
            if row["node"]:
                nodes[term].add(row["node"])
            examples[term].append(
                {"id": int(row["id"]), "period": period, "title": row["title"]}
            )
    source.close()

    rows = []
    for term in eligible:
        if len(authors[term]) < min_authors or len(nodes[term]) < min_nodes:
            continue
        current = current_counts[term]
        previous = previous_counts[term]
        rows.append(
            {
                "term": term,
                "titles": counts[term],
                "authors": len(authors[term]),
                "nodes": len(nodes[term]),
                "recent_12m": current,
                "previous_12m": previous,
                "change": current - previous,
                "configured": term in configured_terms,
                "examples": list(reversed(examples[term])),
            }
        )
    rows.sort(
        key=lambda item: (
            -item["titles"],
            -item["authors"],
            item["term"].casefold(),
            item["term"],
        )
    )
    return rows[:limit]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find stable title terms that are tokenized but not indexed"
    )
    parser.add_argument("--source-db", type=Path, default=SOURCE_DB)
    parser.add_argument("--analysis-dir", type=Path, default=ANALYSIS_DIR)
    parser.add_argument("--public-dir", type=Path, default=PUBLIC_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--min-count", type=int, default=20)
    parser.add_argument("--min-authors", type=int, default=15)
    parser.add_argument("--min-nodes", type=int, default=3)
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--skip-cache-sync", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    index_path = args.public_dir / "dynamic-content-hotspots-index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    token_cache = args.analysis_dir / "content_tokens.sqlite"
    cache_summary = None
    if not args.skip_cache_sync:
        cache_summary = sync_title_token_cache(
            args.source_db, args.analysis_dir, MIN_VALID_CREATE_AT, token_cache
        )
    rows = collect_candidates(
        args.source_db,
        token_cache,
        set(index.get("terms", {})),
        _configured_content_terms(args.analysis_dir),
        index["metadata"]["default_end_period"],
        args.min_count,
        args.min_authors,
        args.min_nodes,
        args.limit,
    )
    payload = {
        "metadata": {
            "default_end_period": index["metadata"]["default_end_period"],
            "min_count": args.min_count,
            "min_authors": args.min_authors,
            "min_nodes": args.min_nodes,
            "method": (
                "Candidates are stable production-tokenizer terms absent from the detail index. "
                "They require title review and never modify production dictionaries automatically."
            ),
            "cache": cache_summary,
        },
        "candidates": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp_path = args.output.with_suffix(f"{args.output.suffix}.tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temp_path.replace(args.output)
    print(f"Wrote {len(rows)} candidates to {args.output}")


if __name__ == "__main__":
    main()
