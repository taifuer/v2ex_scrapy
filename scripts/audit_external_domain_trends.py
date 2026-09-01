#!/usr/bin/env python3
"""Build an offline pilot report for external-link domain trends."""

from __future__ import annotations

import argparse
import html
import ipaddress
import json
import re
import sqlite3
from collections import Counter, defaultdict, deque
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent.parent
SOURCE_DB = ROOT / "v2ex.sqlite"
PUBLIC_DIR = ROOT / "analysis" / "v2ex-analysis" / "public"
DEFAULT_OUTPUT = ROOT / "analysis" / "data_audits" / "external-domains.json"
MIN_VALID_CREATE_AT = 1262304000
URL_RE = re.compile(r"https?://[^\s<>\"']+|www\.[^\s<>\"']+", re.IGNORECASE)
HREF_RE = re.compile(r"href\s*=\s*([\"'])(.*?)\1", re.IGNORECASE | re.DOTALL)
TRAILING_URL_PUNCTUATION = ").,;:!?]}，。；：！？】》」』"
EXCLUDED_NODES = frozenset({"promotions", "all4all", "exchange", "free", "deals"})
VALID_HOST_LABEL_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
DOMAIN_ALIASES = {
    "twitter.com": "x.com",
    "mobile.twitter.com": "x.com",
    "youtu.be": "youtube.com",
    "m.youtube.com": "youtube.com",
    "raw.githubusercontent.com": "github.com",
    "gist.github.com": "github.com",
    "githubusercontent.com": "github.com",
    "m.bilibili.com": "bilibili.com",
    "b23.tv": "bilibili.com",
    "itunes.apple.com": "apps.apple.com",
    "chrome.google.com": "chromewebstore.google.com",
}
COLLAPSED_SUFFIXES = (
    "github.com",
    "github.io",
    "youtube.com",
    "bilibili.com",
    "zhihu.com",
    "juejin.cn",
    "csdn.net",
    "weibo.com",
    "reddit.com",
    "medium.com",
    "segmentfault.com",
    "stackoverflow.com",
)
DOMAIN_LABELS = {
    "github.com": "GitHub",
    "youtube.com": "YouTube",
    "bilibili.com": "哔哩哔哩",
    "zhihu.com": "知乎",
    "juejin.cn": "稀土掘金",
    "csdn.net": "CSDN",
    "x.com": "X / Twitter",
    "weibo.com": "微博",
    "reddit.com": "Reddit",
    "medium.com": "Medium",
    "segmentfault.com": "SegmentFault",
    "stackoverflow.com": "Stack Overflow",
    "mp.weixin.qq.com": "微信公众号",
}
DOMAIN_CATEGORIES = {
    "github.com": "code",
    "github.io": "code",
    "gitee.com": "code",
    "gitlab.com": "code",
    "npmjs.com": "code",
    "pypi.org": "code",
    "huggingface.co": "code",
    "cdn.jsdelivr.net": "code",
    "stackoverflow.com": "technical-content",
    "segmentfault.com": "technical-content",
    "juejin.cn": "technical-content",
    "csdn.net": "technical-content",
    "cnblogs.com": "technical-content",
    "infoq.cn": "technical-content",
    "sspai.com": "technical-content",
    "mp.weixin.qq.com": "social-content",
    "zhihu.com": "social-content",
    "x.com": "social-content",
    "weibo.com": "social-content",
    "reddit.com": "social-content",
    "medium.com": "social-content",
    "douban.com": "social-content",
    "jianshu.com": "social-content",
    "t.me": "social-content",
    "youtube.com": "video",
    "bilibili.com": "video",
    "vimeo.com": "video",
    "youku.com": "video",
    "douyin.com": "video",
    "docs.google.com": "documents",
    "docs.qq.com": "documents",
    "yuque.com": "documents",
    "shimo.im": "documents",
    "notion.so": "documents",
    "feishu.cn": "documents",
    "apps.apple.com": "app-distribution",
    "play.google.com": "app-distribution",
    "chromewebstore.google.com": "app-distribution",
    "testflight.apple.com": "app-distribution",
    "arxiv.org": "research",
    "paperswithcode.com": "research",
    "pan.baidu.com": "file-sharing",
    "drive.google.com": "file-sharing",
    "aliyundrive.com": "file-sharing",
    "lanzou.com": "file-sharing",
    "m.tb.cn": "commerce",
    "item.taobao.com": "commerce",
    "2.taobao.com": "commerce",
    "market.m.taobao.com": "commerce",
    "item.jd.com": "commerce",
    "h5.m.goofish.com": "commerce",
}
INFORMATION_CATEGORIES = frozenset(
    {
        "code",
        "technical-content",
        "social-content",
        "video",
        "documents",
        "app-distribution",
        "research",
        "file-sharing",
    }
)
IMAGE_SUFFIXES = (
    "imgur.com",
    "sinaimg.cn",
    "loli.net",
    "ax1x.com",
    "zhimg.com",
    "twimg.com",
    "qpic.cn",
    "v2ex.co",
    "nodeimage.com",
)


