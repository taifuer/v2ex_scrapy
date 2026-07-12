import argparse
import hashlib
import heapq
import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = ROOT / "analysis"
SOURCE_DB = ROOT / "v2ex.sqlite"
ANALYTICS_DB = ANALYSIS_DIR / "analytics.sqlite"
PUBLIC_DIR = ANALYSIS_DIR / "v2ex-analysis" / "public"
MIN_VALID_CREATE_AT = 1262304000
LOCAL_TIMEZONE = timezone(timedelta(hours=8))
TOP_TAG_LIMIT = 500
REPRESENTATIVE_POSTS_PER_MONTH = 30
INTERACTION_POST_RANKING_LIMIT = 100
COMMENT_RANKING_LIMIT = 300
FIRST_REPLY_BUCKETS = ("10m", "1h", "6h", "24h", "3d", "7d", "none")
COMMENT_AGE_BUCKETS = ("10m", "1h", "6h", "24h", "3d", "7d")
EXCLUDED_THANK_USERS = frozenset({"usdc"})
EXCLUDED_REPRESENTATIVE_NODES = frozenset({"promotions"})
MEMBER_RANKING_LIMIT = 30
TAG_DETAIL_BUCKET_COUNT = 16
TAG_DETAIL_LIST_LIMIT = 15
ANALYTICS_SCHEMA_VERSION = 3


class CommentTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag in {"br", "div", "p", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str):
        if tag in {"div", "p", "li"}:
            self.parts.append("\n")

    def handle_data(self, data: str):
        self.parts.append(data)

    def text(self) -> str:
        return "\n".join(
            line for line in (" ".join(part.split()) for part in "".join(self.parts).splitlines())
            if line
        )


def comment_text(content: str | None) -> str:
    parser = CommentTextParser()
    parser.feed(content or "")
    parser.close()
    return parser.text()


def load_json(path: Path):
    with path.open(encoding="utf-8") as fp:
        return json.load(fp)


def write_json(path: Path, payload):
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    with temp_path.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, separators=(",", ":"))
    temp_path.replace(path)


def source_fingerprint() -> dict[str, int]:
    stat = SOURCE_DB.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def write_manifest(component: str, full_build: bool = False):
    manifest_path = PUBLIC_DIR / "dynamic-manifest.json"
    manifest = load_json(manifest_path) if manifest_path.exists() else {
        "schema_version": ANALYTICS_SCHEMA_VERSION,
        "components": {},
    }
    generated_at = datetime.now(LOCAL_TIMEZONE).isoformat(timespec="seconds")
    manifest["schema_version"] = ANALYTICS_SCHEMA_VERSION
    manifest["generated_at"] = generated_at
    manifest["components"][component] = generated_at
    if full_build:
        manifest["full_build_source"] = source_fingerprint()
    manifest["files"] = {
        path.name: path.stat().st_size
        for path in sorted(PUBLIC_DIR.glob("dynamic-*.json"))
        if path.name != manifest_path.name
    }
    write_json(manifest_path, manifest)


def source_unchanged_since_full_build() -> bool:
    manifest_path = PUBLIC_DIR / "dynamic-manifest.json"
    if not manifest_path.exists():
        return False
    manifest = load_json(manifest_path)
    return (
        manifest.get("schema_version") == ANALYTICS_SCHEMA_VERSION
        and manifest.get("full_build_source") == source_fingerprint()
    )


def synonym_map() -> dict[str, str]:
    result: dict[str, str] = {}
    for canonical, variants in load_json(ANALYSIS_DIR / "tag_synonyms.json").items():
        result[canonical.casefold()] = canonical
        for variant in variants:
            result[str(variant).casefold()] = canonical
    return result


def canonical_tag(tag: str, synonyms: dict[str, str]) -> str:
    value = tag.strip()
    return synonyms.get(value.casefold(), value)


def normalize_tags(raw_tags, synonyms: dict[str, str], stopwords: set[str]) -> set[str]:
    normalized = {
        canonical_tag(str(tag), synonyms) for tag in raw_tags if str(tag).strip()
    }
    return {tag for tag in normalized if tag.casefold() not in stopwords}


def month_for(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, LOCAL_TIMEZONE).strftime("%Y-%m")


def first_reply_bucket(delay: int | None) -> str:
    if delay is None:
        return "none"
    for label, upper_bound in (("10m", 600), ("1h", 3600), ("6h", 21600),
                               ("24h", 86400), ("3d", 259200), ("7d", 604800)):
        if delay < upper_bound:
            return label
    return "none"


def comment_age_bucket(delay: int) -> str | None:
    for label, upper_bound in (("10m", 600), ("1h", 3600), ("6h", 21600),
                               ("24h", 86400), ("3d", 259200), ("7d", 604800)):
        if delay < upper_bound:
            return label
    return None


def matches_group(title: str, node: str, tags: set[str], group: dict) -> bool:
    title_folded = title.casefold()
    node_folded = node.casefold()
    tag_values = {tag.casefold() for tag in tags}
    if node_folded in {item.casefold() for item in group.get("nodes", [])}:
        return True
    return any(
        keyword.casefold() in title_folded or keyword.casefold() in tag_values
        for keyword in group.get("keywords", [])
    )


def engagement_score(row: sqlite3.Row) -> float:
    return (
        max(0, row["reply_count"])
        + max(0, row["favorite_count"]) * 3
        + max(0, row["thank_count"]) * 5
        + max(0, row["votes"]) * 2
        + math.log1p(max(0, row["clicks"]))
    )


