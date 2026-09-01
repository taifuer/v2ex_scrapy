#!/usr/bin/env python3
"""Build a stratified review queue from real V2EX topic titles."""

from __future__ import annotations

import argparse
import html
import json
import random
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.content_hotspots import TitleTokenizer  # noqa: E402
from scripts.evaluate_title_keywords import load_gold  # noqa: E402


ANALYSIS_DIR = ROOT / "analysis"
SOURCE_DB = ROOT / "v2ex.sqlite"
DEFAULT_GOLD = ANALYSIS_DIR / "title_keyword_gold.jsonl"
DEFAULT_REVIEW = ANALYSIS_DIR / "tokenizer_audits" / "gold-review.jsonl"
MIN_VALID_CREATE_AT = 1262304000
PERIOD_BANDS = (
    ("2010-2014", "2010-01", "2014-12"),
    ("2015-2019", "2015-01", "2019-12"),
    ("2020-2023", "2020-01", "2023-12"),
    ("2024-latest", "2024-01", "9999-12"),
)
TITLE_STYLES = ("short", "long", "mixed", "latin", "chinese")
CHINESE_RE = re.compile(r"[\u3400-\u9fff]")
LATIN_RE = re.compile(r"[A-Za-z]")


def period_band(period: str) -> str:
    for name, start, end in PERIOD_BANDS:
        if start <= period <= end:
            return name
    return "outside"


def title_style(title: str) -> str:
    normalized = html.unescape(title).strip()
    length = len(normalized)
    has_chinese = CHINESE_RE.search(normalized) is not None
    has_latin = LATIN_RE.search(normalized) is not None
    if length <= 12:
        return "short"
    if length >= 42:
        return "long"
    if has_chinese and has_latin:
        return "mixed"
    if has_latin:
        return "latin"
    return "chinese"


def reservoir_add(
    reservoir: list[dict],
    row: dict,
    seen: int,
    limit: int,
    rng: random.Random,
) -> None:
    if limit <= 0:
        return
    if len(reservoir) < limit:
        reservoir.append(row)
        return
    replacement = rng.randrange(seen)
    if replacement < limit:
        reservoir[replacement] = row


def sample_real_titles(
    database: Path,
    existing_titles: set[str],
    sample_size: int,
    seed: int,
    end_period: str = "9999-12",
    batch_size: int = 5000,
) -> list[dict]:
    strata = [
        f"{band}/{style}"
        for band, _, _ in PERIOD_BANDS
        for style in TITLE_STYLES
    ]
    base_quota, remainder = divmod(sample_size, len(strata))
    quotas = {
        stratum: base_quota + int(index < remainder)
        for index, stratum in enumerate(strata)
    }
    reservoirs: dict[str, list[dict]] = defaultdict(list)
    seen_by_stratum: dict[str, int] = defaultdict(int)
    fallback: list[dict] = []
    fallback_seen = 0
    rng = random.Random(seed)
    fallback_rng = random.Random(seed + 1)

    last_id = 0
    while True:
        source = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
        rows = source.execute(
            """
            SELECT id, title, node,
                   strftime('%Y-%m', create_at, 'unixepoch', '+8 hours') AS period
            FROM topic
            WHERE clicks >= 0 AND create_at >= ? AND title != '' AND id > ?
            ORDER BY id
            LIMIT ?
            """,
            (MIN_VALID_CREATE_AT, last_id, max(1, batch_size)),
        ).fetchall()
        source.close()
        if not rows:
            break
        for topic_id, title, node, period in rows:
            if title in existing_titles or not period or str(period) > end_period:
                continue
            band = period_band(str(period))
            if band == "outside":
                continue
            style = title_style(str(title))
            stratum = f"{band}/{style}"
            row = {
                "topic_id": int(topic_id),
                "period": str(period),
                "node": str(node or ""),
                "stratum": stratum,
                "title": str(title),
            }
            seen_by_stratum[stratum] += 1
            reservoir_add(
                reservoirs[stratum],
                row,
                seen_by_stratum[stratum],
                quotas[stratum],
                rng,
            )
            fallback_seen += 1
            reservoir_add(
                fallback,
                row,
                fallback_seen,
                max(sample_size * 3, sample_size),
                fallback_rng,
            )
        last_id = int(rows[-1][0])
        if len(rows) < max(1, batch_size):
            break

    selected = []
    selected_ids = set()
    for stratum in strata:
        for row in reservoirs.get(stratum, []):
            if row["topic_id"] in selected_ids:
                continue
            selected.append(row)
            selected_ids.add(row["topic_id"])
    if len(selected) < sample_size:
        for row in fallback:
            if row["topic_id"] in selected_ids:
                continue
            selected.append(row)
            selected_ids.add(row["topic_id"])
            if len(selected) >= sample_size:
                break
    selected.sort(
        key=lambda row: (row["stratum"], row["period"], row["topic_id"])
    )
    return selected[:sample_size]


