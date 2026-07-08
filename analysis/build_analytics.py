import argparse
import heapq
import json
import math
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

import jieba


ROOT = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = ROOT / "analysis"
SOURCE_DB = ROOT / "v2ex.sqlite"
ANALYTICS_DB = ANALYSIS_DIR / "analytics.sqlite"
PUBLIC_DIR = ANALYSIS_DIR / "v2ex-analysis" / "public"
MIN_VALID_CREATE_AT = 1262304000
LOCAL_TIMEZONE = timezone(timedelta(hours=8))
TOP_TAG_LIMIT = 500
TITLE_TOKEN_LIMIT = 800
REPRESENTATIVE_POSTS_PER_MONTH = 30
INTERACTION_RANKING_LIMIT = 50
FIRST_REPLY_BUCKETS = ("10m", "1h", "6h", "24h", "3d", "7d", "none")
COMMENT_AGE_BUCKETS = ("10m", "1h", "6h", "24h", "3d", "7d")
EXCLUDED_THANK_USERS = frozenset({"usdc"})
TOKEN_SEGMENT_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9+#._-]*(?:\s+[A-Za-z][A-Za-z0-9+#._-]*)?|"
    r"\d+(?:\.\d+)?|"
    r"[\u4e00-\u9fff]+"
)
_JIEBA_CONFIGURED = False


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


def load_word_set(path: Path) -> set[str]:
    words: set[str] = set()
    with path.open(encoding="utf-8") as fp:
        for line in fp:
            value = line.strip()
            if not value or value.startswith("#"):
                continue
            words.add(value.casefold())
    return words


def synonym_map() -> dict[str, str]:
    result: dict[str, str] = {}
    for canonical, variants in load_json(ANALYSIS_DIR / "tag_synonyms.json").items():
        result[canonical.casefold()] = canonical
        for variant in variants:
            result[str(variant).casefold()] = canonical
    return result


def title_synonym_map() -> dict[str, str]:
    result: dict[str, str] = {}
    for canonical, variants in load_json(ANALYSIS_DIR / "title_synonyms.json").items():
        result[canonical.casefold()] = canonical
        for variant in variants:
            result[str(variant).casefold()] = canonical
    return result


def configure_jieba() -> None:
    global _JIEBA_CONFIGURED
    if _JIEBA_CONFIGURED:
        return
    user_dict = ANALYSIS_DIR / "title_user_dict.txt"
    if user_dict.exists():
        with user_dict.open(encoding="utf-8") as fp:
            jieba.load_userdict(fp)
    _JIEBA_CONFIGURED = True


def canonical_tag(tag: str, synonyms: dict[str, str]) -> str:
    value = tag.strip()
    return synonyms.get(value.casefold(), value)


def normalize_tags(raw_tags, synonyms: dict[str, str], stopwords: set[str]) -> set[str]:
    normalized = {
        canonical_tag(str(tag), synonyms) for tag in raw_tags if str(tag).strip()
    }
    return {tag for tag in normalized if tag.casefold() not in stopwords}


def canonical_title_token(token: str, synonyms: dict[str, str]) -> str:
    value = " ".join(token.strip().split())
    if not value:
        return ""
    folded = value.casefold()
    if folded in synonyms:
        return synonyms[folded]
    if re.fullmatch(r"[A-Za-z0-9+#._-]+(?:\s+[A-Za-z0-9+#._-]+)?", value):
        if value.isupper() or any(char.isdigit() for char in value):
            return value
        return value[:1].upper() + value[1:]
    return value


def should_drop_title_token(token: str, stopwords: set[str]) -> bool:
    folded = token.casefold()
    if not folded or folded in stopwords:
        return True
    if len(token) < 2:
        return True
    if re.fullmatch(r"\d+(?:\.\d+)?", token):
        return True
    if re.fullmatch(r"[A-Za-z]", token):
        return True
    if re.fullmatch(r"[\u4e00-\u9fff]{1}", token):
        return True
    return False