def tag_detail_bucket(tag: str) -> str:
    return hashlib.sha1(tag.encode("utf-8")).hexdigest()[0]


def update_tag_details():
    topics_path = PUBLIC_DIR / "dynamic-topics.json"
    topics_output = load_json(topics_path)
    tag_totals = {item["tag"]: int(item["total"]) for item in topics_output["tags"]}
    selected_tags = set(tag_totals)
    synonyms = synonym_map()
    tag_stopwords = {
        str(tag).casefold() for tag in load_json(ANALYSIS_DIR / "tag_stopwords.json")
    }
    related = defaultdict(lambda: defaultdict(int))
    nodes = defaultdict(lambda: defaultdict(int))
    authors = defaultdict(lambda: defaultdict(int))

    source = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    for row in source.execute(
        """
        SELECT author, node, tag
        FROM topic
        WHERE clicks >= 0 AND create_at >= ?
        ORDER BY id
        """,
        (MIN_VALID_CREATE_AT,),
    ):
        try:
            raw_tags = json.loads(row["tag"] or "[]")
        except json.JSONDecodeError:
            raw_tags = []
        normalized_tags = normalize_tags(raw_tags, synonyms, tag_stopwords)
        detail_tags = normalized_tags & selected_tags
        if not detail_tags:
            continue
        node = row["node"] or "未分类"
        for tag in detail_tags:
            nodes[tag][node] += 1
            if row["author"]:
                authors[tag][row["author"]] += 1
            for other in detail_tags:
                if other != tag:
                    related[tag][other] += 1
    source.close()

    buckets = {format(index, "x"): {"details": {}} for index in range(TAG_DETAIL_BUCKET_COUNT)}
    index_output = {"tags": {}}
    for tag in sorted(selected_tags):
        bucket = tag_detail_bucket(tag)
        detail = {
            "tag": tag,
            "total": tag_totals[tag],
            "related": sorted(related[tag].items(), key=lambda item: (-item[1], item[0]))[:TAG_DETAIL_LIST_LIMIT],
            "nodes": sorted(nodes[tag].items(), key=lambda item: (-item[1], item[0]))[:TAG_DETAIL_LIST_LIMIT],
            "authors": sorted(authors[tag].items(), key=lambda item: (-item[1], item[0]))[:TAG_DETAIL_LIST_LIMIT],
        }
        buckets[bucket]["details"][tag] = detail
        index_output["tags"][tag] = {"bucket": bucket, "total": tag_totals[tag]}

    write_json(PUBLIC_DIR / "dynamic-tag-detail-index.json", index_output)
    for bucket, payload in buckets.items():
        write_json(PUBLIC_DIR / f"dynamic-tag-details-{bucket}.json", payload)
    write_manifest("tag_details")
    print(f"Updated tag details: {len(selected_tags)} tags across {len(buckets)} shards")


def build_member_rank_rows(source: sqlite3.Connection, limit: int = MEMBER_RANKING_LIMIT) -> list[list]:
    source.execute("PRAGMA temp_store = FILE")
    source.executescript(
        f"""
        DROP TABLE IF EXISTS temp.member_topic_period;
        DROP TABLE IF EXISTS temp.member_comment_period;
        CREATE TEMP TABLE member_topic_period AS
        SELECT strftime('%Y-%m', create_at, 'unixepoch', '+8 hours') AS period,
               author AS username,
               COUNT(*) AS topic_count,
               SUM(CASE WHEN thank_count > 0 THEN thank_count ELSE 0 END) AS thank_count
        FROM topic
        WHERE clicks >= 0 AND create_at >= {MIN_VALID_CREATE_AT} AND author != ''
        GROUP BY 1, 2;
        CREATE TEMP TABLE member_comment_period AS
        SELECT strftime('%Y-%m', create_at, 'unixepoch', '+8 hours') AS period,
               commenter AS username,
               COUNT(*) AS comment_count,
               SUM(CASE WHEN thank_count > 0 THEN thank_count ELSE 0 END) AS thank_count
        FROM comment
        WHERE create_at >= {MIN_VALID_CREATE_AT} AND commenter != ''
        GROUP BY 1, 2;
        """
    )

    rows: list[list] = []

    def append_rankings(grain: str, metric: str, values_sql: str, parameters=()):
        ranking_sql = f"""
            WITH values_by_member AS ({values_sql}),
            ranked AS (
                SELECT period, username, value,
                       ROW_NUMBER() OVER (
                           PARTITION BY period
                           ORDER BY value DESC, username COLLATE NOCASE
                       ) AS position
                FROM values_by_member
                WHERE value > 0
            )
            SELECT period, position, username, value
            FROM ranked
            WHERE position <= ?
            ORDER BY period, position
        """
        rows.extend(
            [grain, period, metric, int(position), username, int(value)]
            for period, position, username, value in source.execute(
                ranking_sql, (*parameters, limit)
            )
        )

    current_period = datetime.now(LOCAL_TIMEZONE).strftime("%Y-%m")
    for grain, period_sql, period_filter in (
        ("month", "period", ""),
        ("year", "substr(period, 1, 4)", f"WHERE period < '{current_period}'"),
    ):
        append_rankings(
            grain,
            "topics",
            f"""
                SELECT {period_sql} AS period, username, SUM(topic_count) AS value
                FROM member_topic_period
                {period_filter}
                GROUP BY 1, 2
            """,
        )
        append_rankings(
            grain,
            "comments",
            f"""
                SELECT {period_sql} AS period, username, SUM(comment_count) AS value
                FROM member_comment_period
                {period_filter}
                GROUP BY 1, 2
            """,
        )
        excluded = ",".join("?" for _ in EXCLUDED_THANK_USERS)
        thanks_period_filter = f"AND period < '{current_period}'" if grain == "year" else ""
        append_rankings(
            grain,
            "thanks",
            f"""
                SELECT {period_sql} AS period, username, SUM(thank_count) AS value
                FROM (
                    SELECT period, username, thank_count FROM member_topic_period
                    UNION ALL
                    SELECT period, username, thank_count FROM member_comment_period
                )
                WHERE LOWER(username) NOT IN ({excluded})
                  {thanks_period_filter}
                GROUP BY 1, 2
            """,
            tuple(EXCLUDED_THANK_USERS),
        )

    source.executescript(
        """
        DROP TABLE temp.member_topic_period;
        DROP TABLE temp.member_comment_period;
        """
    )
    return rows