def build_review_rows(rows: list[dict], tokenizer: TitleTokenizer) -> list[dict]:
    return [
        {
            "review_status": "pending",
            **row,
            "suggested": sorted(
                tokenizer.tokenize(row["title"]),
                key=lambda term: (term.casefold(), term),
            ),
            "expected": None,
            "notes": "",
        }
        for row in rows
    ]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    temporary.replace(path)


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as source:
        for line_number, raw_line in enumerate(source, 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            row = json.loads(line)
            row["_line_number"] = line_number
            rows.append(row)
    return rows


def append_approved(review_path: Path, gold_path: Path) -> int:
    gold_rows = load_gold(gold_path)
    existing_ids = {str(row["id"]) for row in gold_rows}
    existing_titles = {str(row["title"]) for row in gold_rows}
    approved = []
    for row in read_jsonl(review_path):
        if row.get("review_status") != "approved":
            continue
        expected = row.get("expected")
        if not isinstance(expected, list) or any(
            not isinstance(term, str) for term in expected
        ):
            raise ValueError(
                f"approved row {review_path}:{row['_line_number']} needs expected: []"
            )
        topic_id = int(row["topic_id"])
        gold_id = f"real-{topic_id}"
        title = str(row["title"])
        if gold_id in existing_ids or title in existing_titles:
            continue
        approved.append(
            {
                "id": gold_id,
                "category": f"real-{str(row['stratum']).split('/')[-1]}",
                "title": title,
                "expected": list(dict.fromkeys(expected)),
                "topic_id": topic_id,
                "period": str(row.get("period", "")),
                "node": str(row.get("node", "")),
            }
        )
        existing_ids.add(gold_id)
        existing_titles.add(title)
    if not approved:
        return 0

    encoded_existing = gold_path.read_text(encoding="utf-8").rstrip()
    encoded_new = "\n".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        for row in approved
    )
    temporary = gold_path.with_suffix(gold_path.suffix + ".tmp")
    temporary.write_text(encoded_existing + "\n" + encoded_new + "\n", encoding="utf-8")
    temporary.replace(gold_path)
    return len(approved)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sample real titles for review or append reviewed rows to the gold set."
    )
    parser.add_argument("action", nargs="?", choices=("sample", "apply"), default="sample")
    parser.add_argument("--source-db", type=Path, default=SOURCE_DB)
    parser.add_argument("--analysis-dir", type=Path, default=ANALYSIS_DIR)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--sample-size", type=int, default=376)
    parser.add_argument("--seed", type=int, default=20260821)
    parser.add_argument("--end-period")
    parser.add_argument("--batch-size", type=int, default=5000)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.action == "apply":
        appended = append_approved(args.review, args.gold)
        print(f"Appended {appended:,} reviewed rows to {args.gold}")
        return

    gold_rows = load_gold(args.gold)
    end_period = args.end_period
    if end_period is None:
        overview_path = (
            args.analysis_dir / "v2ex-analysis" / "public" / "dynamic-overview.json"
        )
        overview = json.loads(overview_path.read_text(encoding="utf-8"))
        end_period = str(overview["metadata"]["default_end_period"])
    sampled = sample_real_titles(
        args.source_db,
        {str(row["title"]) for row in gold_rows},
        max(1, args.sample_size),
        args.seed,
        end_period,
        max(1, args.batch_size),
    )
    review = build_review_rows(sampled, TitleTokenizer(args.analysis_dir))
    write_jsonl(args.review, review)
    counts: dict[str, int] = defaultdict(int)
    for row in review:
        counts[row["stratum"]] += 1
    print(
        f"Wrote {len(review):,} pending real-title reviews across "
        f"{len(counts):,} strata to {args.review}"
    )
    print("Review expected terms manually, set review_status to approved, then run apply.")


if __name__ == "__main__":
    main()