def default_end_period(public_dir: Path) -> str:
    path = public_dir / "dynamic-overview.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return str(payload["metadata"]["default_end_period"])


def canonical_domain(value: str) -> str | None:
    candidate = html.unescape(value).strip().rstrip(TRAILING_URL_PUNCTUATION)
    if candidate.startswith("www."):
        candidate = "https://" + candidate
    elif candidate.startswith("//"):
        candidate = "https:" + candidate
    try:
        parsed = urlsplit(candidate)
        host = (parsed.hostname or "").casefold().rstrip(".")
    except ValueError:
        return None
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]
    if host == "localhost" or host.endswith(".localhost"):
        return None
    try:
        ipaddress.ip_address(host)
        return None
    except ValueError:
        pass
    if host == "v2ex.com" or host.endswith(".v2ex.com"):
        return None
    if host.endswith(".md") or any(
        VALID_HOST_LABEL_RE.fullmatch(label) is None for label in host.split(".")
    ):
        return None
    host = DOMAIN_ALIASES.get(host, host)
    for suffix in COLLAPSED_SUFFIXES:
        if host == suffix or host.endswith("." + suffix):
            return suffix
    return host


def domain_category(domain: str) -> str:
    direct = DOMAIN_CATEGORIES.get(domain)
    if direct:
        return direct
    if any(domain == suffix or domain.endswith("." + suffix) for suffix in IMAGE_SUFFIXES):
        return "images"
    if re.search(r"(?:^|[.-])(?:img|image|images|pic|pics|upload)(?:[.-]|$)", domain):
        return "images"
    if re.search(r"(?:^|[.-])cdn(?:[.-]|$)", domain):
        return "infrastructure"
    return "other"


def extract_external_urls(text: str) -> set[str]:
    if not text:
        return set()
    decoded = html.unescape(text)
    values = {match.group(2) for match in HREF_RE.finditer(decoded)}
    values.update(match.group(0) for match in URL_RE.finditer(decoded))
    return {
        value.strip().rstrip(TRAILING_URL_PUNCTUATION)
        for value in values
        if value.strip()
    }


def shift_month(period: str, months: int) -> str:
    year, month = map(int, period.split("-"))
    absolute = year * 12 + month - 1 + months
    return f"{absolute // 12:04d}-{absolute % 12 + 1:02d}"


def iter_source_topics(source_db: Path, batch_size: int):
    last_id = 0
    while True:
        source = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)
        rows = source.execute(
            """
            SELECT id, author, title, node, content,
                   strftime('%Y-%m', create_at, 'unixepoch', '+8 hours') AS period
            FROM topic
            WHERE clicks >= 0 AND create_at >= ? AND id > ?
            ORDER BY id
            LIMIT ?
            """,
            (MIN_VALID_CREATE_AT, last_id, batch_size),
        ).fetchall()
        source.close()
        if not rows:
            return
        yield from rows
        last_id = int(rows[-1][0])
        if len(rows) < batch_size:
            return