def create_schema(conn: sqlite3.Connection):
    conn.executescript(
        """
        DROP TABLE IF EXISTS period_metrics;
        DROP TABLE IF EXISTS activity_period;
        DROP TABLE IF EXISTS node_period;
        DROP TABLE IF EXISTS tag_period;
        DROP TABLE IF EXISTS title_token_period;
        DROP TABLE IF EXISTS topic_group_period;
        DROP TABLE IF EXISTS representative_post;
        DROP TABLE IF EXISTS first_reply_period;
        DROP TABLE IF EXISTS comment_age_period;
        DROP TABLE IF EXISTS long_tail_period;
        DROP TABLE IF EXISTS member_activity_period;
        DROP TABLE IF EXISTS engagement_period;

        CREATE TABLE period_metrics (
            period TEXT PRIMARY KEY,
            topic_count INTEGER NOT NULL,
            comment_count INTEGER NOT NULL,
            member_count INTEGER NOT NULL,
            reply_count INTEGER NOT NULL,
            zero_reply_count INTEGER NOT NULL,
            click_sum INTEGER NOT NULL,
            favorite_sum INTEGER NOT NULL,
            thank_sum INTEGER NOT NULL
        );
        CREATE TABLE activity_period (
            period TEXT NOT NULL,
            weekday INTEGER NOT NULL,
            hour INTEGER NOT NULL,
            topic_count INTEGER NOT NULL,
            comment_count INTEGER NOT NULL,
            PRIMARY KEY (period, weekday, hour)
        );
        CREATE TABLE node_period (
            period TEXT NOT NULL,
            node TEXT NOT NULL,
            topic_count INTEGER NOT NULL,
            reply_count INTEGER NOT NULL,
            click_sum INTEGER NOT NULL,
            PRIMARY KEY (period, node)
        );
        CREATE TABLE tag_period (
            period TEXT NOT NULL,
            tag TEXT NOT NULL,
            topic_count INTEGER NOT NULL,
            reply_count INTEGER NOT NULL,
            click_sum INTEGER NOT NULL,
            PRIMARY KEY (period, tag)
        );
        CREATE TABLE topic_group_period (
            period TEXT NOT NULL,
            group_name TEXT NOT NULL,
            topic_count INTEGER NOT NULL,
            reply_count INTEGER NOT NULL,
            PRIMARY KEY (period, group_name)
        );
        CREATE TABLE representative_post (
            id INTEGER PRIMARY KEY,
            period TEXT NOT NULL,
            title TEXT NOT NULL,
            node TEXT NOT NULL,
            tags TEXT NOT NULL,
            create_at INTEGER NOT NULL,
            clicks INTEGER NOT NULL,
            reply_count INTEGER NOT NULL,
            favorite_count INTEGER NOT NULL,
            thank_count INTEGER NOT NULL,
            score REAL NOT NULL
        );
        CREATE TABLE first_reply_period (
            period TEXT NOT NULL,
            bucket TEXT NOT NULL,
            topic_count INTEGER NOT NULL,
            PRIMARY KEY (period, bucket)
        );
        CREATE TABLE comment_age_period (
            period TEXT NOT NULL,
            bucket TEXT NOT NULL,
            comment_count INTEGER NOT NULL,
            PRIMARY KEY (period, bucket)
        );
        CREATE TABLE long_tail_period (
            period TEXT PRIMARY KEY,
            comment_30d_count INTEGER NOT NULL,
            after_24h_count INTEGER NOT NULL,
            after_7d_count INTEGER NOT NULL,
            eligible_topic_count INTEGER NOT NULL
        );
        CREATE TABLE member_activity_period (
            period TEXT PRIMARY KEY,
            new_member_count INTEGER NOT NULL,
            author_count INTEGER NOT NULL,
            commenter_count INTEGER NOT NULL
        );
        CREATE TABLE engagement_period (
            period TEXT PRIMARY KEY,
            topic_count INTEGER NOT NULL,
            click_count INTEGER NOT NULL,
            favorite_count INTEGER NOT NULL,
            topic_thank_count INTEGER NOT NULL,
            vote_count INTEGER NOT NULL,
            reply_count INTEGER NOT NULL,
            comment_count INTEGER NOT NULL,
            comment_thank_count INTEGER NOT NULL,
            thanked_comment_count INTEGER NOT NULL
        );
        """
    )


