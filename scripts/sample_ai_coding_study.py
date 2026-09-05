#!/usr/bin/env python3
"""Create a reproducible, local-only review corpus for AI coding experiences."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.builders.common import LOCAL_TIMEZONE, comment_text  # noqa: E402

RULE_VERSION = 1
DEFAULT_OUTPUT = ROOT / "analysis/data_audits/ai-coding-study"
TOOLS = {
    "Claude Code": r"(?<![a-z])claude[\s_-]*code(?![a-z])",
    "GitHub Copilot": r"(?<![a-z])(?:github[\s_-]*)?copilot(?![a-z])",
    "Codex": r"(?<![a-z])codex(?![a-z])",
    "Cursor": r"(?<![a-z])cursor(?![a-z])",
    "Windsurf": r"(?<![a-z])windsurf(?![a-z])",
    "Cline": r"(?<![a-z])cline(?![a-z])",
    "Roo Code": r"(?<![a-z])roo[\s_-]*code(?![a-z])",
    "Aider": r"(?<![a-z])aider(?![a-z])",
    "Trae": r"(?<![a-z])trae(?![a-z])",
    "Augment": r"(?<![a-z])augment(?![a-z])",
    "Tabnine": r"(?<![a-z])tabnine(?![a-z])",
    "Qoder": r"(?<![a-z])qoder(?![a-z])",
    "Kiro": r"(?<![a-z])kiro(?![a-z])",
    "Devin": r"(?<![a-z])devin(?![a-z])",
    "OpenCode": r"(?<![a-z])open[\s_-]*code(?![a-z])",
    "Gemini CLI": r"(?<![a-z])gemini[\s_-]*cli(?![a-z])",
    "Kimi Code": r"(?<![a-z])kimi[\s_-]*code(?![a-z])",
    "CodeBuddy": r"(?<![a-z])code[\s_-]*buddy(?![a-z])",
    "Antigravity": r"(?<![a-z])antigravity(?![a-z])",
}
TOOL_PATTERNS = {name: re.compile(pattern, re.I) for name, pattern in TOOLS.items()}
GENERAL_AI = re.compile(r"(?<![a-z])(?:ai|chatgpt|claude|deepseek|glm|kimi|gpt)(?![a-z])|人工智能|大模型", re.I)
CODING_CONTEXT = re.compile(r"编程|代码|写码|补全|重构|(?<![a-z])(?:coding|code|ide|vibe)(?![a-z])", re.I)
AI_ASSISTED = re.compile(r"(?:用|借助|利用).{0,24}(?<![a-z])(?:ai|chatgpt|claude|deepseek|glm|kimi|gpt)(?![a-z]).{0,20}(?:写|开发|搭建|做了)|(?<![a-z])vibe[\s-]*coding(?![a-z])", re.I)
EXCLUDED_NODES = frozenset({"promotions", "all4all", "free", "exchange", "giveaway", "jobs", "cosub"})
CODING_NODES = frozenset({"programmer", "vibecoding", "ide", "cursor", "copilot", "claudecode", "aicode"})
PLACEHOLDERS = frozenset({"", "[图片]", "[视频]", "评论原文未收录", "内容已删除", "该回复已被删除"})
URL = re.compile(r"https?://\S+", re.I)
ATTRIBUTION = re.compile(r"转载|转过来|转自|译文|文章翻译|原作者|原文链接")


def candidate_tools(title: str) -> list[str]:
    tools = [name for name, pattern in TOOL_PATTERNS.items() if pattern.search(title)]
    if "Cursor" in tools and re.search(r"mongodb|数据库游标", title, re.I):
        tools.remove("Cursor")
    if "GitHub Copilot" in tools and re.search(r"windows|微软", title, re.I) and not re.search(r"github|代码|编程", title, re.I):
        tools.remove("GitHub Copilot")
    if not tools and ((GENERAL_AI.search(title) and CODING_CONTEXT.search(title)) or AI_ASSISTED.search(title)):
        tools.append("通用 AI 编程")
    return tools


class ProseParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skipped = []
        self.media = 0
        self.quoted_or_code = False

    def handle_starttag(self, tag, attrs):
        if tag in {"img", "iframe"}:
            self.media += 1
        if tag in {"blockquote", "pre", "code", "script", "style"}:
            self.skipped.append(tag)
            self.quoted_or_code = True
        if tag in {"p", "div", "br", "li"} and not self.skipped:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.skipped:
            index = len(self.skipped) - 1 - self.skipped[::-1].index(tag)
            del self.skipped[index:]
        if tag in {"p", "div", "li", "blockquote", "pre"} and not self.skipped:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skipped:
            self.parts.append(data)


def inspect_text(content: str | None) -> dict:
    parser = ProseParser()
    parser.feed(content or "")
    parser.close()
    prose = "\n".join(" ".join(line.split()) for line in "".join(parser.parts).splitlines()
                      if line.strip() and line.strip() not in PLACEHOLDERS and not line.lstrip().startswith(">"))
    if prose in PLACEHOLDERS:
        prose = ""
    prose_without_links = URL.sub("", prose).strip(" \n.,，。:：()（）[]")
    return {"text": comment_text(content), "prose": prose, "media": parser.media,
            "links": len(URL.findall(prose)), "link_only": bool(prose) and not prose_without_links,
            "attribution_hint": bool(ATTRIBUTION.search(prose)),
            "quoted_or_code": parser.quoted_or_code or "```" in (content or "") or any(line.lstrip().startswith(">") for line in (content or "").splitlines()),
            "has_prose": bool(prose_without_links)}


def identity(value: str) -> str:
    return hashlib.sha256(value.casefold().encode()).hexdigest()[:16]


def known(value):
    return int(value) if value is not None and value >= 0 else None


def date_for(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, LOCAL_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")


def stratum_for(row: dict) -> str:
    year, month = row["period"].split("-")
    quarter = f"{year}-Q{(int(month) - 1) // 3 + 1}"
    node_group = "coding" if row["node"] in CODING_NODES else "other"
    replies = row["replies"]
    reply_band = "unknown" if replies is None else "0" if replies == 0 else "1-19" if replies < 20 else "20+"
    return f"{quarter}/{node_group}/{reply_band}"


def load_candidates(tokens: sqlite3.Connection, source: sqlite3.Connection, start: str, end: str):
    candidates, exclusions = [], Counter()
    scanned = 0
    # Scan only the compact title cache. Body/comments are fetched by primary key
    # or ix_comment_topic_id after selection, never by a full comment-table scan.
    for topic_id, title in tokens.execute("SELECT topic_id, title FROM title_tokens ORDER BY topic_id"):
        scanned += 1
        if not candidate_tools(title):
            continue
        row = source.execute("""SELECT id, title, node, author, create_at, clicks,
                                       reply_count, favorite_count, thank_count
                                FROM topic WHERE id = ?""", (topic_id,)).fetchone()
        if row is None:
            exclusions["missing_source"] += 1
            continue
        _, current_title, node, author, created, clicks, replies, favorites, thanks = row
        tools = candidate_tools(current_title)
        if not tools:
            exclusions["changed_title"] += 1
            continue
        if not created or created < 1262304000 or clicks is None or clicks < 0:
            exclusions["invalid_or_inaccessible"] += 1
            continue
        date = date_for(created)
        if not start <= date[:7] <= end:
            exclusions["outside_period"] += 1
            continue
        if node in EXCLUDED_NODES:
            exclusions["trading_or_promotional_node"] += 1
            continue
        record = {"id": topic_id, "title": current_title, "node": node, "author_key": identity(author),
                  "date": date, "period": date[:7], "tools": tools, "replies": known(replies),
                  "favorites": known(favorites), "thanks": known(thanks)}
        record["stratum"] = stratum_for(record)
        candidates.append(record)
    return candidates, {"title_cache_rows_scanned": scanned, "excluded": dict(exclusions)}


def stratified_sample(candidates: list[dict], sample_size: int, seed: int):
    strata = defaultdict(list)
    for row in candidates:
        strata[row["stratum"]].append(row)
    target = min(sample_size, len(candidates))
    if target < len(strata):
        raise ValueError(f"Sample needs at least {len(strata)} posts to cover every stratum")
    quotas = {key: 1 for key in sorted(strata)}
    for _ in range(target - len(quotas)):
        key = max((key for key in quotas if quotas[key] < len(strata[key])),
                  key=lambda key: (math.sqrt(len(strata[key])) / (quotas[key] + 1), key))
        quotas[key] += 1
    sample, coverage = [], []
    for key in sorted(strata):
        population, selected = len(strata[key]), quotas[key]
        rows = sorted(strata[key], key=lambda row: hashlib.sha256(f"{seed}:{row['id']}".encode()).digest())
        sample.extend({**row, "selection": "stratified", "inclusion_probability": selected / population,
                       "design_weight": population / selected} for row in rows[:selected])
        coverage.append({"stratum": key, "population": population, "sample": selected})
    return sample, coverage


def read_thread(source: sqlite3.Connection, row: dict, cutoff: int, has_supplements=False) -> dict:
    content, = source.execute("SELECT content FROM topic WHERE id = ?", (row["id"],)).fetchone()
    body = inspect_text(content)
    supplements = []
    if has_supplements:
        for extra, created in source.execute(
            "SELECT content, create_at FROM topic_supplement WHERE topic_id = ? ORDER BY create_at, content", (row["id"],)
        ):
            if created and created >= cutoff:
                continue
            dated = bool(created and created >= 1262304000)
            supplements.append({"date": date_for(created) if dated else None,
                                "temporal_status": "in_window" if dated else "undated",
                                **inspect_text(extra)})
    comments, unavailable = [], Counter()
    for comment_id, author, content, thanks, created, floor in source.execute(
        "SELECT id, commenter, content, thank_count, create_at, no FROM comment WHERE topic_id = ? ORDER BY no, id",
        (row["id"],),
    ):
        if not created or created < 1262304000 or created >= cutoff:
            unavailable["invalid_or_after_cutoff"] += 1
            continue
        text = inspect_text(content)
        comments.append({"id": comment_id, "author_key": identity(author), "is_op": identity(author) == row["author_key"],
                         "date": date_for(created), "floor": floor, "thanks": known(thanks), **text})
    normalized = [" ".join(comment["prose"].casefold().split()) for comment in comments if comment["has_prose"]]
    counts = Counter(normalized)
    digest = hashlib.sha256(json.dumps({"body": body, "supplements": supplements, "comments": comments}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return {**row, "url": f"https://www.v2ex.com/t/{row['id']}", "body": body, "supplements": supplements, "comments": comments,
            "source_digest": digest, "review_status": "pending", "relevant_experience": None,
            "reviewed_claims": [],
            "coverage": {"stored_comments_in_window": len(comments), "comments_with_prose": len(normalized),
                         "comment_users": len({comment['author_key'] for comment in comments}),
                         "media_comments": sum(bool(comment['media']) for comment in comments),
                         "attribution_hint_comments": sum(comment['attribution_hint'] for comment in comments),
                         "quoted_or_code_comments": sum(comment['quoted_or_code'] for comment in comments),
                         "duplicate_prose_comments": sum(count - 1 for count in counts.values()),
                         "reply_snapshot_difference": None if row["replies"] is None else row["replies"] - len(comments),
                         **unavailable}}


def distribution(rows, field):
    return dict(sorted(Counter(row[field] for row in rows).items()))


def build_corpus(source, tokens, *, start="2021-01", end="2026-08", sample_size=200, seed=20260905):
    candidates, audit = load_candidates(tokens, source, start, end)
    sample, strata = stratified_sample(candidates, sample_size, seed)
    year, month = map(int, end.split("-"))
    cutoff = int(datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=LOCAL_TIMEZONE).timestamp())
    has_supplements = source.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'topic_supplement'").fetchone() is not None
    selected_ids = {row["id"] for row in sample}
    case_rows = {}
    for metric in ("favorites", "thanks"):
        eligible = [row for row in candidates if row[metric] is not None and row[metric] >= 5]
        for row in sorted(eligible, key=lambda row: (-row[metric], row["id"]))[:5]:
            case_rows.setdefault(row["id"], {**row, "selection": "high_interaction_case", "case_metrics": []})["case_metrics"].append(metric)
    records = [read_thread(source, row, cutoff, has_supplements) for row in sample]
    for row in records:
        if row["id"] in case_rows:
            row["case_metrics"] = case_rows[row["id"]]["case_metrics"]
    cases = [read_thread(source, row, cutoff, has_supplements) for topic_id, row in case_rows.items() if topic_id not in selected_ids]
    summary = {
        "rule_version": RULE_VERSION, "seed": seed, "start": start, "end": end,
        "source_max_topic_id": source.execute("SELECT max(id) FROM topic").fetchone()[0],
        "title_cache_max_topic_id": tokens.execute("SELECT max(topic_id) FROM title_tokens").fetchone()[0],
        "candidate_count": len(candidates), "sample_count": len(records), "extra_cases": len(cases),
        "fully_annotated_threads": 0, "strata": strata, "exclusion_nodes": sorted(EXCLUDED_NODES), **audit,
        "body_with_prose": sum(row["body"]["has_prose"] for row in records),
        "supplements": sum(len(row["supplements"]) for row in records),
        "undated_supplements": sum(extra["temporal_status"] == "undated" for row in records for extra in row["supplements"]),
        "sample_comments": sum(len(row["comments"]) for row in records),
        "comments_with_prose": sum(row["coverage"]["comments_with_prose"] for row in records),
        "media_comments": sum(row["coverage"]["media_comments"] for row in records),
        "quoted_or_code_comments": sum(row["coverage"]["quoted_or_code_comments"] for row in records),
        "attribution_hint_comments": sum(row["coverage"]["attribution_hint_comments"] for row in records),
        "bodies_with_links": sum(bool(row["body"]["links"]) for row in records),
        "link_only_bodies": sum(row["body"]["link_only"] for row in records),
        "duplicate_prose_comments_within_thread": sum(row["coverage"]["duplicate_prose_comments"] for row in records),
        "threads_with_reply_snapshot_difference": sum(row["coverage"]["reply_snapshot_difference"] not in (None, 0) for row in records),
        "candidates_by_node": distribution(candidates, "node"), "sample_by_node": distribution(records, "node"),
        "candidates_by_period": distribution(candidates, "period"), "sample_by_period": distribution(records, "period"),
        "candidate_authors": len({row["author_key"] for row in candidates}),
        "sample_authors": len({row["author_key"] for row in records}),
    }
    return summary, records, cases, candidates


def validate_review(records: list[dict], review: dict) -> dict:
    by_id = {row["id"]: row for row in records}
    units, thread_ids = set(), set()
    for item in review.get("evidence", []):
        row = by_id.get(item["topic_id"])
        if row is None:
            raise ValueError(f"Reviewed thread missing from corpus: {item['topic_id']}")
        if item["code"] not in review["codebook"]:
            raise ValueError(f"Unknown review code: {item['code']}")
        if item["unit"] == "comment":
            comment = next((comment for comment in row["comments"] if comment["id"] == item["comment_id"]), None)
            text = comment["prose"] if comment else ""
        elif item["unit"] == "body":
            text = row["body"]["prose"]
        elif item["unit"] == "title":
            text = row["title"]
        else:
            raise ValueError(f"Unknown evidence unit: {item['unit']}")
        if not item.get("quote") or item["quote"] not in text:
            raise ValueError(f"Evidence no longer matches source: {item['topic_id']} / {item.get('comment_id', item['unit'])}")
        units.add((item["topic_id"], item["unit"], item.get("comment_id")))
        thread_ids.add(row["id"])
    return {"evidence_checked_threads": len(thread_ids), "evidence_checked_units": len(units),
            "evidence_items": len(review.get("evidence", [])),
            "verified_source_digests": {str(topic_id): by_id[topic_id]["source_digest"] for topic_id in sorted(thread_ids)},
            "review_note": "Only cited passages checked; not full annotation of the 200-thread sample."}


def write_json(path: Path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "v2ex.sqlite")
    parser.add_argument("--tokens", type=Path, default=ROOT / "analysis/content_tokens.sqlite")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--start", default="2021-01")
    parser.add_argument("--end", default="2026-08")
    parser.add_argument("--sample-size", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20260905)
    parser.add_argument("--review", type=Path, help="Validate a reviewed evidence JSON against this corpus")
    args = parser.parse_args()
    for period in (args.start, args.end):
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period):
            parser.error("Periods must be YYYY-MM")
    if args.start > args.end or args.sample_size < 1:
        parser.error("Invalid range or sample size")
    if args.output.resolve().is_relative_to((ROOT / "analysis/v2ex-analysis/public").resolve()):
        parser.error("The review corpus must not be placed in public/")
    args.output.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"{args.source.resolve().as_uri()}?mode=ro", uri=True)
    tokens = sqlite3.connect(f"{args.tokens.resolve().as_uri()}?mode=ro", uri=True)
    try:
        source.execute("BEGIN")
        summary, records, cases, candidates = build_corpus(
            source, tokens, start=args.start, end=args.end, sample_size=args.sample_size, seed=args.seed)
    finally:
        source.close()
        tokens.close()
    write_json(args.output / "summary.json", summary)
    write_json(args.output / "candidates.json", candidates)
    # Keep annotations in a separate file: rerunning this export cannot erase a review.
    write_json(args.output / "sample.json", records)
    write_json(args.output / "cases.json", cases)
    if args.review:
        review = json.loads(args.review.read_text(encoding="utf-8"))
        checked = validate_review(records + cases, review)
        write_json(args.output / "review-check.json", checked)
        print(json.dumps({key: value for key, value in checked.items() if key != "verified_source_digests"}, ensure_ascii=False, indent=2))
    print(json.dumps({key: value for key, value in summary.items() if not isinstance(value, (list, dict))}, ensure_ascii=False, indent=2))
    print(f"Local review corpus: {args.output}")


if __name__ == "__main__":
    main()