def build_domain_report(
    source_db: Path,
    end_period: str,
    *,
    minimum_topics: int,
    minimum_authors: int,
    minimum_nodes: int,
    top_limit: int,
    batch_size: int = 5000,
) -> dict:
    domain_topics = Counter()
    domain_links = Counter()
    period_counts: dict[str, Counter] = defaultdict(Counter)
    domain_authors: dict[str, set[str]] = defaultdict(set)
    domain_nodes: dict[str, Counter] = defaultdict(Counter)
    examples: dict[str, deque] = defaultdict(lambda: deque(maxlen=5))
    category_topics = Counter()
    category_period_counts: dict[str, Counter] = defaultdict(Counter)
    eligible_topics = 0
    topics_with_external_links = 0
    excluded_topics = 0

    for topic_id, author, title, node, content, period in iter_source_topics(
        source_db, max(1, batch_size)
    ):
        if not period or str(period) > end_period:
            continue
        normalized_node = str(node or "").casefold()
        if normalized_node in EXCLUDED_NODES:
            excluded_topics += 1
            continue
        eligible_topics += 1
        urls = extract_external_urls(f"{title or ''}\n{content or ''}")
        domains_by_url = {
            url: domain
            for url in urls
            if (domain := canonical_domain(url)) is not None
        }
        if not domains_by_url:
            continue
        topics_with_external_links += 1
        per_topic_domains = Counter(domains_by_url.values())
        per_topic_categories = {domain_category(domain) for domain in per_topic_domains}
        for category in per_topic_categories:
            category_topics[category] += 1
            category_period_counts[category][str(period)] += 1
        for domain, link_count in per_topic_domains.items():
            domain_topics[domain] += 1
            domain_links[domain] += link_count
            period_counts[domain][str(period)] += 1
            if author:
                domain_authors[domain].add(str(author))
            if node:
                domain_nodes[domain][str(node)] += 1
            examples[domain].append(
                {
                    "id": int(topic_id),
                    "period": str(period),
                    "title": str(title),
                    "node": str(node or ""),
                }
            )
    selected = {
        domain
        for domain, count in domain_topics.items()
        if count >= minimum_topics
        and len(domain_authors[domain]) >= minimum_authors
        and len(domain_nodes[domain]) >= minimum_nodes
    }
    current_start = shift_month(end_period, -11)
    previous_start = shift_month(end_period, -23)
    previous_end = shift_month(end_period, -12)
    domain_rows = []
    for domain in selected:
        counts = period_counts[domain]
        periods = sorted(counts)
        recent = sum(
            count
            for period, count in counts.items()
            if current_start <= period <= end_period
        )
        previous = sum(
            count
            for period, count in counts.items()
            if previous_start <= period <= previous_end
        )
        domain_rows.append(
            {
                "domain": domain,
                "label": DOMAIN_LABELS.get(domain, domain),
                "category": domain_category(domain),
                "topics": domain_topics[domain],
                "links": domain_links[domain],
                "authors": len(domain_authors[domain]),
                "nodes": len(domain_nodes[domain]),
                "first_period": periods[0],
                "last_period": periods[-1],
                "recent_12m": recent,
                "previous_12m": previous,
                "change": recent - previous,
                "top_nodes": [
                    {"node": node, "topics": count}
                    for node, count in domain_nodes[domain].most_common(5)
                ],
                "examples": list(reversed(examples[domain])),
                "rows": dict(sorted(counts.items())),
            }
        )
    domain_rows.sort(
        key=lambda row: (-row["topics"], row["domain"].casefold(), row["domain"])
    )

    annual: dict[str, Counter] = defaultdict(Counter)
    for domain in selected:
        for period, count in period_counts[domain].items():
            annual[period[:4]][domain] += count
    annual_top = {
        year: [
            {
                "domain": domain,
                "label": DOMAIN_LABELS.get(domain, domain),
                "topics": count,
            }
            for domain, count in counts.most_common(top_limit)
        ]
        for year, counts in sorted(annual.items())
    }
    information_domains = [
        row for row in domain_rows if row["category"] in INFORMATION_CATEGORIES
    ]
    category_rows = []
    for category, topics in category_topics.items():
        counts = category_period_counts[category]
        recent = sum(
            count for period, count in counts.items() if current_start <= period <= end_period
        )
        previous = sum(
            count
            for period, count in counts.items()
            if previous_start <= period <= previous_end
        )
        category_rows.append(
            {
                "category": category,
                "topics": topics,
                "recent_12m": recent,
                "previous_12m": previous,
                "change": recent - previous,
                "rows": dict(sorted(counts.items())),
            }
        )
    category_rows.sort(key=lambda row: (-row["topics"], row["category"]))
    return {
        "metadata": {
            "end_period": end_period,
            "eligible_topics": eligible_topics,
            "topics_with_external_links": topics_with_external_links,
            "coverage_rate": round(
                topics_with_external_links / max(1, eligible_topics), 4
            ),
            "excluded_nodes": sorted(EXCLUDED_NODES),
            "excluded_topics": excluded_topics,
            "minimum_topics": minimum_topics,
            "minimum_authors": minimum_authors,
            "minimum_nodes": minimum_nodes,
            "selected_domains": len(domain_rows),
            "method": (
                "Counts distinct topics containing each external HTTP(S) domain in "
                "the topic title or body; does not fetch linked pages."
            ),
        },
        "domains": domain_rows,
        "top_domains": domain_rows[:top_limit],
        "information_domains": information_domains,
        "top_information_domains": information_domains[:top_limit],
        "categories": category_rows,
        "annual_top": annual_top,
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
        description="Audit external-link domain trends without fetching linked pages."
    )
    parser.add_argument("--source-db", type=Path, default=SOURCE_DB)
    parser.add_argument("--public-dir", type=Path, default=PUBLIC_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--end-period")
    parser.add_argument("--minimum-topics", type=int, default=50)
    parser.add_argument("--minimum-authors", type=int, default=20)
    parser.add_argument("--minimum-nodes", type=int, default=3)
    parser.add_argument("--top-limit", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=5000)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    end_period = args.end_period or default_end_period(args.public_dir)
    report = build_domain_report(
        args.source_db,
        end_period,
        minimum_topics=max(1, args.minimum_topics),
        minimum_authors=max(1, args.minimum_authors),
        minimum_nodes=max(1, args.minimum_nodes),
        top_limit=max(1, args.top_limit),
        batch_size=max(1, args.batch_size),
    )
    write_report(args.output, report)
    metadata = report["metadata"]
    print(
        f"Scanned {metadata['eligible_topics']:,} eligible topics through {end_period}; "
        f"{metadata['topics_with_external_links']:,} contain external links "
        f"({metadata['coverage_rate']:.1%})."
    )
    print(
        f"Selected {metadata['selected_domains']:,} domains meeting coverage thresholds."
    )
    for row in report["top_information_domains"][:10]:
        print(f"  {row['label']}: {row['topics']:,} topics")
    print(f"Report written to {args.output}")


if __name__ == "__main__":
    main()