def build():
    groups = load_json(ANALYSIS_DIR / "topic_groups.json")
    synonyms = synonym_map()
    tag_stopwords = {
        str(tag).casefold() for tag in load_json(ANALYSIS_DIR / "tag_stopwords.json")
    }
    period_metrics = defaultdict(lambda: [0, 0, 0, 0, 0, 0])
    topic_activity = defaultdict(int)
    nodes = defaultdict(lambda: [0, 0, 0])
    tags = defaultdict(lambda: [0, 0, 0])
    tag_totals = defaultdict(int)
    group_period = defaultdict(lambda: [0, 0])
    post_heaps: dict[str, list] = defaultdict(list)
    engagement_period = defaultdict(lambda: [0, 0, 0, 0, 0, 0])
    interaction_heaps: dict[str, list] = defaultdict(list)

    source = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    query = source.execute(
        """
        SELECT id, author, title, node, tag, create_at, clicks, reply_count,
               favorite_count, thank_count, votes
        FROM topic
        WHERE clicks >= 0 AND create_at >= ?
        ORDER BY id
        """,
        (MIN_VALID_CREATE_AT,),
    )
    for row in query:
        period = month_for(row["create_at"])
        metrics = period_metrics[period]
        metrics[0] += 1
        metrics[1] += max(0, row["reply_count"])
        metrics[2] += int(row["reply_count"] == 0)
        metrics[3] += max(0, row["clicks"])
        metrics[4] += max(0, row["favorite_count"])
        metrics[5] += max(0, row["thank_count"])

        engagement = engagement_period[period]
        engagement[0] += 1
        engagement[1] += max(0, row["clicks"])
        engagement[2] += max(0, row["favorite_count"])
        engagement[3] += max(0, row["thank_count"])
        engagement[4] += max(0, row["votes"])
        engagement[5] += max(0, row["reply_count"])

        created = datetime.fromtimestamp(row["create_at"], LOCAL_TIMEZONE)
        topic_activity[(period, created.weekday(), created.hour)] += 1

        node = row["node"] or "未分类"
        node_metrics = nodes[(period, node)]
        node_metrics[0] += 1
        node_metrics[1] += max(0, row["reply_count"])
        node_metrics[2] += max(0, row["clicks"])

        try:
            raw_tags = json.loads(row["tag"] or "[]")
        except json.JSONDecodeError:
            raw_tags = []
        normalized_tags = normalize_tags(raw_tags, synonyms, tag_stopwords)
        for tag in normalized_tags:
            tag_metrics = tags[(period, tag)]
            tag_metrics[0] += 1
            tag_metrics[1] += max(0, row["reply_count"])
            tag_metrics[2] += max(0, row["clicks"])
            tag_totals[tag] += 1

        for group_name, group in groups.items():
            if matches_group(row["title"], node, normalized_tags, group):
                values = group_period[(period, group_name)]
                values[0] += 1
                values[1] += max(0, row["reply_count"])

        post = {
            "id": row["id"],
            "period": period,
            "title": row["title"],
            "node": node,
            "tags": sorted(normalized_tags),
            "create_at": row["create_at"],
            "clicks": row["clicks"],
            "reply_count": row["reply_count"],
            "favorite_count": row["favorite_count"],
            "thank_count": row["thank_count"],
            "votes": row["votes"],
            "author": row["author"],
        }
        score = engagement_score(row)
        if node.casefold() not in EXCLUDED_REPRESENTATIVE_NODES:
            heap = post_heaps[period]
            item = (score, row["id"], post)
            if len(heap) < REPRESENTATIVE_POSTS_PER_MONTH:
                heapq.heappush(heap, item)
            elif item > heap[0]:
                heapq.heapreplace(heap, item)

        for metric in ("clicks", "favorite_count", "thank_count", "votes"):
            metric_heap = interaction_heaps[metric]
            metric_item = (max(0, row[metric]), row["id"], post)
            if len(metric_heap) < INTERACTION_POST_RANKING_LIMIT:
                heapq.heappush(metric_heap, metric_item)
            elif metric_item > metric_heap[0]:
                heapq.heapreplace(metric_heap, metric_item)

    comment_stats = {
        period: (count, thank_count, thanked_count)
        for period, count, thank_count, thanked_count in source.execute(
            """
            SELECT strftime('%Y-%m', create_at, 'unixepoch', '+8 hours'),
                   COUNT(*), SUM(MAX(0, thank_count)),
                   SUM(CASE WHEN thank_count > 0 THEN 1 ELSE 0 END)
            FROM comment
            WHERE create_at >= ?
            GROUP BY 1
            """,
            (MIN_VALID_CREATE_AT,),
        )
    }
    comment_period = {period: values[0] for period, values in comment_stats.items()}
    member_period = dict(
        source.execute(
            """
            SELECT strftime('%Y-%m', create_at, 'unixepoch', '+8 hours'), COUNT(*)
            FROM member
            WHERE create_at >= ?
            GROUP BY 1
            """,
            (MIN_VALID_CREATE_AT,),
        )
    )
    author_period = dict(
        source.execute(
            """
            SELECT strftime('%Y-%m', create_at, 'unixepoch', '+8 hours'),
                   COUNT(DISTINCT author)
            FROM topic
            WHERE clicks >= 0 AND create_at >= ? AND author != ''
            GROUP BY 1
            """,
            (MIN_VALID_CREATE_AT,),
        )
    )
    commenter_period = dict(
        source.execute(
            """
            SELECT strftime('%Y-%m', create_at, 'unixepoch', '+8 hours'),
                   COUNT(DISTINCT commenter)
            FROM comment
            WHERE create_at >= ? AND commenter != ''
            GROUP BY 1
            """,
            (MIN_VALID_CREATE_AT,),
        )
    )
    comment_activity = {
        (period, int(weekday), int(hour)): count
        for period, weekday, hour, count in source.execute(
            """
            SELECT strftime('%Y-%m', create_at, 'unixepoch', '+8 hours'),
                   (CAST(strftime('%w', create_at, 'unixepoch', '+8 hours') AS INTEGER) + 6) % 7,
                   CAST(strftime('%H', create_at, 'unixepoch', '+8 hours') AS INTEGER),
                   COUNT(*)
            FROM comment
            WHERE create_at >= ?
            GROUP BY 1, 2, 3
            """,
            (MIN_VALID_CREATE_AT,),
        )
    }
    data_as_of = max(
        source.execute("SELECT MAX(create_at) FROM topic").fetchone()[0] or 0,
        source.execute("SELECT MAX(create_at) FROM comment").fetchone()[0] or 0,
    )
    seven_day_cutoff = data_as_of - 7 * 86400
    thirty_day_cutoff = data_as_of - 30 * 86400
    first_reply_period = defaultdict(int)
    for period, topic_created, first_comment in source.execute(
        """
        SELECT strftime('%Y-%m', t.create_at, 'unixepoch', '+8 hours'),
               t.create_at, MIN(c.create_at)
        FROM topic t
        LEFT JOIN comment c ON c.topic_id = t.id AND c.create_at >= t.create_at
        WHERE t.clicks >= 0 AND t.create_at >= ? AND t.create_at <= ?
        GROUP BY t.id
        """,
        (MIN_VALID_CREATE_AT, seven_day_cutoff),
    ):
        delay = None if first_comment is None else first_comment - topic_created
        first_reply_period[(period, first_reply_bucket(delay))] += 1

    comment_age_period = defaultdict(int)
    for period, bucket, count in source.execute(
        """
        SELECT period,
               CASE
                 WHEN delay < 600 THEN '10m'
                 WHEN delay < 3600 THEN '1h'
                 WHEN delay < 21600 THEN '6h'
                 WHEN delay < 86400 THEN '24h'
                 WHEN delay < 259200 THEN '3d'
                 ELSE '7d'
               END,
               COUNT(*)
        FROM (
          SELECT strftime('%Y-%m', t.create_at, 'unixepoch', '+8 hours') AS period,
                 c.create_at - t.create_at AS delay
          FROM comment c
          JOIN topic t ON t.id = c.topic_id
          WHERE t.clicks >= 0 AND t.create_at >= ? AND t.create_at <= ?
            AND c.create_at >= t.create_at AND c.create_at - t.create_at < 604800
        )
        GROUP BY 1, 2
        """,
        (MIN_VALID_CREATE_AT, seven_day_cutoff),
    ):
        comment_age_period[(period, bucket)] += count

    long_tail_period = {
        period: (comment_count, after_24h, after_7d, eligible_topics)
        for period, comment_count, after_24h, after_7d, eligible_topics in source.execute(
            """
            SELECT strftime('%Y-%m', t.create_at, 'unixepoch', '+8 hours'),
                   COUNT(c.id),
                   SUM(CASE WHEN c.create_at - t.create_at >= 86400 THEN 1 ELSE 0 END),
                   SUM(CASE WHEN c.create_at - t.create_at >= 604800 THEN 1 ELSE 0 END),
                   COUNT(DISTINCT t.id)
            FROM topic t
            LEFT JOIN comment c ON c.topic_id = t.id
              AND c.create_at >= t.create_at AND c.create_at - t.create_at < 2592000
            WHERE t.clicks >= 0 AND t.create_at >= ? AND t.create_at <= ?
            GROUP BY 1
            """,
            (MIN_VALID_CREATE_AT, thirty_day_cutoff),
        )
    }
    author_stats = {
        username: {"topic_count": topic_count, "topic_thanks": topic_thanks or 0}
        for username, topic_count, topic_thanks in source.execute(
            """
            SELECT author, COUNT(*), SUM(MAX(0, thank_count))
            FROM topic
            WHERE clicks >= 0 AND create_at >= ? AND author != ''
            GROUP BY author
            """,
            (MIN_VALID_CREATE_AT,),
        )
    }
    commenter_stats = {
        username: {"comment_count": comment_count, "comment_thanks": comment_thanks or 0}
        for username, comment_count, comment_thanks in source.execute(
            """
            SELECT commenter, COUNT(*), SUM(MAX(0, thank_count))
            FROM comment
            WHERE create_at >= ? AND commenter != ''
            GROUP BY commenter
            """,
            (MIN_VALID_CREATE_AT,),
        )
    }
    member_stats = []
    for username in set(author_stats) | set(commenter_stats):
        author = author_stats.get(username, {})
        commenter = commenter_stats.get(username, {})
        member_stats.append(
            {
                "username": username,
                "topic_count": author.get("topic_count", 0),
                "comment_count": commenter.get("comment_count", 0),
                "topic_thanks": author.get("topic_thanks", 0),
                "comment_thanks": commenter.get("comment_thanks", 0),
                "total_thanks": author.get("topic_thanks", 0)
                + commenter.get("comment_thanks", 0),
            }
        )
    top_comments = [
        {
            "id": row[0], "topic_id": row[1], "commenter": row[2],
            "thank_count": row[3], "no": row[4], "topic_title": row[5],
            "content": comment_text(row[6]), "create_at": row[7],
        }
        for row in source.execute(
            f"""
            SELECT c.id, c.topic_id, c.commenter, c.thank_count, c.no, t.title,
                   c.content, c.create_at
            FROM comment c
            JOIN topic t ON t.id = c.topic_id
            WHERE c.thank_count > 0
              AND LOWER(c.commenter) NOT IN ({','.join('?' for _ in EXCLUDED_THANK_USERS)})
            ORDER BY c.thank_count DESC, c.id DESC
            LIMIT ?
            """,
            (*EXCLUDED_THANK_USERS, COMMENT_RANKING_LIMIT),
        )
    ]
    member_rank_rows = build_member_rank_rows(source)
    source.close()

    top_tags = {tag for tag, _ in sorted(tag_totals.items(), key=lambda x: x[1], reverse=True)[:TOP_TAG_LIMIT]}
    periods = sorted(period_metrics)
    analytics = sqlite3.connect(ANALYTICS_DB)
    create_schema(analytics)
    analytics.executemany(
        "INSERT INTO period_metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                period,
                values[0],
                int(comment_period.get(period, 0)),
                int(member_period.get(period, 0)),
                values[1],
                values[2],
                values[3],
                values[4],
                values[5],
            )
            for period, values in sorted(period_metrics.items())
        ],
    )
    activity_keys = sorted(set(topic_activity) | set(comment_activity))
    analytics.executemany(
        "INSERT INTO activity_period VALUES (?, ?, ?, ?, ?)",
        [
            (*key, topic_activity.get(key, 0), comment_activity.get(key, 0))
            for key in activity_keys
        ],
    )
    analytics.executemany(
        "INSERT INTO node_period VALUES (?, ?, ?, ?, ?)",
        [(period, node, *values) for (period, node), values in sorted(nodes.items())],
    )
    analytics.executemany(
        "INSERT INTO tag_period VALUES (?, ?, ?, ?, ?)",
        [
            (period, tag, *values)
            for (period, tag), values in sorted(tags.items())
            if tag in top_tags
        ],
    )
    analytics.executemany(
        "INSERT INTO topic_group_period VALUES (?, ?, ?, ?)",
        [
            (period, group_name, *values)
            for (period, group_name), values in sorted(group_period.items())
        ],
    )
    representative_posts = []
    for heap in post_heaps.values():
        for score, _, post in heap:
            representative_posts.append({**post, "score": round(score, 3)})
    representative_posts.sort(key=lambda item: (item["period"], item["score"]), reverse=True)
    analytics.executemany(
        "INSERT INTO representative_post VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                post["id"], post["period"], post["title"], post["node"],
                json.dumps(post["tags"], ensure_ascii=False), post["create_at"],
                post["clicks"], post["reply_count"], post["favorite_count"],
                post["thank_count"], post["score"],
            )
            for post in representative_posts
        ],
    )
    analytics.executemany(
        "INSERT INTO first_reply_period VALUES (?, ?, ?)",
        [(period, bucket, count) for (period, bucket), count in sorted(first_reply_period.items())],
    )
    analytics.executemany(
        "INSERT INTO comment_age_period VALUES (?, ?, ?)",
        [(period, bucket, count) for (period, bucket), count in sorted(comment_age_period.items())],
    )
    analytics.executemany(
        "INSERT INTO long_tail_period VALUES (?, ?, ?, ?, ?)",
        [(period, *values) for period, values in sorted(long_tail_period.items())],
    )
    analytics.executemany(
        "INSERT INTO member_activity_period VALUES (?, ?, ?, ?)",
        [
            (period, int(member_period.get(period, 0)), int(author_period.get(period, 0)),
             int(commenter_period.get(period, 0)))
            for period in periods
        ],
    )
    analytics.executemany(
        "INSERT INTO engagement_period VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                period, *values,
                int(comment_stats.get(period, (0, 0, 0))[0]),
                int(comment_stats.get(period, (0, 0, 0))[1]),
                int(comment_stats.get(period, (0, 0, 0))[2]),
            )
            for period, values in sorted(engagement_period.items())
        ],
    )
    analytics.commit()

    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    current_period = datetime.now(LOCAL_TIMEZONE).strftime("%Y-%m")
    incomplete_periods = [period for period in periods if period >= current_period]
    complete_periods = [period for period in periods if period < current_period]
    first_reply_complete_through = max(
        period for period in periods if period < month_for(seven_day_cutoff)
    )
    long_tail_complete_through = max(
        period for period in periods if period < month_for(thirty_day_cutoff)
    )
    overview = {
        "metadata": {
            "generated_at": datetime.now(LOCAL_TIMEZONE).isoformat(timespec="seconds"),
            "start_period": periods[0],
            "end_period": periods[-1],
            "default_end_period": complete_periods[-1] if complete_periods else periods[-1],
            "incomplete_periods": incomplete_periods,
            "data_as_of": datetime.fromtimestamp(data_as_of, LOCAL_TIMEZONE).isoformat(timespec="seconds"),
        },
        "periods": [
            {
                "period": row[0], "topic_count": row[1], "comment_count": row[2],
                "member_count": row[3], "reply_count": row[4],
                "zero_reply_count": row[5], "click_sum": row[6],
                "favorite_sum": row[7], "thank_sum": row[8],
            }
            for row in analytics.execute("SELECT * FROM period_metrics ORDER BY period")
        ],
        "activity": [
            list(row) for row in analytics.execute("SELECT * FROM activity_period ORDER BY period, weekday, hour")
        ],
    }
    nodes_output = {
        "rows": [list(row) for row in analytics.execute("SELECT * FROM node_period ORDER BY period, node")]
    }
    topics_output = {
        "tags": [
            {"tag": tag, "total": total}
            for tag, total in sorted(tag_totals.items(), key=lambda x: x[1], reverse=True)[:TOP_TAG_LIMIT]
        ],
        "rows": [list(row) for row in analytics.execute("SELECT * FROM tag_period ORDER BY period, tag")],
        "groups": [
            {"name": name, "label": config["label"], "color": config["color"]}
            for name, config in groups.items()
        ],
        "group_rows": [list(row) for row in analytics.execute("SELECT * FROM topic_group_period ORDER BY period, group_name")],
    }
    representative_posts_output = {
        "representative_posts": representative_posts,
    }
    lifecycle_output = {
        "metadata": {
            "data_as_of": datetime.fromtimestamp(data_as_of, LOCAL_TIMEZONE).isoformat(timespec="seconds"),
            "first_reply_observation_days": 7,
            "long_tail_observation_days": 30,
            "first_reply_complete_through": first_reply_complete_through,
            "long_tail_complete_through": long_tail_complete_through,
        },
        "first_reply_buckets": list(FIRST_REPLY_BUCKETS),
        "comment_age_buckets": list(COMMENT_AGE_BUCKETS),
        "first_reply_rows": [
            list(row) for row in analytics.execute(
                "SELECT * FROM first_reply_period ORDER BY period, bucket"
            )
        ],
        "comment_age_rows": [
            list(row) for row in analytics.execute(
                "SELECT * FROM comment_age_period ORDER BY period, bucket"
            )
        ],
        "long_tail_rows": [
            list(row) for row in analytics.execute("SELECT * FROM long_tail_period ORDER BY period")
        ],
    }
    community_output = {
        "rows": [
            list(row) for row in analytics.execute(
                "SELECT * FROM member_activity_period ORDER BY period"
            )
        ],
        "top_topic_authors": sorted(
            member_stats, key=lambda item: item["topic_count"], reverse=True
        )[:30],
        "top_commenters": sorted(
            member_stats, key=lambda item: item["comment_count"], reverse=True
        )[:30],
        "top_thanked": sorted(
            (
                item for item in member_stats
                if item["username"].casefold() not in EXCLUDED_THANK_USERS
            ),
            key=lambda item: item["total_thanks"], reverse=True
        )[:30],
        "rank_rows": member_rank_rows,
    }
    engagement_output = {
        "rows": [
            list(row) for row in analytics.execute("SELECT * FROM engagement_period ORDER BY period")
        ],
        "top_posts": {
            metric: [
                {**post, "value": value}
                for value, _, post in sorted(heap, reverse=True)
            ]
            for metric, heap in interaction_heaps.items()
        },
        "top_comments": top_comments,
    }
    for name, payload in (
        ("dynamic-overview.json", overview),
        ("dynamic-nodes.json", nodes_output),
        ("dynamic-topics.json", topics_output),
        ("dynamic-representative-posts.json", representative_posts_output),
        ("dynamic-lifecycle.json", lifecycle_output),
        ("dynamic-community.json", community_output),
        ("dynamic-engagement.json", engagement_output),
    ):
        write_json(PUBLIC_DIR / name, payload)
    analytics.close()
    update_tag_details()
    write_manifest("full", full_build=True)
    print(
        f"Built {ANALYTICS_DB}: {len(periods)} periods, "
        f"{len(nodes)} node rows, {len(top_tags)} tags, {len(representative_posts)} posts"
    )