def title_tokens(title: str | None, synonyms: dict[str, str], stopwords: set[str]) -> list[str]:
    configure_jieba()
    tokens: list[str] = []
    for segment in TOKEN_SEGMENT_RE.findall(title or ""):
        segment = segment.strip()
        if not segment:
            continue
        if re.fullmatch(r"[\u4e00-\u9fff]+", segment):
            candidates = jieba.cut(segment)
        else:
            candidates = [segment]
        for candidate in candidates:
            token = canonical_title_token(candidate, synonyms)
            if not should_drop_title_token(token, stopwords):
                tokens.append(token)
    return tokens


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
        CREATE TABLE title_token_period (
            period TEXT NOT NULL,
            token TEXT NOT NULL,
            topic_count INTEGER NOT NULL,
            reply_count INTEGER NOT NULL,
            click_sum INTEGER NOT NULL,
            favorite_sum INTEGER NOT NULL,
            thank_sum INTEGER NOT NULL,
            PRIMARY KEY (period, token)
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
    title_synonyms = title_synonym_map()
    tag_stopwords = {
        str(tag).casefold() for tag in load_json(ANALYSIS_DIR / "tag_stopwords.json")
    }
    title_stopwords = load_word_set(ANALYSIS_DIR / "title_stopwords.txt")
    period_metrics = defaultdict(lambda: [0, 0, 0, 0, 0, 0])
    topic_activity = defaultdict(int)
    nodes = defaultdict(lambda: [0, 0, 0])
    tags = defaultdict(lambda: [0, 0, 0])
    tag_totals = defaultdict(int)
    title_token_period = defaultdict(lambda: [0, 0, 0, 0, 0])
    title_token_totals = defaultdict(int)
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

        for token in set(title_tokens(row["title"], title_synonyms, title_stopwords)):
            token_metrics = title_token_period[(period, token)]
            token_metrics[0] += 1
            token_metrics[1] += max(0, row["reply_count"])
            token_metrics[2] += max(0, row["clicks"])
            token_metrics[3] += max(0, row["favorite_count"])
            token_metrics[4] += max(0, row["thank_count"])
            title_token_totals[token] += 1

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
        heap = post_heaps[period]
        item = (score, row["id"], post)
        if len(heap) < REPRESENTATIVE_POSTS_PER_MONTH:
            heapq.heappush(heap, item)
        elif item > heap[0]:
            heapq.heapreplace(heap, item)

        for metric in ("clicks", "favorite_count", "thank_count", "votes"):
            metric_heap = interaction_heaps[metric]
            metric_item = (max(0, row[metric]), row["id"], post)
            if len(metric_heap) < INTERACTION_RANKING_LIMIT:
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
            "content": comment_text(row[6]),
        }
        for row in source.execute(
            f"""
            SELECT c.id, c.topic_id, c.commenter, c.thank_count, c.no, t.title,
                   c.content
            FROM comment c
            JOIN topic t ON t.id = c.topic_id
            WHERE c.thank_count > 0
              AND LOWER(c.commenter) NOT IN ({','.join('?' for _ in EXCLUDED_THANK_USERS)})
            ORDER BY c.thank_count DESC, c.id DESC
            LIMIT ?
            """,
            (*EXCLUDED_THANK_USERS, INTERACTION_RANKING_LIMIT),
        )
    ]
    source.close()

    top_tags = {tag for tag, _ in sorted(tag_totals.items(), key=lambda x: x[1], reverse=True)[:TOP_TAG_LIMIT]}
    top_title_tokens = {
        token for token, _ in sorted(
            title_token_totals.items(), key=lambda x: x[1], reverse=True
        )[:TITLE_TOKEN_LIMIT]
    }
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
        "INSERT INTO title_token_period VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (period, token, *values)
            for (period, token), values in sorted(title_token_period.items())
            if token in top_title_tokens
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
    title_tokens_output = {
        "title_tokens": [
            {"token": token, "total": total}
            for token, total in sorted(
                title_token_totals.items(), key=lambda x: x[1], reverse=True
            )[:TITLE_TOKEN_LIMIT]
        ],
        "title_token_rows": [
            list(row) for row in analytics.execute(
                "SELECT * FROM title_token_period ORDER BY period, token"
            )
        ],
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
        ("dynamic-title-tokens.json", title_tokens_output),
        ("dynamic-representative-posts.json", representative_posts_output),
        ("dynamic-lifecycle.json", lifecycle_output),
        ("dynamic-community.json", community_output),
        ("dynamic-engagement.json", engagement_output),
    ):
        with (PUBLIC_DIR / name).open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, separators=(",", ":"))
    analytics.close()
    print(
        f"Built {ANALYTICS_DB}: {len(periods)} periods, "
        f"{len(nodes)} node rows, {len(top_tags)} tags, {len(representative_posts)} posts"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.parse_args()
    build()