def update_engagement_rankings(
    post_limit: int = INTERACTION_POST_RANKING_LIMIT,
    comment_limit: int = COMMENT_RANKING_LIMIT,
):
    output_path = PUBLIC_DIR / "dynamic-engagement.json"
    output = load_json(output_path)
    synonyms = synonym_map()
    tag_stopwords = {
        str(tag).casefold() for tag in load_json(ANALYSIS_DIR / "tag_stopwords.json")
    }
    source = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row

    top_posts = {}
    for metric in ("clicks", "favorite_count", "thank_count", "votes"):
        rows = source.execute(
            f"""
            SELECT id, author, title, node, tag, create_at, clicks, reply_count,
                   favorite_count, thank_count, votes
            FROM topic
            WHERE clicks >= 0 AND create_at >= ?
            ORDER BY MAX(0, {metric}) DESC, id DESC
            LIMIT ?
            """,
            (MIN_VALID_CREATE_AT, post_limit),
        )
        rankings = []
        for row in rows:
            try:
                raw_tags = json.loads(row["tag"] or "[]")
            except json.JSONDecodeError:
                raw_tags = []
            rankings.append({
                "id": row["id"],
                "period": month_for(row["create_at"]),
                "title": row["title"],
                "node": row["node"] or "未分类",
                "tags": sorted(normalize_tags(raw_tags, synonyms, tag_stopwords)),
                "create_at": row["create_at"],
                "clicks": row["clicks"],
                "reply_count": row["reply_count"],
                "favorite_count": row["favorite_count"],
                "thank_count": row["thank_count"],
                "votes": row["votes"],
                "author": row["author"],
                "value": max(0, row[metric]),
            })
        top_posts[metric] = rankings

    top_comments = [
        {
            "id": row[0], "topic_id": row[1], "commenter": row[2],
            "thank_count": row[3], "no": row[4], "topic_title": row[5],
            "content": comment_text(row[6]), "create_at": row[7],
        }
        for row in source.execute(
            f"""
            SELECT c.id, c.topic_id, c.commenter, c.thank_count, c.no, t.title,
                   c.content, c.create_at
            FROM comment c
            JOIN topic t ON t.id = c.topic_id
            WHERE c.thank_count > 0
              AND LOWER(c.commenter) NOT IN ({','.join('?' for _ in EXCLUDED_THANK_USERS)})
            ORDER BY c.thank_count DESC, c.id DESC
            LIMIT ?
            """,
            (*EXCLUDED_THANK_USERS, comment_limit),
        )
    ]
    source.close()
    output["top_posts"] = top_posts
    output["top_comments"] = top_comments
    write_json(output_path, output)
    write_manifest("engagement")
    print(f"Updated engagement rankings: {post_limit} posts per metric, {len(top_comments)} comments")


def update_representative_posts():
    synonyms = synonym_map()
    tag_stopwords = {
        str(tag).casefold() for tag in load_json(ANALYSIS_DIR / "tag_stopwords.json")
    }
    post_heaps: dict[str, list] = defaultdict(list)
    source = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    for row in source.execute(
        """
        SELECT id, author, title, node, tag, create_at, clicks, reply_count,
               favorite_count, thank_count, votes
        FROM topic
        WHERE clicks >= 0 AND create_at >= ?
        ORDER BY id
        """,
        (MIN_VALID_CREATE_AT,),
    ):
        node = row["node"] or "未分类"
        if node.casefold() in EXCLUDED_REPRESENTATIVE_NODES:
            continue
        try:
            raw_tags = json.loads(row["tag"] or "[]")
        except json.JSONDecodeError:
            raw_tags = []
        post = {
            "id": row["id"], "period": month_for(row["create_at"]),
            "title": row["title"], "node": node,
            "tags": sorted(normalize_tags(raw_tags, synonyms, tag_stopwords)),
            "create_at": row["create_at"], "clicks": row["clicks"],
            "reply_count": row["reply_count"], "favorite_count": row["favorite_count"],
            "thank_count": row["thank_count"], "votes": row["votes"],
            "author": row["author"],
        }
        score = engagement_score(row)
        heap = post_heaps[post["period"]]
        item = (score, row["id"], post)
        if len(heap) < REPRESENTATIVE_POSTS_PER_MONTH:
            heapq.heappush(heap, item)
        elif item > heap[0]:
            heapq.heapreplace(heap, item)
    source.close()

    representative_posts = [
        {**post, "score": round(score, 3)}
        for heap in post_heaps.values()
        for score, _, post in heap
    ]
    representative_posts.sort(key=lambda item: (item["period"], item["score"]), reverse=True)
    write_json(
        PUBLIC_DIR / "dynamic-representative-posts.json",
        {"representative_posts": representative_posts},
    )
    if ANALYTICS_DB.exists():
        analytics = sqlite3.connect(ANALYTICS_DB)
        analytics.execute("DELETE FROM representative_post")
        analytics.executemany(
            "INSERT INTO representative_post VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    post["id"], post["period"], post["title"], post["node"],
                    json.dumps(post["tags"], ensure_ascii=False), post["create_at"],
                    post["clicks"], post["reply_count"], post["favorite_count"],
                    post["thank_count"], post["score"],
                )
                for post in representative_posts
            ],
        )
        analytics.commit()
        analytics.close()
    write_manifest("representative_posts")
    print(f"Updated representative posts: {len(representative_posts)} posts, excluded {sorted(EXCLUDED_REPRESENTATIVE_NODES)}")


def update_community_rankings(limit: int = MEMBER_RANKING_LIMIT):
    output_path = PUBLIC_DIR / "dynamic-community.json"
    output = load_json(output_path)
    source = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro", uri=True)
    output["rank_rows"] = build_member_rank_rows(source, limit)
    source.close()
    write_json(output_path, output)
    write_manifest("community")
    print(f"Updated member rankings: {len(output['rank_rows'])} period ranking rows")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--engagement-only", action="store_true")
    parser.add_argument("--community-only", action="store_true")
    parser.add_argument("--tag-details-only", action="store_true")
    parser.add_argument("--representative-only", action="store_true")
    parser.add_argument("--if-changed", action="store_true")
    parser.add_argument("--interaction-limit", type=int, default=INTERACTION_POST_RANKING_LIMIT)
    parser.add_argument("--comment-limit", type=int, default=COMMENT_RANKING_LIMIT)
    parser.add_argument("--member-limit", type=int, default=MEMBER_RANKING_LIMIT)
    args = parser.parse_args()
    if args.engagement_only:
        update_engagement_rankings(args.interaction_limit, args.comment_limit)
    elif args.community_only:
        update_community_rankings(args.member_limit)
    elif args.tag_details_only:
        update_tag_details()
    elif args.representative_only:
        update_representative_posts()
    elif args.if_changed and source_unchanged_since_full_build():
        print("Source database unchanged; skipped full analytics build")
    else:
        build()
