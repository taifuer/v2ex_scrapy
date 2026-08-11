import argparse
import hashlib
import heapq
import json
import math
import sqlite3
from calendar import monthrange
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

if __package__:
    from .content_hotspot_audit import write_content_hotspot_audit
    from .content_hotspots import (
        attach_title_token_cache,
        build_content_hotspots,
        cached_title_tokens,
        content_family_config,
        expand_content_families,
        sync_title_token_cache,
    )
else:
    from content_hotspot_audit import write_content_hotspot_audit
    from content_hotspots import (
        attach_title_token_cache,
        build_content_hotspots,
        cached_title_tokens,
        content_family_config,
        expand_content_families,
        sync_title_token_cache,
    )

ROOT = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = ROOT / "analysis"
SOURCE_DB = ROOT / "v2ex.sqlite"
ANALYTICS_DB = ANALYSIS_DIR / "analytics.sqlite"
PUBLIC_DIR = ANALYSIS_DIR / "v2ex-analysis" / "public"
MIN_VALID_CREATE_AT = 1262304000
LOCAL_TIMEZONE = timezone(timedelta(hours=8))
TOP_TAG_LIMIT = 500
FOCUSED_TAGS = frozenset({"投资", "理财", "股票", "基金"})
TAG_REPRESENTATIVE_POSTS_PER_YEAR = 10
TAG_REPRESENTATIVE_POSTS_PER_MONTH = 3
TAG_REPRESENTATIVE_POSTS_PER_ACTIVE_MONTH = 5
TAG_REPRESENTATIVE_ACTIVE_MONTH_MIN_TOPICS = 20
TAG_REPRESENTATIVE_POSTS_PER_VERY_ACTIVE_MONTH = 10
TAG_REPRESENTATIVE_VERY_ACTIVE_MONTH_MIN_TOPICS = 100
MONTHLY_RANKING_LIMIT = 100
PROFILE_RANKING_LIMIT = 20
MONTHLY_POST_METRICS = ("favorite_count", "thank_count", "clicks")
INTERACTION_POST_RANKING_LIMIT = 200
COMMENT_RANKING_LIMIT = 500
FIRST_REPLY_BUCKETS = ("10m", "1h", "6h", "24h", "3d", "7d", "none")
COMMENT_AGE_BUCKETS = ("10m", "1h", "6h", "24h", "3d", "7d")
EXCLUDED_THANK_USERS = frozenset({"usdc"})
EXCLUDED_REPRESENTATIVE_NODES = frozenset({"promotions"})
TOPIC_GROUP_EXCLUDED_NODES = frozenset({"promotions", "cosub", "free", "deals", "tuan"})
MEMBER_RANKING_LIMIT = 30
MEMBER_PROFILE_LIMIT = 2500
MEMBER_PROFILE_DEFAULT_MONTHS = 60
MEMBER_PROFILE_MIN_ANNUAL_APPEARANCES = 3
MEMBER_PROFILE_BUCKET_COUNT = 64
MEMBER_COMMENT_BUCKET_COUNT = 64
MEMBER_PROFILE_LIST_LIMIT = 20
MEMBER_PROFILE_POST_LIMIT = 20
MEMBER_PROFILE_COMMENT_LIMIT = 20
TAG_DETAIL_BUCKET_COUNT = 64
TAG_PERIOD_POST_BUCKET_COUNT = 128
TAG_DETAIL_LIST_LIMIT = 20
NODE_DETAIL_BUCKET_COUNT = 64
NODE_PERIOD_POST_BUCKET_COUNT = 256
NODE_DETAIL_LIST_LIMIT = 20
NODE_DETAIL_POST_LIMIT = 100
NODE_DETAIL_MIN_TOPICS = 50
NODE_REPRESENTATIVE_POSTS_PER_YEAR = 10
NODE_REPRESENTATIVE_POSTS_PER_MONTH = 3
NODE_REPRESENTATIVE_POSTS_PER_ACTIVE_MONTH = 5
NODE_REPRESENTATIVE_ACTIVE_MONTH_MIN_TOPICS = 20
NODE_REPRESENTATIVE_POSTS_PER_VERY_ACTIVE_MONTH = 10
NODE_REPRESENTATIVE_VERY_ACTIVE_MONTH_MIN_TOPICS = 100
ANALYTICS_SCHEMA_VERSION = 29
SEARCH_SUGGESTION_MONTHS = 12
SEARCH_SUGGESTION_LIMIT = 5
SOURCE_STATE_VERSION = 2
ANALYSIS_CONFIG_FILES = (
    "community_events.json",
    "content_detail_terms.txt",
    "content_families.json",
    "content_groups.json",
    "content_stopwords.txt",
    "content_synonyms.json",
    "content_user_dict.txt",
    "node_labels.json",
    "tag_stopwords.json",
    "tag_synonyms.json",
    "topic_groups.json",
)
_source_state_cache: tuple[dict[str, int], dict] | None = None

SCALE_DISTRIBUTION_THRESHOLDS = {
    "post_favorites": (500, 200, 100, 50, 20, 10, 5),
    "post_thanks": (500, 200, 100, 50, 20, 10, 5),
    "post_clicks": (500_000, 200_000, 100_000, 50_000, 20_000, 10_000, 5_000),
    "comment_thanks": (200, 100, 50, 20, 10, 5),
    "topics": (20_000, 10_000, 5_000, 2_000, 1_000, 500),
    "nodes": (100_000, 50_000, 20_000, 10_000, 5_000, 1_000),
    "member_topics": (1_000, 500, 200, 100, 50, 10, 5),
    "member_comments": (10_000, 5_000, 1_000, 500, 100, 10, 5),
    "member_thanks": (10_000, 5_000, 1_000, 500, 100, 10, 5),
}


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


def content_display_terms(content_index: dict) -> set[str]:
    hidden = set(content_index.get("metadata", {}).get("ranking_excluded_terms", []))
    return set(content_index.get("terms", {})) - hidden


def write_json(path: Path, payload):
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    with temp_path.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, separators=(",", ":"))
    temp_path.replace(path)


def load_dynamic_topics() -> dict:
    output = load_json(PUBLIC_DIR / "dynamic-topics.json")
    if "rows" in output:
        return output
    rows = []
    for name in output.get("row_shards", {}).values():
        rows.extend(load_json(PUBLIC_DIR / name).get("rows", []))
    return {**output, "rows": rows}


def source_fingerprint() -> dict[str, int]:
    stat = SOURCE_DB.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def analysis_config_fingerprint() -> str:
    digest = hashlib.blake2b(digest_size=16)
    for name in ANALYSIS_CONFIG_FILES:
        digest.update(name.encode("ascii"))
        digest.update((ANALYSIS_DIR / name).read_bytes())
    return digest.hexdigest()


def source_analysis_state() -> dict:
    global _source_state_cache
    fingerprint = source_fingerprint()
    if _source_state_cache is not None and _source_state_cache[0] == fingerprint:
        return _source_state_cache[1]
    source = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro", uri=True)
    content_digest = hashlib.blake2b(digest_size=16)
    metric_digest = hashlib.blake2b(digest_size=16)
    topic_count = 0
    latest_topic_at = 0
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
        topic_count += 1
        latest_topic_at = max(latest_topic_at, int(row[5]))
        content_digest.update(
            "\0".join(str(value or "") for value in row[:6]).encode("utf-8")
        )
        content_digest.update(b"\n")
        metric_digest.update(
            "\0".join(str(value or 0) for value in (row[0], *row[6:])).encode("ascii")
        )
        metric_digest.update(b"\n")
    comment_state = source.execute(
        """
        SELECT COUNT(*), COALESCE(MAX(id), 0), COALESCE(MAX(create_at), 0),
               COALESCE(SUM(topic_id), 0),
               COALESCE(SUM(CASE WHEN thank_count > 0 THEN thank_count ELSE 0 END), 0),
               COALESCE(SUM(LENGTH(content)), 0),
               COALESCE(SUM(CASE WHEN INSTR(content, '@') > 0 THEN 1 ELSE 0 END), 0),
               COALESCE(SUM(LENGTH(commenter)), 0)
        FROM comment
        WHERE create_at >= ?
        """,
        (MIN_VALID_CREATE_AT,),
    ).fetchone()
    member_state = source.execute(
        """
        SELECT COUNT(*), COALESCE(MAX(uid), 0), COALESCE(MAX(create_at), 0),
               COALESCE(SUM(uid), 0), COALESCE(SUM(create_at), 0),
               COALESCE(SUM(LENGTH(username)), 0)
        FROM member
        WHERE create_at >= ?
        """,
        (MIN_VALID_CREATE_AT,),
    ).fetchone()
    source.close()
    data_as_of = max(latest_topic_at, int(comment_state[2]))
    current_period = datetime.now(LOCAL_TIMEZONE).strftime("%Y-%m")
    state = {
        "version": SOURCE_STATE_VERSION,
        "topic": {
            "count": topic_count,
            "content_hash": content_digest.hexdigest(),
            "metric_hash": metric_digest.hexdigest(),
        },
        "comment": {
            "count": int(comment_state[0]),
            "max_id": int(comment_state[1]),
            "max_create_at": int(comment_state[2]),
            "topic_id_sum": int(comment_state[3]),
            "thank_sum": int(comment_state[4]),
            "content_length_sum": int(comment_state[5]),
            "mention_count": int(comment_state[6]),
            "commenter_length_sum": int(comment_state[7]),
        },
        "member": {
            "count": int(member_state[0]),
            "max_uid": int(member_state[1]),
            "max_create_at": int(member_state[2]),
            "uid_sum": int(member_state[3]),
            "create_at_sum": int(member_state[4]),
            "username_length_sum": int(member_state[5]),
        },
        "analysis": {
            "complete_through": source_complete_through(
                latest_topic_at, data_as_of, current_period
            ),
            "config_hash": analysis_config_fingerprint(),
        },
    }
    _source_state_cache = (fingerprint, state)
    return state


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
        manifest["full_build_state"] = source_analysis_state()
    manifest["files"] = {
        path.name: path.stat().st_size
        for path in sorted(PUBLIC_DIR.glob("dynamic-*.json"))
        if path.name != manifest_path.name
    }
    write_json(manifest_path, manifest)


def update_about_coverage(write_component: bool = True):
    overview_path = PUBLIC_DIR / "dynamic-overview.json"
    overview = load_json(overview_path)
    overview["metadata"]["analysis_coverage"] = {
        "topics": len(load_json(PUBLIC_DIR / "dynamic-tag-detail-index.json").get("tags", {})),
        "content_terms": len(
            load_json(PUBLIC_DIR / "dynamic-content-hotspots-index.json").get("terms", {})
        ),
        "nodes": len(load_json(PUBLIC_DIR / "dynamic-node-detail-index.json").get("nodes", {})),
        "members": len(
            load_json(PUBLIC_DIR / "dynamic-member-profile-index.json").get("members", {})
        ),
    }
    write_json(overview_path, overview)
    if write_component:
        write_manifest("about")
    coverage = overview["metadata"]["analysis_coverage"]
    print(
        "Updated about coverage: "
        f"{coverage['topics']} topics, {coverage['content_terms']} content terms, "
        f"{coverage['nodes']} nodes, {coverage['members']} members"
    )


def source_unchanged_since_full_build() -> bool:
    manifest_path = PUBLIC_DIR / "dynamic-manifest.json"
    if not manifest_path.exists():
        return False
    manifest = load_json(manifest_path)
    if manifest.get("schema_version") != ANALYTICS_SCHEMA_VERSION:
        return False
    if manifest.get("full_build_source") == source_fingerprint():
        return True
    previous_state = manifest.get("full_build_state")
    return previous_state is not None and previous_state == source_analysis_state()


def source_changes_since_full_build() -> set[str] | None:
    manifest_path = PUBLIC_DIR / "dynamic-manifest.json"
    if not manifest_path.exists():
        return None
    manifest = load_json(manifest_path)
    previous = manifest.get("full_build_state")
    if (
        manifest.get("schema_version") != ANALYTICS_SCHEMA_VERSION
        or not isinstance(previous, dict)
        or previous.get("version") != SOURCE_STATE_VERSION
    ):
        return None
    current = source_analysis_state()
    return {
        component
        for component in ("topic", "comment", "member", "analysis")
        if previous.get(component) != current.get(component)
    }


def previous_period(period: str) -> str:
    year, month = map(int, period.split("-"))
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"


def source_complete_through(
    latest_topic_at: int,
    data_as_of: int,
    current_period: str,
) -> str:
    latest_topic_period = month_for(latest_topic_at)
    if latest_topic_period >= current_period:
        return previous_period(current_period)
    data_datetime = datetime.fromtimestamp(data_as_of, LOCAL_TIMEZONE)
    data_period = data_datetime.strftime("%Y-%m")
    if data_period > latest_topic_period:
        return latest_topic_period
    last_day = monthrange(data_datetime.year, data_datetime.month)[1]
    if data_period == latest_topic_period and data_datetime.day == last_day:
        return latest_topic_period
    return previous_period(latest_topic_period)


def period_end_timestamp(period: str) -> int:
    year, month = map(int, period.split("-"))
    if month == 12:
        year += 1
        month = 1
    else:
        month += 1
    return int(datetime(year, month, 1, tzinfo=LOCAL_TIMEZONE).timestamp())


def threshold_rows(values, thresholds) -> list[dict[str, int]]:
    normalized = [max(0, int(value or 0)) for value in values]
    return [
        {
            "threshold": threshold,
            "count": sum(value >= threshold for value in normalized),
        }
        for threshold in thresholds
    ]


def build_scale_distribution(
    source: sqlite3.Connection,
    tag_periods: dict,
    node_periods: dict,
    default_end_period: str,
) -> dict:
    cutoff = period_end_timestamp(default_end_period)

    def source_metric(
        metric_id: str,
        label: str,
        table: str,
        column: str,
        thresholds: tuple[int, ...],
        where: str,
        params: tuple,
    ) -> dict:
        threshold_columns = ", ".join(
            f"SUM(CASE WHEN {column} >= ? THEN 1 ELSE 0 END)"
            for _ in thresholds
        )
        row = source.execute(
            f"""
            SELECT SUM(CASE WHEN {column} >= 0 THEN 1 ELSE 0 END),
                   MAX(CASE WHEN {column} >= 0 THEN {column} ELSE 0 END),
                   {threshold_columns}
            FROM {table}
            WHERE {where}
            """,
            (*thresholds, *params),
        ).fetchone()
        return {
            "id": metric_id,
            "label": label,
            "observed_count": int(row[0] or 0),
            "maximum": int(row[1] or 0),
            "rows": [
                {"threshold": threshold, "count": int(row[index + 2] or 0)}
                for index, threshold in enumerate(thresholds)
            ],
        }

    topic_where = "clicks >= 0 AND create_at >= ? AND create_at < ?"
    topic_params = (MIN_VALID_CREATE_AT, cutoff)
    post_metrics = {
        "favorites": source_metric(
            "favorites", "收藏", "topic", "favorite_count",
            SCALE_DISTRIBUTION_THRESHOLDS["post_favorites"],
            topic_where, topic_params,
        ),
        "thanks": source_metric(
            "thanks", "感谢", "topic", "thank_count",
            SCALE_DISTRIBUTION_THRESHOLDS["post_thanks"],
            topic_where, topic_params,
        ),
        "clicks": source_metric(
            "clicks", "浏览", "topic", "clicks",
            SCALE_DISTRIBUTION_THRESHOLDS["post_clicks"],
            topic_where, topic_params,
        ),
    }
    comment_thanks = source_metric(
        "comment_thanks", "评论感谢", "comment", "thank_count",
        SCALE_DISTRIBUTION_THRESHOLDS["comment_thanks"],
        "create_at >= ? AND create_at < ?", topic_params,
    )

    topic_user_stats = {
        username: (int(topic_count), max(0, int(thanks or 0)))
        for username, topic_count, thanks in source.execute(
            """
            SELECT author, COUNT(*), SUM(MAX(0, thank_count))
            FROM topic
            WHERE clicks >= 0 AND create_at >= ? AND create_at < ? AND author != ''
            GROUP BY author
            """,
            topic_params,
        )
    }
    comment_user_stats = {
        username: (int(comment_count), max(0, int(thanks or 0)))
        for username, comment_count, thanks in source.execute(
            """
            SELECT commenter, COUNT(*), SUM(MAX(0, thank_count))
            FROM comment
            WHERE create_at >= ? AND create_at < ? AND commenter != ''
            GROUP BY commenter
            """,
            topic_params,
        )
    }
    participants = set(topic_user_stats) | set(comment_user_stats)
    member_topic_values = [topic_user_stats.get(username, (0, 0))[0] for username in participants]
    member_comment_values = [comment_user_stats.get(username, (0, 0))[0] for username in participants]
    member_thank_values = [
        topic_user_stats.get(username, (0, 0))[1]
        + comment_user_stats.get(username, (0, 0))[1]
        for username in participants
        if username.casefold() not in EXCLUDED_THANK_USERS
    ]

    def aggregate_period_counts(period_values: dict) -> dict[str, int]:
        totals: dict[str, int] = defaultdict(int)
        for (period, name), values in period_values.items():
            if period <= default_end_period:
                totals[name] += int(values[0])
        return dict(totals)

    topic_totals = aggregate_period_counts(tag_periods)
    node_totals = aggregate_period_counts(node_periods)

    def aggregate_metric(
        metric_id: str,
        label: str,
        values,
        thresholds: tuple[int, ...],
    ) -> dict:
        normalized = [max(0, int(value or 0)) for value in values]
        return {
            "id": metric_id,
            "label": label,
            "observed_count": sum(value > 0 for value in normalized),
            "maximum": max(normalized, default=0),
            "rows": threshold_rows(normalized, thresholds),
        }

    first_topic_at, topic_count = source.execute(
        """
        SELECT MIN(create_at), COUNT(*)
        FROM topic
        WHERE clicks >= 0 AND create_at >= ? AND create_at < ?
        """,
        topic_params,
    ).fetchone()
    comment_count = source.execute(
        "SELECT COUNT(*) FROM comment WHERE create_at >= ? AND create_at < ?",
        topic_params,
    ).fetchone()[0]
    unknown_interactions = source.execute(
        """
        SELECT COUNT(*)
        FROM topic
        WHERE clicks >= 0 AND create_at >= ? AND create_at < ?
          AND (favorite_count < 0 OR thank_count < 0)
        """,
        topic_params,
    ).fetchone()[0]

    return {
        "metadata": {
            "generated_at": datetime.now(LOCAL_TIMEZONE).isoformat(timespec="seconds"),
            "start_period": month_for(first_topic_at) if first_topic_at else "",
            "end_period": default_end_period,
            "scope": "complete_history",
            "unknown_post_interactions": int(unknown_interactions),
            "excluded_thank_users": sorted(EXCLUDED_THANK_USERS),
            "counts": {
                "posts": int(topic_count),
                "comments": int(comment_count),
                "topics": len(topic_totals),
                "nodes": len(node_totals),
                "participants": len(participants),
            },
        },
        "post_metrics": post_metrics,
        "comment_thanks": comment_thanks,
        "entity_metrics": {
            "topics": aggregate_metric(
                "topics", "话题", topic_totals.values(),
                SCALE_DISTRIBUTION_THRESHOLDS["topics"],
            ),
            "nodes": aggregate_metric(
                "nodes", "节点", node_totals.values(),
                SCALE_DISTRIBUTION_THRESHOLDS["nodes"],
            ),
        },
        "member_metrics": {
            "topics": aggregate_metric(
                "member_topics", "发帖", member_topic_values,
                SCALE_DISTRIBUTION_THRESHOLDS["member_topics"],
            ),
            "comments": aggregate_metric(
                "member_comments", "评论", member_comment_values,
                SCALE_DISTRIBUTION_THRESHOLDS["member_comments"],
            ),
            "thanks": aggregate_metric(
                "member_thanks", "收到感谢", member_thank_values,
                SCALE_DISTRIBUTION_THRESHOLDS["member_thanks"],
            ),
        },
    }


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


def select_topic_tags(
    tag_totals: dict[str, int],
    limit: int = TOP_TAG_LIMIT,
    focused_tags: set[str] | frozenset[str] = FOCUSED_TAGS,
) -> list[tuple[str, int]]:
    ranked = sorted(tag_totals.items(), key=lambda item: (-item[1], item[0].casefold()))
    selected = ranked[:limit]
    selected_names = {tag for tag, _ in selected}
    focused = [item for item in ranked if item[0] in focused_tags and item[0] not in selected_names]
    if focused:
        removable = [item for item in reversed(selected) if item[0] not in focused_tags]
        remove_names = {tag for tag, _ in removable[:len(focused)]}
        selected = [item for item in selected if item[0] not in remove_names] + focused
    return sorted(selected, key=lambda item: (-item[1], item[0].casefold()))


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


def prepare_topic_groups(groups: dict) -> dict:
    for group in groups.values():
        group["_topic_lookup"] = {
            str(topic).casefold(): str(topic)
            for topic in group.get("topics", [])
        }
        group["_node_names"] = {
            str(node).casefold()
            for node in group.get("nodes", [])
        }
    return groups


def matching_group_topics(tags: set[str], group: dict) -> set[str]:
    configured = group.get("_topic_lookup") or {
        str(topic).casefold(): str(topic)
        for topic in group.get("topics", [])
    }
    return {
        configured[tag.casefold()]
        for tag in tags
        if tag.casefold() in configured
    }


def matches_topic_group(
    node: str,
    tags: set[str],
    group: dict,
    matched_topics: set[str] | None = None,
) -> bool:
    node_folded = node.casefold()
    if node_folded in TOPIC_GROUP_EXCLUDED_NODES:
        return False
    node_names = group.get("_node_names") or {
        str(item).casefold()
        for item in group.get("nodes", [])
    }
    if node_folded in node_names:
        return True
    return bool(
        matching_group_topics(tags, group)
        if matched_topics is None
        else matched_topics
    )


def engagement_score(row: sqlite3.Row) -> float:
    return (
        max(0, row["reply_count"])
        + max(0, row["favorite_count"]) * 3
        + max(0, row["thank_count"]) * 5
        + max(0, row["votes"]) * 2
        + math.log1p(max(0, row["clicks"]))
    )


def push_top(heap: list, item: tuple, limit: int = MONTHLY_RANKING_LIMIT):
    if len(heap) < limit:
        heapq.heappush(heap, item)
    elif item > heap[0]:
        heapq.heapreplace(heap, item)


def push_tag_representative_candidates(
    heaps: dict[tuple[str, str], list],
    tags: set[str],
    post: dict,
    score: float,
    limit: int = TAG_REPRESENTATIVE_POSTS_PER_YEAR,
):
    year = post["period"][:4]
    for tag in tags:
        heap = heaps.setdefault((tag, year), [])
        push_top(heap, (score, post["id"], post), limit)


def push_tag_monthly_representative_candidates(
    heaps: dict[tuple[str, str], list],
    tags: set[str],
    post: dict,
    score: float,
    limit: int = TAG_REPRESENTATIVE_POSTS_PER_MONTH,
):
    period = post["period"]
    for tag in tags:
        heap = heaps.setdefault((tag, period), [])
        push_top(heap, (score, post["id"], post), limit)


def tag_monthly_representative_limit(topic_count: int) -> int:
    if topic_count >= TAG_REPRESENTATIVE_VERY_ACTIVE_MONTH_MIN_TOPICS:
        return TAG_REPRESENTATIVE_POSTS_PER_VERY_ACTIVE_MONTH
    if topic_count >= TAG_REPRESENTATIVE_ACTIVE_MONTH_MIN_TOPICS:
        return TAG_REPRESENTATIVE_POSTS_PER_ACTIVE_MONTH
    return TAG_REPRESENTATIVE_POSTS_PER_MONTH


def node_monthly_representative_limit(topic_count: int) -> int:
    if topic_count >= NODE_REPRESENTATIVE_VERY_ACTIVE_MONTH_MIN_TOPICS:
        return NODE_REPRESENTATIVE_POSTS_PER_VERY_ACTIVE_MONTH
    if topic_count >= NODE_REPRESENTATIVE_ACTIVE_MONTH_MIN_TOPICS:
        return NODE_REPRESENTATIVE_POSTS_PER_ACTIVE_MONTH
    return NODE_REPRESENTATIVE_POSTS_PER_MONTH


def group_tag_representative_posts(
    heaps: dict[tuple[str, str], list],
) -> dict[str, list[dict]]:
    posts_by_tag = defaultdict(list)
    for (tag, _), heap in heaps.items():
        posts_by_tag[tag].extend(post for _, _, post in heap)
    for posts in posts_by_tag.values():
        posts.sort(
            key=lambda post: (post["score"], post["create_at"], post["id"]),
            reverse=True,
        )
    return posts_by_tag


def group_tag_monthly_representative_posts(
    heaps: dict[tuple[str, str], list],
) -> dict[str, dict[str, list[dict]]]:
    posts_by_tag: dict[str, dict[str, list[dict]]] = defaultdict(dict)
    for (tag, period), heap in heaps.items():
        posts_by_tag[tag][period] = sorted(
            (post for _, _, post in heap),
            key=lambda post: (post["score"], post["create_at"], post["id"]),
            reverse=True,
        )
    return posts_by_tag


def build_monthly_comment_heaps(
    source: sqlite3.Connection,
    default_end_period: str | None = None,
) -> dict[str, list]:
    heaps: dict[str, list] = defaultdict(list)
    placeholders = ",".join("?" for _ in EXCLUDED_THANK_USERS)
    for row in source.execute(
        f"""
        SELECT c.id, c.topic_id, c.commenter, c.thank_count, c.no, t.title,
               c.content, c.create_at
        FROM comment c
        JOIN topic t ON t.id = c.topic_id
        WHERE c.create_at >= ? AND c.thank_count > 0 AND t.clicks >= 0
          AND LOWER(c.commenter) NOT IN ({placeholders})
        """,
        (MIN_VALID_CREATE_AT, *EXCLUDED_THANK_USERS),
    ):
        period = month_for(row[7])
        if default_end_period is not None and period > default_end_period:
            continue
        comment = {
            "id": row[0], "topic_id": row[1], "commenter": row[2],
            "thank_count": row[3], "no": row[4], "topic_title": row[5],
            "content": comment_text(row[6]), "create_at": row[7],
        }
        push_top(heaps[period], (max(0, row[3]), row[0], comment))
    return heaps


def build_annual_comment_heaps(source: sqlite3.Connection, default_end_period: str) -> dict[str, list]:
    heaps: dict[str, list] = defaultdict(list)
    placeholders = ",".join("?" for _ in EXCLUDED_THANK_USERS)
    for row in source.execute(
        f"""
        SELECT c.id, c.topic_id, c.commenter, c.thank_count, c.no, t.title,
               c.content, c.create_at
        FROM comment c
        JOIN topic t ON t.id = c.topic_id
        WHERE c.create_at >= ? AND c.thank_count > 0 AND t.clicks >= 0
          AND LOWER(c.commenter) NOT IN ({placeholders})
        """,
        (MIN_VALID_CREATE_AT, *EXCLUDED_THANK_USERS),
    ):
        period = month_for(row[7])
        if period > default_end_period:
            continue
        comment = {
            "id": row[0], "topic_id": row[1], "commenter": row[2],
            "thank_count": row[3], "no": row[4], "topic_title": row[5],
            "content": comment_text(row[6]), "create_at": row[7],
        }
        push_top(heaps[period[:4]], (max(0, row[3]), row[0], comment))
    return heaps


def build_monthly_summaries(topics: dict, nodes: dict, community: dict) -> dict[str, dict]:
    summaries: dict[str, dict] = defaultdict(
        lambda: {"tags": [], "content": [], "nodes": [], "activity": {}}
    )

    tags_by_period: dict[str, list] = defaultdict(list)
    for period, tag, topic_count, *_ in topics.get("rows", []):
        tags_by_period[period].append({"name": tag, "value": topic_count})
    for period, rows in tags_by_period.items():
        summaries[period]["tags"] = sorted(
            rows, key=lambda item: (-item["value"], item["name"].casefold())
        )[:PROFILE_RANKING_LIMIT]

    nodes_by_period: dict[str, list] = defaultdict(list)
    for period, node, topic_count, *_ in nodes.get("rows", []):
        nodes_by_period[period].append({"name": node, "value": topic_count})
    for period, rows in nodes_by_period.items():
        summaries[period]["nodes"] = sorted(
            rows, key=lambda item: (-item["value"], item["name"].casefold())
        )[:PROFILE_RANKING_LIMIT]

    activity = {
        row[0]: {"authors": int(row[2]), "commenters": int(row[3])}
        for row in community.get("rows", [])
    }
    for period, values in activity.items():
        year, month = map(int, period.split("-"))
        previous_period = f"{year - 1}-12" if month == 1 else f"{year}-{month - 1:02d}"
        year_ago_period = f"{year - 1}-{month:02d}"
        for metric in ("authors", "commenters"):
            summaries[period]["activity"][metric] = [
                values[metric],
                activity.get(previous_period, {}).get(metric),
                activity.get(year_ago_period, {}).get(metric),
            ]
    return dict(summaries)


def build_annual_summaries(
    topics: dict,
    nodes: dict,
    community: dict,
    default_end_period: str,
) -> dict[str, dict]:
    summaries: dict[str, dict] = defaultdict(
        lambda: {"tags": [], "content": [], "nodes": [], "activity": {}}
    )
    tag_values: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    node_values: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for period, tag, topic_count, *_ in topics.get("rows", []):
        if period <= default_end_period:
            tag_values[period[:4]][tag] += int(topic_count)
    for period, node, topic_count, *_ in nodes.get("rows", []):
        if period <= default_end_period:
            node_values[period[:4]][node] += int(topic_count)
    for year, values in tag_values.items():
        summaries[year]["tags"] = [
            {"name": name, "value": value}
            for name, value in sorted(values.items(), key=lambda item: (-item[1], item[0].casefold()))[:PROFILE_RANKING_LIMIT]
        ]
    for year, values in node_values.items():
        summaries[year]["nodes"] = [
            {"name": name, "value": value}
            for name, value in sorted(values.items(), key=lambda item: (-item[1], item[0].casefold()))[:PROFILE_RANKING_LIMIT]
        ]
    return dict(summaries)


def load_content_period_summaries(public_dir: Path = PUBLIC_DIR) -> tuple[dict[str, list], dict[str, list]]:
    index_path = public_dir / "dynamic-content-hotspots-index.json"
    if not index_path.exists():
        return {}, {}
    monthly: dict[str, list] = defaultdict(list)
    annual: dict[str, list] = defaultdict(list)
    index = load_json(index_path)
    for name in index.get("year_shards", {}).values():
        path = public_dir / name
        if not path.exists():
            continue
        payload = load_json(path)
        for row in payload.get("rows", []):
            if len(row) > 9 and 0 < int(row[9]) <= PROFILE_RANKING_LIMIT:
                monthly[row[0]].append((int(row[9]), {"name": row[1], "value": int(row[2])}))
        for row in payload.get("annual_rows", []):
            if len(row) > 9 and 0 < int(row[9]) <= PROFILE_RANKING_LIMIT:
                annual[row[0]].append((int(row[9]), {"name": row[1], "value": int(row[2])}))
    return (
        {period: [item for _, item in sorted(rows)] for period, rows in monthly.items()},
        {year: [item for _, item in sorted(rows)] for year, rows in annual.items()},
    )


def load_content_hotspot_rows(public_dir: Path = PUBLIC_DIR) -> list[list]:
    index_path = public_dir / "dynamic-content-hotspots-index.json"
    if not index_path.exists():
        return []
    rows = []
    index = load_json(index_path)
    for name in index.get("year_shards", {}).values():
        path = public_dir / name
        if path.exists():
            rows.extend(load_json(path).get("rows", []))
    return rows


def build_search_suggestions(public_dir: Path = PUBLIC_DIR) -> dict:
    overview = load_json(public_dir / "dynamic-overview.json")
    end_period = overview["metadata"]["default_end_period"]
    window = [end_period]
    for _ in range(SEARCH_SUGGESTION_MONTHS - 1):
        window.append(previous_period(window[-1]))
    start_period = window[-1]

    topic_index = load_json(public_dir / "dynamic-topics.json")
    topic_counts: dict[str, int] = defaultdict(int)
    for year, name in topic_index.get("row_shards", {}).items():
        if year < start_period[:4] or year > end_period[:4]:
            continue
        for period, topic, count, *_ in load_json(public_dir / name).get("rows", []):
            if start_period <= period <= end_period:
                topic_counts[topic] += int(count)

    content_index = load_json(public_dir / "dynamic-content-hotspots-index.json")
    ranked_content = {
        term
        for term, entry in content_index.get("terms", {}).items()
        if entry.get("ranked")
    }
    content_counts: dict[str, int] = defaultdict(int)
    for year, name in content_index.get("year_shards", {}).items():
        if year < start_period[:4] or year > end_period[:4]:
            continue
        for row in load_json(public_dir / name).get("rows", []):
            period, term, count = row[:3]
            if start_period <= period <= end_period and term in ranked_content:
                content_counts[term] += int(count)

    def ranked_items(counts: dict[str, int], excluded: set[str] | None = None) -> list[dict]:
        excluded = excluded or set()
        return [
            {"value": value, "count": count}
            for value, count in sorted(
                counts.items(), key=lambda item: (-item[1], item[0].casefold(), item[0])
            )
            if value.casefold() not in excluded
        ][:SEARCH_SUGGESTION_LIMIT]

    topics = ranked_items(topic_counts)
    used = {item["value"].casefold() for item in topics}
    content = ranked_items(content_counts, used)
    output = {
        "metadata": {
            "from_period": start_period,
            "to_period": end_period,
            "months": SEARCH_SUGGESTION_MONTHS,
            "limit_per_type": SEARCH_SUGGESTION_LIMIT,
            "method": "按最近 12 个完整月份累计帖子数排序；话题与标题关键词候选按名称去重。",
        },
        "topics": topics,
        "content": content,
    }
    write_json(public_dir / "dynamic-search-suggestions.json", output)
    return output


def refresh_period_ranking_content(public_dir: Path = PUBLIC_DIR) -> tuple[int, int]:
    monthly, annual = load_content_period_summaries(public_dir)
    updated_months = 0
    updated_years = 0
    for path in public_dir.glob("dynamic-monthly-ranking-*.json"):
        payload = load_json(path)
        period = payload.get("period", "")
        summary = payload.setdefault("ranking", {}).setdefault("summary", {})
        summary.pop("members", None)
        summary["content"] = monthly.get(period, [])
        write_json(path, payload)
        updated_months += 1
    for path in public_dir.glob("dynamic-annual-ranking-*.json"):
        payload = load_json(path)
        year = payload.get("year", "")
        summary = payload.setdefault("ranking", {}).setdefault("summary", {})
        summary.pop("members", None)
        summary["content"] = annual.get(year, [])
        write_json(path, payload)
        updated_years += 1
    return updated_months, updated_years


def build_annual_activity(source: sqlite3.Connection, default_end_period: str) -> dict[str, dict]:
    result: dict[str, dict] = defaultdict(dict)
    for metric, table, member_column in (
        ("authors", "topic", "author"),
        ("commenters", "comment", "commenter"),
    ):
        rows = source.execute(
            f"""
            SELECT strftime('%Y', create_at, 'unixepoch', '+8 hours') AS year,
                   COUNT(DISTINCT {member_column})
            FROM {table}
            WHERE create_at >= ? AND {member_column} != ''
              AND strftime('%Y-%m', create_at, 'unixepoch', '+8 hours') <= ?
            GROUP BY 1
            """,
            (MIN_VALID_CREATE_AT, default_end_period),
        )
        values = {year: int(value) for year, value in rows}
        for year, value in values.items():
            previous = values.get(str(int(year) - 1))
            result[year][metric] = [value, previous, previous]
    return dict(result)


def write_monthly_rankings(
    score_heaps: dict[str, list],
    metric_heaps: dict[tuple[str, str], list],
    comment_heaps: dict[str, list],
    summaries: dict[str, dict],
):
    months: dict[str, dict] = {}
    periods = sorted(set(score_heaps) | {period for period, _ in metric_heaps} | set(comment_heaps))
    for period in periods:
        ranking_entries = {
            "score": sorted(score_heaps.get(period, []), reverse=True),
            **{
                metric: sorted(metric_heaps.get((period, metric), []), reverse=True)
                for metric in MONTHLY_POST_METRICS
            },
        }
        posts = {}
        rankings = {}
        for metric, entries in ranking_entries.items():
            rankings[metric] = [item[1] for item in entries]
            for _, _, post in entries:
                posts[post["id"]] = {
                    key: value for key, value in post.items()
                    if key not in {"period", "tags"}
                }
        comments = [item[2] for item in sorted(comment_heaps.get(period, []), reverse=True)]
        months[period] = {
            "summary": summaries.get(period, {}),
            "posts": list(posts.values()),
            "post_rankings": rankings,
            "comments": comments,
        }

    for path in PUBLIC_DIR.glob("dynamic-monthly-rankings-*.json"):
        path.unlink()
    for path in PUBLIC_DIR.glob("dynamic-monthly-ranking-*.json"):
        path.unlink()
    index = {
        "limit": MONTHLY_RANKING_LIMIT,
        "post_metrics": ["score", *MONTHLY_POST_METRICS],
        "periods": {},
    }
    for period, payload in sorted(months.items()):
        name = f"dynamic-monthly-ranking-{period}.json"
        write_json(PUBLIC_DIR / name, {"period": period, "ranking": payload})
        index["periods"][period] = name
    write_json(PUBLIC_DIR / "dynamic-monthly-rankings-index.json", index)


def write_annual_rankings(
    score_heaps: dict[str, list],
    metric_heaps: dict[tuple[str, str], list],
    comment_heaps: dict[str, list],
    summaries: dict[str, dict],
):
    years = {}
    for year in sorted(set(score_heaps) | {period for period, _ in metric_heaps} | set(comment_heaps)):
        ranking_entries = {
            "score": sorted(score_heaps.get(year, []), reverse=True),
            **{
                metric: sorted(metric_heaps.get((year, metric), []), reverse=True)
                for metric in MONTHLY_POST_METRICS
            },
        }
        posts = {}
        rankings = {}
        for metric, entries in ranking_entries.items():
            rankings[metric] = [item[1] for item in entries]
            for _, _, post in entries:
                posts[post["id"]] = {
                    key: value for key, value in post.items()
                    if key not in {"period", "tags"}
                }
        years[year] = {
            "summary": summaries.get(year, {}),
            "posts": list(posts.values()),
            "post_rankings": rankings,
            "comments": [item[2] for item in sorted(comment_heaps.get(year, []), reverse=True)],
        }
    for path in PUBLIC_DIR.glob("dynamic-annual-ranking-*.json"):
        path.unlink()
    aggregate_path = PUBLIC_DIR / "dynamic-annual-rankings.json"
    if aggregate_path.exists():
        aggregate_path.unlink()
    index_path = PUBLIC_DIR / "dynamic-annual-rankings-index.json"
    if index_path.exists():
        index_path.unlink()
    index = {
        "limit": MONTHLY_RANKING_LIMIT,
        "post_metrics": ["score", *MONTHLY_POST_METRICS],
        "years": {},
    }
    for year, payload in sorted(years.items()):
        name = f"dynamic-annual-ranking-{year}.json"
        write_json(PUBLIC_DIR / name, {"year": year, "ranking": payload})
        index["years"][year] = name
    write_json(index_path, index)


def hashed_bucket(value: str, bucket_count: int) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()
    width = max(1, len(format(bucket_count - 1, "x")))
    return format(int(digest[:8], 16) % bucket_count, f"0{width}x")


def bucket_names(bucket_count: int) -> list[str]:
    width = max(1, len(format(bucket_count - 1, "x")))
    return [format(index, f"0{width}x") for index in range(bucket_count)]


def tag_detail_bucket(tag: str) -> str:
    return hashed_bucket(tag, TAG_DETAIL_BUCKET_COUNT)


def tag_period_post_bucket(tag: str) -> str:
    return hashed_bucket(tag, TAG_PERIOD_POST_BUCKET_COUNT)


def node_detail_bucket(node: str) -> str:
    return hashed_bucket(node, NODE_DETAIL_BUCKET_COUNT)


def node_period_post_bucket(node: str) -> str:
    return hashed_bucket(node, NODE_PERIOD_POST_BUCKET_COUNT)


def member_profile_bucket(username: str) -> str:
    return hashed_bucket(username, MEMBER_PROFILE_BUCKET_COUNT)


def member_comment_bucket(username: str) -> str:
    digest = hashlib.sha1(username.encode("utf-8")).hexdigest()
    return format(int(digest[:2], 16) % MEMBER_COMMENT_BUCKET_COUNT, "02x")


def percent_change(current: float, previous: float) -> float:
    return ((current - previous) / previous * 100) if previous else 0.0


def build_observation_output(
    overview: dict,
    topics: dict,
    lifecycle: dict,
    engagement: dict,
    content_rows: list[list],
) -> dict:
    complete = [
        row for row in overview["periods"]
        if row["period"] <= overview["metadata"]["default_end_period"]
    ]
    analysis = complete[-120:]
    current = analysis[-60:]
    previous = analysis[:60]
    current_periods = {row["period"] for row in analysis}
    current_five_periods = {row["period"] for row in current}
    previous_five_periods = {row["period"] for row in previous}
    current_start, current_end = analysis[0]["period"], analysis[-1]["period"]
    previous_start, previous_end = previous[0]["period"], previous[-1]["period"]

    def total(rows: list[dict], key: str) -> int:
        return sum(int(row[key]) for row in rows)

    current_topics = total(current, "topic_count")
    previous_topics = total(previous, "topic_count")
    current_comments = total(current, "comment_count")
    previous_comments = total(previous, "comment_count")
    topic_change = percent_change(current_topics, previous_topics)
    comment_change = percent_change(current_comments, previous_comments)
    current_density = current_comments / current_topics
    previous_density = previous_comments / previous_topics
    analysis_topics = total(analysis, "topic_count")
    analysis_comments = total(analysis, "comment_count")
    analysis_density = analysis_comments / analysis_topics

    invitation_period = "2024-05"
    invitation_index = next(
        index for index, row in enumerate(complete) if row["period"] == invitation_period
    )
    invitation_before = complete[invitation_index - 12:invitation_index]
    invitation_after = complete[invitation_index:invitation_index + 12]

    def average(rows: list[dict], key: str) -> float:
        return total(rows, key) / len(rows)

    members_before = average(invitation_before, "member_count")
    members_after = average(invitation_after, "member_count")
    topics_after_change = percent_change(
        average(invitation_after, "topic_count"), average(invitation_before, "topic_count")
    )
    comments_after_change = percent_change(
        average(invitation_after, "comment_count"), average(invitation_before, "comment_count")
    )

    recent_12 = complete[-12:]
    recent_periods = {row["period"] for row in recent_12}

    def tag_count(tag: str, periods: set[str]) -> int:
        return sum(
            int(row[2]) for row in topics["rows"]
            if row[0] in periods and row[1] == tag
        )

    tag_period_counts = {
        (row[1], row[0]): int(row[2]) for row in topics["rows"]
    }
    content_period_counts = {
        (row[1], row[0]): int(row[2]) for row in content_rows
    }

    def tag_month(tag: str, period: str) -> int:
        return tag_period_counts.get((tag, period), 0)

    def content_month(term: str, period: str) -> int:
        return content_period_counts.get((term, period), 0)

    complete_periods = [row["period"] for row in complete]

    def rolling_tag_peak(tag: str) -> tuple[int, str, str]:
        peak = (0, "", "")
        for end_index in range(11, len(complete_periods)):
            window = complete_periods[end_index - 11:end_index + 1]
            value = sum(tag_month(tag, period) for period in window)
            if value > peak[0]:
                peak = (value, window[0], window[-1])
        return peak

    def tag_peak(tag: str) -> tuple[int, str]:
        return max(
            ((tag_month(tag, period), period) for period in complete_periods),
            default=(0, ""),
        )

    def content_peak(term: str) -> tuple[int, str]:
        return max(
            ((content_month(term, period), period) for period in complete_periods),
            default=(0, ""),
        )

    def recent_content_count(term: str) -> int:
        return sum(content_month(term, period) for period in recent_periods)

    recent_java = tag_count("Java", recent_periods)
    recent_python = tag_count("Python", recent_periods)
    java_peak = rolling_tag_peak("Java")
    python_peak = rolling_tag_peak("Python")
    chatgpt_peak = tag_peak("ChatGPT")
    ai_peak = tag_peak("AI")
    model_peak = tag_peak("模型")
    codex_recent = recent_content_count("Codex")
    claude_code_recent = recent_content_count("Claude Code")
    agent_recent = recent_content_count("Agent")
    codex_peak = content_peak("Codex")
    claude_code_peak = content_peak("Claude Code")
    agent_peak = content_peak("Agent")

    thanked_post = engagement["top_posts"]["thank_count"][0]

    def group_count(group: str, periods: set[str]) -> int:
        return sum(
            int(row[2]) for row in topics["group_rows"]
            if row[0] in periods and row[1] == group
        )

    previous_engineering = group_count("engineering", previous_five_periods)
    current_engineering = group_count("engineering", current_five_periods)
    previous_career = group_count("career", previous_five_periods)
    current_career = group_count("career", current_five_periods)
    previous_creation = group_count("creation", previous_five_periods)
    current_creation = group_count("creation", current_five_periods)
    previous_ai = group_count("ai", previous_five_periods)
    current_ai = group_count("ai", current_five_periods)
    previous_home = group_count("home", previous_five_periods)
    current_home = group_count("home", current_five_periods)

    subscription_changes = {
        tag: (
            tag_count(tag, previous_five_periods),
            tag_count(tag, current_five_periods),
        )
        for tag in ("拼车", "88vip", "订阅")
    }

    favorite_top = engagement["top_posts"]["favorite_count"][:20]
    thanked_top = engagement["top_posts"]["thank_count"][:20]
    favorite_top_ids = {post["id"] for post in favorite_top}
    interaction_overlap = sum(post["id"] in favorite_top_ids for post in thanked_top)
    favorite_programmer_count = sum(post["node"] == "programmer" for post in favorite_top)
    thanked_life_count = sum(post["node"] == "life" for post in thanked_top)

    thanked_comments = engagement["top_comments"][:100]
    thanked_comment_lengths = sorted(
        len((comment.get("content") or "").strip()) for comment in thanked_comments
    )
    thanked_comment_median = thanked_comment_lengths[len(thanked_comment_lengths) // 2]
    short_thanked_comments = sum(length <= 30 for length in thanked_comment_lengths)
    top_comment = thanked_comments[0]

    apple_rows = [row for row in topics["group_rows"] if row[1] == "apple"]
    apple_topics = sum(row[2] for row in apple_rows if row[0] in current_periods)
    apple_previous = sum(row[2] for row in apple_rows if row[0] in previous_five_periods)
    apple_current = sum(row[2] for row in apple_rows if row[0] in current_five_periods)
    apple_share = apple_topics / analysis_topics * 100
    apple_previous_share = apple_previous / previous_topics * 100
    apple_current_share = apple_current / current_topics * 100

    activity_rows = [row for row in overview["activity"] if row[0] in current_periods]
    work_topics = sum(row[3] for row in activity_rows if row[1] < 5 and 9 <= row[2] < 18)
    work_comments = sum(row[4] for row in activity_rows if row[1] < 5 and 9 <= row[2] < 18)
    activity_topics = sum(row[3] for row in activity_rows)
    activity_comments = sum(row[4] for row in activity_rows)
    topic_slots = defaultdict(int)
    comment_slots = defaultdict(int)
    for row in activity_rows:
        topic_slots[(row[1], row[2])] += row[3]
        comment_slots[(row[1], row[2])] += row[4]
    weekday_names = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
    topic_peak = max(topic_slots, key=topic_slots.get)
    comment_peak = max(comment_slots, key=comment_slots.get)

    first_cutoff = lifecycle["metadata"]["first_reply_complete_through"]
    tail_cutoff = lifecycle["metadata"]["long_tail_complete_through"]
    first_rows = [
        row for row in lifecycle["first_reply_rows"]
        if current_start <= row[0] <= min(current_end, first_cutoff)
    ]
    first_counts = defaultdict(int)
    for row in first_rows:
        first_counts[row[1]] += row[2]
    eligible_topics = sum(first_counts.values())
    within_1h = first_counts["10m"] + first_counts["1h"]
    within_24h = within_1h + first_counts["6h"] + first_counts["24h"]
    response_rate = (eligible_topics - first_counts["none"]) / eligible_topics * 100
    tail_rows = [
        row for row in lifecycle["long_tail_rows"]
        if current_start <= row[0] <= min(current_end, tail_cutoff)
    ]
    comments_30d = sum(row[1] for row in tail_rows)
    comments_after_7d = sum(row[3] for row in tail_rows)
    after_7d_share = comments_after_7d / comments_30d * 100

    def link(
        tab: str,
        label: str,
        view: str | None = None,
        anchor: str | None = None,
        **params,
    ) -> dict:
        query = {"tab": tab, "from": current_start, "to": current_end, **params}
        if view:
            query["view"] = view
        href = "?" + "&".join(f"{key}={value}" for key, value in query.items())
        if anchor:
            href += f"#{anchor}"
        return {"label": label, "href": href}

    observations = [
        {
            "id": "content-rebalance",
            "category": "话题结构",
            "title": "技术主线仍在，但话题重心已明显重新分配",
            "summary": (
                f"后五年，编程与工程、工作与职场话题板块分别较前五年变化 "
                f"{percent_change(current_engineering, previous_engineering):+.1f}% 和 "
                f"{percent_change(current_career, previous_career):+.1f}%；AI 与智能体增长 "
                f"{percent_change(current_ai, previous_ai):.1f}%，产品与创造增长 "
                f"{percent_change(current_creation, previous_creation):.1f}%。"
            ),
            "interpretation": (
                f"城市与生活话题也增长 {percent_change(current_home, previous_home):.1f}%。"
                "这不是技术内容消失，而是社区从通用语言、开发和求职问题，扩展到 AI 工具、产品实践、数字消费与生活经验。"
                "话题板块允许重叠，适合观察方向变化，不能相加为全站占比。"
            ),
            "evidence": "话题板块对比",
            "confidence": "高",
            "stats": [
                {"value": f"{percent_change(current_engineering, previous_engineering):+.1f}%", "label": "编程与工程"},
                {"value": f"{percent_change(current_ai, previous_ai):+.1f}%", "label": "AI 与智能体"},
                {"value": f"{percent_change(current_creation, previous_creation):+.1f}%", "label": "产品与创造"},
            ],
            "links": [link("content", "查看话题演变", view="topics")],
        },
        {
            "id": "decade-shift",
            "category": "规模与参与",
            "title": "十年社区由规模扩张转向存量讨论",
            "summary": (
                f"{current_start} 至 {current_end} 共发布 {analysis_topics:,} 个帖子、产生 {analysis_comments:,} 条评论；"
                f"后 5 年帖子数较前 5 年下降 {abs(topic_change):.1f}%，评论数只下降 {abs(comment_change):.1f}%。"
            ),
            "interpretation": (
                f"平均每个帖子的评论从 {previous_density:.1f} 条升至 {current_density:.1f} 条。"
                "社区不再主要依赖帖子数量扩张，而是由较少帖子承载更集中讨论；这比单纯描述为‘活跃度下降’更准确。"
            ),
            "evidence": "数据事实",
            "confidence": "高",
            "stats": [
                {"value": f"{analysis_topics:,}", "label": "近 10 年帖子"},
                {"value": f"{analysis_comments:,}", "label": "近 10 年评论"},
                {"value": f"{analysis_density:.1f}", "label": "十年评论 / 帖子"},
            ],
            "links": [link("overview", "查看规模变化")],
        },
        {
            "id": "invitation-system",
            "category": "成员变化",
            "title": "邀请码制度构成清晰的成员增长断点",
            "summary": (
                f"邀请码实施前 12 个月平均每月新增 {members_before:,.0f} 人，之后 12 个月为 "
                f"{members_after:,.0f} 人，下降 {abs(percent_change(members_after, members_before)):.1f}%。"
            ),
            "interpretation": (
                f"同期帖子和评论月均值仅分别变化 {topics_after_change:.1f}% 和 {comments_after_change:.1f}%。"
                "新增成员断崖式减少与 2024-05-06 生效的邀请码机制时间高度吻合，也说明存量成员仍维持了大部分社区活动；"
                "观察数据支持强关联，但不能证明这是唯一原因。"
            ),
            "evidence": "事实 + 背景推断",
            "confidence": "较高",
            "stats": [
                {"value": f"{members_before:,.0f}", "label": "实施前月均新增"},
                {"value": f"{members_after:,.0f}", "label": "实施后月均新增"},
                {"value": f"{percent_change(members_after, members_before):.1f}%", "label": "新增变化"},
            ],
            "source": {
                "label": "V2EX：20240505 - 邀请码系统",
                "url": "https://www.v2ex.com/t/1037849",
                "date": "2024-05-06 生效",
                "action": "官方说明",
            },
            "links": [
                {
                    "label": "查看成员变化",
                    "href": "?tab=community&from=2023-05&to=2025-04",
                }
            ],
        },
        {
            "id": "ai-waves",
            "category": "话题变化",
            "title": "AI 讨论从聊天产品扩展到模型与编码智能体",
            "summary": (
                f"话题数据中，ChatGPT 于 {chatgpt_peak[1]} 达到月峰值 {chatgpt_peak[0]}，"
                f"AI 于 {ai_peak[1]} 达到 {ai_peak[0]}；标题关键词中，最近 12 个月 Codex、"
                f"Claude Code 和 Agent 分别出现在 {codex_recent:,}、{claude_code_recent:,} 和 "
                f"{agent_recent:,} 个帖子中。"
            ),
            "interpretation": (
                f"‘模型’话题在 {model_peak[1]} 达到月峰值 {model_peak[0]}；标题中的 Codex、Claude Code "
                f"和 Agent 则分别在 {codex_peak[1]}、{claude_code_peak[1]} 和 {agent_peak[1]} 达到峰值。"
                f"与此同时，Java 和 Python 最近 12 个月分别只有各自滚动峰值的 "
                f"{recent_java / java_peak[0] * 100:.1f}% 和 {recent_python / python_peak[0] * 100:.1f}%。"
                "讨论语言已从‘使用哪款聊天产品’进一步扩展到模型选择、编码代理和工作流实践；标题与话题走势都不等于技术使用量。"
            ),
            "evidence": "话题 + 标题关键词",
            "confidence": "高",
            "stats": [
                {"value": f"{chatgpt_peak[0]:,}", "label": "ChatGPT 话题月峰值"},
                {"value": f"{codex_recent:,}", "label": "近 12 月 Codex 标题"},
                {"value": f"{claude_code_recent:,}", "label": "近 12 月 Claude Code 标题"},
            ],
            "links": [
                link("content", "AI", view="topic-detail", tag="AI"),
                link("content", "Codex", view="content-detail", term="Codex"),
                link("content", "Claude Code", view="content-detail", term="Claude Code"),
                link("content", "Agent", view="content-detail", term="Agent"),
            ],
        },
        {
            "id": "subscription-collaboration",
            "category": "数字消费",
            "title": "拼车、会员与订阅正在形成新的社区协作场景",
            "summary": (
                f"前后五年相比，‘拼车’话题从 {subscription_changes['拼车'][0]:,} 增至 "
                f"{subscription_changes['拼车'][1]:,}，‘88vip’从 {subscription_changes['88vip'][0]:,} 增至 "
                f"{subscription_changes['88vip'][1]:,}，‘订阅’从 {subscription_changes['订阅'][0]:,} 增至 "
                f"{subscription_changes['订阅'][1]:,}。"
            ),
            "interpretation": (
                "相关帖子不只是优惠信息，还包括权益拆分、合租组织、价格比较、账号风险和订阅教程。"
                "V2EX 因而也承担数字服务消费的经验交换与协作组织功能；各话题可能出现在同一帖子中，不能直接相加。"
            ),
            "evidence": "话题结构对比",
            "confidence": "高",
            "stats": [
                {"value": f"{subscription_changes['拼车'][1] / max(subscription_changes['拼车'][0], 1):.1f}x", "label": "拼车话题倍数"},
                {"value": f"{subscription_changes['88vip'][1]:,}", "label": "后五年 88vip"},
                {
                    "value": f"{percent_change(subscription_changes['订阅'][1], subscription_changes['订阅'][0]):+.1f}%",
                    "label": "订阅话题变化",
                },
            ],
            "links": [
                link("content", "拼车", view="topic-detail", tag="拼车"),
                link("content", "88vip", view="topic-detail", tag="88vip"),
                link("content", "订阅", view="topic-detail", tag="订阅"),
            ],
        },
        {
            "id": "apple-mainline",
            "category": "话题结构",
            "title": "Apple 生态是十年间最稳定的社区主线之一",
            "summary": (
                f"最近十年 Apple 生态覆盖 {apple_topics:,} 个帖子，占全部帖子 {apple_share:.2f}%；"
                f"前五年占比为 {apple_previous_share:.2f}%，后五年升至 {apple_current_share:.2f}%。"
            ),
            "interpretation": (
                f"后五年 Apple 生态帖子数下降 {abs(percent_change(apple_current, apple_previous)):.1f}%，"
                f"慢于全站帖子 {abs(topic_change):.1f}% 的降幅。内部关注点也在变化：Apple 和 macOS 话题分别变化 "
                f"{percent_change(tag_count('Apple', current_five_periods), tag_count('Apple', previous_five_periods)):+.1f}%、"
                f"{percent_change(tag_count('macOS', current_five_periods), tag_count('macOS', previous_five_periods)):+.1f}%，"
                f"MacBook 和 iOS 则分别变化 {percent_change(tag_count('MacBook', current_five_periods), tag_count('MacBook', previous_five_periods)):+.1f}%、"
                f"{percent_change(tag_count('iOS', current_five_periods), tag_count('iOS', previous_five_periods)):+.1f}%。"
                "这反映话题结构，不等同于用户设备占有率。"
            ),
            "evidence": "话题板块统计",
            "confidence": "高",
            "stats": [
                {"value": f"{apple_topics:,}", "label": "十年帖子"},
                {"value": f"{apple_share:.2f}%", "label": "十年帖子份额"},
                {"value": f"+{apple_current_share - apple_previous_share:.2f}pp", "label": "后五年份额变化"},
            ],
            "links": [
                link("content", "Apple", view="topic-detail", tag="Apple"),
                link("content", "iOS", view="topic-detail", tag="iOS"),
                link("content", "Mac", view="topic-detail", tag="Mac"),
                link("content", "MacBook", view="topic-detail", tag="MacBook"),
                link("content", "macOS", view="topic-detail", tag="macOS"),
            ],
        },
        {
            "id": "interaction-value-split",
            "category": "内容偏好",
            "title": "收藏与感谢对应两套不同的内容价值",
            "summary": (
                f"收藏 Top 20 与感谢 Top 20 只有 {interaction_overlap} 个帖子重合；收藏榜中有 "
                f"{favorite_programmer_count} 个来自程序员节点，感谢榜中有 {thanked_life_count} 个来自生活节点。"
            ),
            "interpretation": (
                "收藏更偏向以后还会用到的工具、教程、清单和办事指南；感谢则更多流向原创调查、产品复盘、公共经验和个人叙事。"
                f"感谢榜首《{thanked_post['title']}》正是高投入公共信息内容的典型，单一榜单无法代表全部内容价值。"
            ),
            "evidence": "累计互动快照",
            "confidence": "高",
            "stats": [
                {"value": f"{interaction_overlap} / 20", "label": "两榜重合"},
                {"value": f"{favorite_programmer_count} / 20", "label": "收藏榜程序员节点"},
                {"value": f"{thanked_life_count} / 20", "label": "感谢榜生活节点"},
            ],
            "source": {
                "label": f"帖子 #{thanked_post['id']}",
                "url": f"https://www.v2ex.com/t/{thanked_post['id']}",
                "date": datetime.fromtimestamp(
                    thanked_post["create_at"], LOCAL_TIMEZONE
                ).strftime("%Y-%m-%d %H:%M"),
                "action": "查看原帖",
            },
            "links": [
                link("engagement", "收藏榜", postSort="favorite_count", anchor="engagement-posts"),
                link("engagement", "感谢榜", postSort="thank_count", anchor="engagement-posts"),
            ],
        },
        {
            "id": "comment-language",
            "category": "评论表达",
            "title": "高感谢评论常靠短句、反转和即时共鸣传播",
            "summary": (
                f"感谢最多的 100 条评论中，正文长度中位数仅 {thanked_comment_median} 个字符，"
                f"其中 {short_thanked_comments} 条不超过 30 个字符。"
            ),
            "interpretation": (
                "热门评论大量采用直接回应、复述反转、调侃或鲜明立场，说明评论感谢更奖励即时可感知的表达，而非篇幅。"
                "榜单中仍有少量长篇技术解释，短并不等于浅；它反映的是传播方式，不是质量评分。"
            ),
            "evidence": "热门评论 Top 100",
            "confidence": "高",
            "stats": [
                {"value": f"{thanked_comment_median}", "label": "正文长度中位数"},
                {"value": f"{short_thanked_comments} / 100", "label": "不超过 30 字"},
                {"value": f"{top_comment['thank_count']}", "label": "榜首评论感谢"},
            ],
            "links": [link("engagement", "查看热门评论", anchor="engagement-comments")],
        },
        {
            "id": "workday-community",
            "category": "活跃节律",
            "title": "V2EX 的社区节律与工作日高度重合",
            "summary": (
                f"近 10 年有 {work_topics / activity_topics * 100:.1f}% 的帖子和 "
                f"{work_comments / activity_comments * 100:.1f}% 的评论发生在工作日 9:00–17:00。"
            ),
            "interpretation": (
                f"发帖峰值位于{weekday_names[topic_peak[0]]} {topic_peak[1]} 时，评论峰值位于"
                f"{weekday_names[comment_peak[0]]} {comment_peak[1]} 时。社区更像嵌入工作与技术协作场景的信息网络，而不是只在晚间活跃的休闲论坛。"
            ),
            "evidence": "数据事实",
            "confidence": "高",
            "stats": [
                {"value": f"{work_topics / activity_topics * 100:.1f}%", "label": "工作时段帖子"},
                {"value": f"{work_comments / activity_comments * 100:.1f}%", "label": "工作时段评论"},
                {"value": f"{weekday_names[comment_peak[0]]} {comment_peak[1]} 时", "label": "评论峰值"},
            ],
            "links": [link("overview", "查看活跃时段")],
        },
        {
            "id": "short-discussion-window",
            "category": "讨论生命周期",
            "title": "回应很快，但多数讨论的有效窗口很短",
            "summary": (
                f"具备完整观察窗口的帖子中，{within_1h / eligible_topics * 100:.1f}% 在 1 小时内获得首条回复，"
                f"{within_24h / eligible_topics * 100:.1f}% 在 24 小时内获得回复。"
            ),
            "interpretation": (
                f"7 日内总体回复覆盖率为 {response_rate:.1f}%，但发布 7 天后产生的评论只占 30 日评论的 "
                f"{after_7d_share:.1f}%。V2EX 擅长快速反馈，长期持续讨论则属于少数。"
            ),
            "evidence": "数据事实",
            "confidence": "高",
            "stats": [
                {"value": f"{within_1h / eligible_topics * 100:.1f}%", "label": "1 小时内首回"},
                {"value": f"{within_24h / eligible_topics * 100:.1f}%", "label": "24 小时内首回"},
                {"value": f"{after_7d_share:.1f}%", "label": "7 天后评论"},
            ],
            "links": [link("content", "查看生命周期", view="lifecycle")],
        },
    ]

    return {
        "metadata": {
            "generated_at": datetime.now(LOCAL_TIMEZONE).isoformat(timespec="seconds"),
            "generated_by": "Codex 离线数据解读",
            "analysis_start": current_start,
            "analysis_end": current_end,
            "comparison_start": previous_start,
            "comparison_end": previous_end,
            "recent_start": recent_12[0]["period"],
            "recent_end": recent_12[-1]["period"],
        },
        "headline": {
            "title": "技术主线仍在，AI 工具、数字协作与生活经验正在重塑社区讨论",
            "summary": (
                "通用编程与求职话题回落的同时，AI 讨论从聊天产品延伸到模型与编码智能体，数字订阅和生活经验也获得更多空间。"
                "收藏偏向可复用资源，感谢偏向原创调查与真实经历；社区规模趋于存量化，但内容功能比过去更复杂。"
            ),
            "metrics": [
                {"value": f"{percent_change(current_ai, previous_ai):+.1f}%", "label": "AI 话题板块变化"},
                {"value": f"{codex_recent:,}", "label": "近 12 月 Codex 标题"},
                {"value": f"{interaction_overlap} / 20", "label": "收藏与感谢榜重合"},
                {"value": f"{percent_change(members_after, members_before):.1f}%", "label": "邀请码后新增变化"},
            ],
        },
        "observations": observations,
        "notes": [
            "点评基于汇总数据离线生成，主要分析最近 120 个完整月份；前后各 60 个月只用于结构比较。",
            "邀请码时间线引用 V2EX 官方帖子；成员注册数据可能受到档案抓取完整度影响。",
            "收藏、感谢、点击和投票是抓取时累计快照，榜单反映截至抓取日的累计结果，不代表互动发生时间。",
            "话题及话题板块允许重叠，走势描述社区讨论语言的变化，不等同于技术使用量、市场份额或行业需求。",
            "标题关键词按分词结果统计，同一帖子对同一关键词只计一次；它用于补充原始话题，不能代替全文语义分析。",
            "内容偏好由榜单整体结构归纳，用于解释互动方式；不对单篇帖子或评论作质量判断。",
        ],
    }


def update_events(write_component: bool = True):
    events = load_json(ANALYSIS_DIR / "community_events.json")
    write_json(PUBLIC_DIR / "dynamic-events.json", {"events": events})
    if write_component:
        write_manifest("events")


def update_content_hotspots(write_component: bool = True):
    overview = load_json(PUBLIC_DIR / "dynamic-overview.json")
    summary = build_content_hotspots(
        SOURCE_DB,
        PUBLIC_DIR,
        ANALYSIS_DIR,
        MIN_VALID_CREATE_AT,
        overview["metadata"]["default_end_period"],
    )
    write_content_hotspot_audit(
        PUBLIC_DIR,
        ANALYSIS_DIR / "content_hotspot_audit.md",
    )
    refresh_period_ranking_content()
    build_search_suggestions()
    if write_component:
        write_manifest("content_hotspots")
    print(
        "Updated content hotspots: "
        f"{summary['terms']} terms ({summary['ranking_terms']} ranked, "
        f"{summary['detail_entity_terms']} confirmed) from {summary['candidates']} candidates; "
        f"token cache {summary['token_cache_updated']}/{summary['token_cache_total']} updated; "
        f"{summary['latest_period']} Top 10: {', '.join(summary['latest_terms'])}"
    )


def topic_group_definitions(groups: dict) -> list[dict]:
    return [
        {
            "name": name,
            "label": config["label"],
            "color": config["color"],
            "description": config["description"],
            "topics": config["topics"],
            "nodes": config["nodes"],
        }
        for name, config in groups.items()
    ]


def collect_topic_groups(
    source: sqlite3.Connection,
    groups: dict,
    synonyms: dict[str, str],
    tag_stopwords: set[str],
) -> tuple[dict, dict]:
    group_period = defaultdict(lambda: [0, 0, 0])
    group_topic_period = defaultdict(int)
    source.row_factory = sqlite3.Row
    for row in source.execute(
        """
        SELECT node, tag, create_at, reply_count
        FROM topic
        WHERE clicks >= 0 AND create_at >= ?
        ORDER BY id
        """,
        (MIN_VALID_CREATE_AT,),
    ):
        period = month_for(row["create_at"])
        node = row["node"] or "未分类"
        try:
            raw_tags = json.loads(row["tag"] or "[]")
        except json.JSONDecodeError:
            raw_tags = []
        normalized_tags = normalize_tags(raw_tags, synonyms, tag_stopwords)
        for group_name, group in groups.items():
            matched_topics = matching_group_topics(normalized_tags, group)
            if not matches_topic_group(node, normalized_tags, group, matched_topics):
                continue
            values = group_period[(period, group_name)]
            values[0] += 1
            values[1] += max(0, row["reply_count"])
            values[2] += int(bool(matched_topics))
            for topic in matched_topics:
                group_topic_period[(period, group_name, topic)] += 1
    return group_period, group_topic_period


def update_topic_groups():
    groups = prepare_topic_groups(load_json(ANALYSIS_DIR / "topic_groups.json"))
    synonyms = synonym_map()
    tag_stopwords = {
        str(tag).casefold() for tag in load_json(ANALYSIS_DIR / "tag_stopwords.json")
    }
    topic_index = load_json(PUBLIC_DIR / "dynamic-topics.json")
    source = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro", uri=True)
    group_period, group_topic_period = collect_topic_groups(
        source, groups, synonyms, tag_stopwords
    )
    source.close()

    analytics = sqlite3.connect(ANALYTICS_DB)
    analytics.execute("DELETE FROM topic_group_period")
    analytics.execute("DROP TABLE IF EXISTS topic_group_tag_period")
    analytics.execute("DROP TABLE IF EXISTS topic_group_term_period")
    analytics.execute("DROP TABLE IF EXISTS topic_group_node_period")
    analytics.execute(
        """
        CREATE TABLE IF NOT EXISTS topic_group_topic_period (
            period TEXT NOT NULL,
            group_name TEXT NOT NULL,
            topic TEXT NOT NULL,
            topic_count INTEGER NOT NULL,
            PRIMARY KEY (period, group_name, topic)
        )
        """
    )
    analytics.execute("DELETE FROM topic_group_topic_period")
    analytics.executemany(
        "INSERT INTO topic_group_period VALUES (?, ?, ?, ?)",
        [
            (period, group_name, *values[:2])
            for (period, group_name), values in sorted(group_period.items())
        ],
    )
    analytics.executemany(
        "INSERT INTO topic_group_topic_period VALUES (?, ?, ?, ?)",
        [
            (period, group_name, topic, count)
            for (period, group_name, topic), count in sorted(group_topic_period.items())
        ],
    )
    analytics.commit()
    analytics.close()

    topic_index["groups"] = topic_group_definitions(groups)
    topic_index["group_rows"] = [
        [period, group_name, *values[:2]]
        for (period, group_name), values in sorted(group_period.items())
    ]
    topic_index["group_topic_match_rows"] = [
        [period, group_name, values[2]]
        for (period, group_name), values in sorted(group_period.items())
        if values[2]
    ]
    topic_index["group_metadata"] = {
        "classification_basis": ["original_topics", "nodes"],
        "excluded_nodes": sorted(TOPIC_GROUP_EXCLUDED_NODES),
        "item_display_rule": {
            "minimum_count": 3,
            "minimum_share": 0.01,
            "absolute_count": 100,
        },
        "topic_coverage_row_schema": ["period", "group_name", "matched_topic_count"],
    }
    write_json(PUBLIC_DIR / "dynamic-topics.json", topic_index)

    topic_rows_by_year: dict[str, list] = defaultdict(list)
    for (period, group_name, topic), count in sorted(group_topic_period.items()):
        topic_rows_by_year[period[:4]].append([period, group_name, topic, count])
    for year, name in topic_index.get("row_shards", {}).items():
        path = PUBLIC_DIR / name
        payload = load_json(path)
        payload.pop("group_tag_rows", None)
        payload.pop("group_term_rows", None)
        payload.pop("group_node_rows", None)
        payload["group_topic_rows"] = topic_rows_by_year.get(year, [])
        write_json(path, payload)

    update_observations(write_component=False)
    write_manifest("topic_groups")
    print(
        f"Updated topic groups: {len(group_period)} period rows, "
        f"{len(group_topic_period)} group-topic rows"
    )


def update_observations(write_component: bool = True):
    overview = load_json(PUBLIC_DIR / "dynamic-overview.json")
    overview["activity"] = load_json(PUBLIC_DIR / "dynamic-overview-activity.json")["rows"]
    content_rows = load_content_hotspot_rows()
    if not content_rows:
        raise ValueError("content hotspot rows are required to build observations")
    output = build_observation_output(
        overview,
        load_dynamic_topics(),
        load_json(PUBLIC_DIR / "dynamic-lifecycle.json"),
        load_json(PUBLIC_DIR / "dynamic-engagement.json"),
        content_rows,
    )
    for path in PUBLIC_DIR.glob("dynamic-community-signal-posts-*.json"):
        path.unlink()
    write_json(PUBLIC_DIR / "dynamic-observations.json", output)
    update_events(write_component=False)
    if write_component:
        write_manifest("observations")
    print(f"Updated offline observations: {len(output['observations'])} findings")


def build_member_profile_candidates(
    community: dict,
    limit: int = MEMBER_PROFILE_LIMIT,
    min_annual_appearances: int = MEMBER_PROFILE_MIN_ANNUAL_APPEARANCES,
    default_periods: set[str] | None = None,
) -> list[str]:
    leaders = []
    seen = set()
    for key in ("top_topic_authors", "top_commenters", "top_thanked"):
        for member in community.get(key, []):
            username = member.get("username", "")
            if not username or username.casefold() in EXCLUDED_THANK_USERS or username in seen:
                continue
            seen.add(username)
            leaders.append(username)

    recent_values = defaultdict(int)
    recent_appearances = defaultdict(int)
    years = defaultdict(set)
    annual_values = defaultdict(int)
    for row in community.get("rank_rows", []):
        if not row[4] or str(row[4]).casefold() in EXCLUDED_THANK_USERS:
            continue
        if row[0] == "month" and default_periods and row[1] in default_periods:
            recent_appearances[row[4]] += 1
            recent_values[row[4]] += int(row[5])
            continue
        if row[0] != "year":
            continue
        years[row[4]].add(row[1])
        annual_values[row[4]] += int(row[5])
    recent = sorted(
        (username for username in recent_values if username not in seen),
        key=lambda username: (
            -recent_appearances[username], -recent_values[username], username.casefold()
        ),
    )
    seen.update(recent)
    recurring = sorted(
        (
            username for username, active_years in years.items()
            if len(active_years) >= min_annual_appearances and username not in seen
        ),
        key=lambda username: (-len(years[username]), -annual_values[username], username.casefold()),
    )
    return (leaders + recent + recurring)[:limit]


def build_member_comment_heaps(
    source: sqlite3.Connection,
    candidates: list[str],
    limit: int = MEMBER_PROFILE_COMMENT_LIMIT,
) -> dict[str, list]:
    if not candidates:
        return {}
    heaps: dict[str, list] = defaultdict(list)
    placeholders = ",".join("?" for _ in candidates)
    excluded_placeholders = ",".join("?" for _ in EXCLUDED_THANK_USERS)
    for row in source.execute(
        f"""
        SELECT c.id, c.topic_id, c.commenter, c.thank_count, c.no, t.title,
               c.content, c.create_at
        FROM comment c
        JOIN topic t ON t.id = c.topic_id
        WHERE c.create_at >= ? AND c.thank_count > 0 AND t.clicks >= 0
          AND c.commenter IN ({placeholders})
          AND LOWER(c.commenter) NOT IN ({excluded_placeholders})
        """,
        (MIN_VALID_CREATE_AT, *candidates, *EXCLUDED_THANK_USERS),
    ):
        comment = {
            "id": row[0], "topic_id": row[1], "commenter": row[2],
            "thank_count": row[3], "no": row[4], "topic_title": row[5],
            "content": comment_text(row[6]), "create_at": row[7],
        }
        push_top(heaps[row[2]], (max(0, row[3]), row[0], comment), limit)
    return heaps


def update_member_profiles():
    community = load_json(PUBLIC_DIR / "dynamic-community.json")
    overview = load_json(PUBLIC_DIR / "dynamic-overview.json")
    default_end = overview["metadata"]["default_end_period"]
    default_periods = {
        row["period"] for row in overview["periods"] if row["period"] <= default_end
    }
    default_periods = set(sorted(default_periods)[-MEMBER_PROFILE_DEFAULT_MONTHS:])
    candidates = build_member_profile_candidates(community, default_periods=default_periods)
    profiles = {
        username: {
            "periods": defaultdict(lambda: [0, 0, 0, 0]),
            "topic_nodes": defaultdict(int),
            "comment_nodes": defaultdict(int),
            "tags": defaultdict(int),
            "content_terms": defaultdict(int),
            "posts": [],
            "registered_at": 0,
        }
        for username in candidates
    }
    if not candidates:
        raise ValueError("member profile candidate set is empty")

    placeholders = ",".join("?" for _ in candidates)
    synonyms = synonym_map()
    tag_stopwords = {
        str(tag).casefold() for tag in load_json(ANALYSIS_DIR / "tag_stopwords.json")
    }
    content_index = load_json(PUBLIC_DIR / "dynamic-content-hotspots-index.json")
    content_terms = content_display_terms(content_index)
    _, content_member_families = content_family_config(ANALYSIS_DIR)
    selected_tags = set(load_json(PUBLIC_DIR / "dynamic-tag-detail-index.json").get("tags", {}))
    selected_nodes = set(load_json(PUBLIC_DIR / "dynamic-node-detail-index.json").get("nodes", {}))
    source = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    source.execute(
        "ATTACH DATABASE ? AS token_cache",
        (f"file:{ANALYSIS_DIR / 'content_tokens.sqlite'}?mode=ro",),
    )
    comment_heaps = build_member_comment_heaps(source, candidates)

    for row in source.execute(
        f"""
        SELECT topic.id, topic.author, topic.title, topic.node, topic.tag,
               topic.create_at, topic.clicks, topic.reply_count,
               topic.favorite_count, topic.thank_count, topic.votes,
               cached.tokens AS title_tokens
        FROM topic
        LEFT JOIN token_cache.title_tokens AS cached ON cached.topic_id = topic.id
        WHERE topic.clicks >= 0 AND topic.create_at >= ?
          AND topic.author IN ({placeholders})
        ORDER BY topic.id
        """,
        (MIN_VALID_CREATE_AT, *candidates),
    ):
        profile = profiles[row["author"]]
        period = month_for(row["create_at"])
        values = profile["periods"][period]
        values[0] += 1
        values[2] += max(0, row["thank_count"])
        node = row["node"] or "未分类"
        if node in selected_nodes:
            profile["topic_nodes"][node] += 1
        try:
            raw_tags = json.loads(row["tag"] or "[]")
        except json.JSONDecodeError:
            raw_tags = []
        normalized_tags = normalize_tags(raw_tags, synonyms, tag_stopwords)
        for tag in normalized_tags & selected_tags:
            profile["tags"][tag] += 1
        if node.casefold() not in EXCLUDED_REPRESENTATIVE_NODES:
            try:
                title_terms = expand_content_families(
                    set(json.loads(row["title_tokens"] or "[]")),
                    content_member_families,
                )
            except json.JSONDecodeError:
                title_terms = set()
            for term in title_terms & content_terms:
                profile["content_terms"][term] += 1
        score = engagement_score(row)
        post = {
            "id": row["id"], "title": row["title"], "node": node,
            "tags": sorted(normalized_tags & selected_tags), "create_at": row["create_at"],
            "reply_count": row["reply_count"], "favorite_count": row["favorite_count"],
            "thank_count": row["thank_count"], "score": round(score, 3),
        }
        item = (score, row["id"], post)
        heap = profile["posts"]
        if len(heap) < MEMBER_PROFILE_POST_LIMIT:
            heapq.heappush(heap, item)
        elif item > heap[0]:
            heapq.heapreplace(heap, item)

    for row in source.execute(
        f"""
        SELECT c.commenter,
               strftime('%Y-%m', c.create_at, 'unixepoch', '+8 hours') AS period,
               COALESCE(t.node, '未分类') AS node,
               COUNT(*) AS comment_count,
               SUM(MAX(0, c.thank_count)) AS thank_count
        FROM comment c
        JOIN topic t ON t.id = c.topic_id
        WHERE c.create_at >= ? AND c.commenter IN ({placeholders})
        GROUP BY c.commenter, period, node
        """,
        (MIN_VALID_CREATE_AT, *candidates),
    ):
        profile = profiles[row["commenter"]]
        values = profile["periods"][row["period"]]
        values[1] += int(row["comment_count"])
        values[3] += int(row["thank_count"] or 0)
        if row["node"] in selected_nodes:
            profile["comment_nodes"][row["node"]] += int(row["comment_count"])

    for row in source.execute(
        f"SELECT username, create_at FROM member WHERE username IN ({placeholders})",
        candidates,
    ):
        profiles[row["username"]]["registered_at"] = max(0, int(row["create_at"] or 0))
    source.close()

    buckets = {bucket: {"profiles": {}} for bucket in bucket_names(MEMBER_PROFILE_BUCKET_COUNT)}
    comment_buckets = {
        format(index, "02x"): {"comments": {}}
        for index in range(MEMBER_COMMENT_BUCKET_COUNT)
    }
    index_output = {
        "criteria": {
            "limit": MEMBER_PROFILE_LIMIT,
            "default_months": MEMBER_PROFILE_DEFAULT_MONTHS,
            "default_start_period": min(default_periods),
            "default_end_period": max(default_periods),
            "minimum_annual_appearances": MEMBER_PROFILE_MIN_ANNUAL_APPEARANCES,
            "representative_post_limit": MEMBER_PROFILE_POST_LIMIT,
            "representative_comment_limit": MEMBER_PROFILE_COMMENT_LIMIT,
            "representative_comments_require_thank": True,
            "content_term_limit": MEMBER_PROFILE_LIST_LIMIT,
            "content_terms_exclude_nodes": sorted(EXCLUDED_REPRESENTATIVE_NODES),
            "includes_overall_leaders": True,
            "includes_default_range_top_30": True,
            "default_member": next(iter(community.get("top_topic_authors", [])), {}).get("username", ""),
        },
        "members": {},
    }
    for username in candidates:
        profile = profiles[username]
        periods = [
            [period, *values]
            for period, values in sorted(profile["periods"].items())
        ]
        topic_count = sum(row[1] for row in periods)
        comment_count = sum(row[2] for row in periods)
        topic_thanks = sum(row[3] for row in periods)
        comment_thanks = sum(row[4] for row in periods)
        detail = {
            "username": username,
            "registered_at": profile["registered_at"],
            "totals": {
                "topics": topic_count,
                "comments": comment_count,
                "topic_thanks": topic_thanks,
                "comment_thanks": comment_thanks,
            },
            "periods": periods,
            "topic_nodes": sorted(profile["topic_nodes"].items(), key=lambda item: (-item[1], item[0]))[:MEMBER_PROFILE_LIST_LIMIT],
            "comment_nodes": sorted(profile["comment_nodes"].items(), key=lambda item: (-item[1], item[0]))[:MEMBER_PROFILE_LIST_LIMIT],
            "tags": sorted(profile["tags"].items(), key=lambda item: (-item[1], item[0]))[:MEMBER_PROFILE_LIST_LIMIT],
            "content_terms": sorted(profile["content_terms"].items(), key=lambda item: (-item[1], item[0].casefold(), item[0]))[:MEMBER_PROFILE_LIST_LIMIT],
            "posts": [post for _, __, post in sorted(profile["posts"], reverse=True)],
        }
        bucket = member_profile_bucket(username)
        buckets[bucket]["profiles"][username] = detail
        comment_bucket = member_comment_bucket(username)
        comment_buckets[comment_bucket]["comments"][username] = [
            comment for _, __, comment in sorted(comment_heaps.get(username, []), reverse=True)
        ]
        index_output["members"][username] = {
            "bucket": bucket,
            "comment_bucket": comment_bucket,
            "topics": topic_count,
            "comments": comment_count,
        }

    for path in PUBLIC_DIR.glob("dynamic-member-profiles-*.json"):
        path.unlink()
    write_json(PUBLIC_DIR / "dynamic-member-profile-index.json", index_output)
    for bucket, payload in buckets.items():
        write_json(PUBLIC_DIR / f"dynamic-member-profiles-{bucket}.json", payload)
    for path in PUBLIC_DIR.glob("dynamic-member-comments-*.json"):
        path.unlink()
    for bucket, payload in comment_buckets.items():
        write_json(PUBLIC_DIR / f"dynamic-member-comments-{bucket}.json", payload)
    write_manifest("member_profiles")
    print(f"Updated member profiles: {len(candidates)} members across {len(buckets)} shards")


def update_tag_details(title_tokens_ready: bool = False):
    if ANALYTICS_DB.exists():
        with sqlite3.connect(ANALYTICS_DB) as analytics:
            analytics.execute("DROP TABLE IF EXISTS representative_post")
    topics_output = load_dynamic_topics()
    tag_totals = {item["tag"]: int(item["total"]) for item in topics_output["tags"]}
    selected_tags = set(tag_totals)
    default_end_period = load_json(
        PUBLIC_DIR / "dynamic-overview.json"
    )["metadata"]["default_end_period"]
    content_index = load_json(PUBLIC_DIR / "dynamic-content-hotspots-index.json")
    selected_content_terms = content_display_terms(content_index)
    _, content_member_families = content_family_config(ANALYSIS_DIR)
    rows_by_tag = defaultdict(list)
    for row in topics_output.get("rows", []):
        if row[1] in selected_tags:
            rows_by_tag[row[1]].append(row)
    monthly_tag_counts = {
        (row[0], tag): int(row[2])
        for tag, rows in rows_by_tag.items()
        for row in rows
    }
    synonyms = synonym_map()
    tag_stopwords = {
        str(tag).casefold() for tag in load_json(ANALYSIS_DIR / "tag_stopwords.json")
    }
    related = defaultdict(lambda: defaultdict(int))
    related_content = defaultdict(lambda: defaultdict(int))
    nodes = defaultdict(lambda: defaultdict(int))
    authors = defaultdict(lambda: defaultdict(int))
    post_heaps: dict[tuple[str, str], list] = defaultdict(list)
    monthly_post_heaps: dict[tuple[str, str], list] = defaultdict(list)

    if not title_tokens_ready:
        sync_title_token_cache(SOURCE_DB, ANALYSIS_DIR, MIN_VALID_CREATE_AT)

    source = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    attach_title_token_cache(source, ANALYSIS_DIR)
    for row in source.execute(
        """
        SELECT topic.id, topic.author, topic.title, topic.node, topic.tag,
               topic.create_at, topic.clicks, topic.reply_count,
               topic.favorite_count, topic.thank_count, topic.votes,
               cached.tokens AS cached_tokens
        FROM topic
        LEFT JOIN token_cache.title_tokens AS cached ON cached.topic_id = topic.id
        WHERE topic.clicks >= 0 AND topic.create_at >= ?
        ORDER BY topic.id
        """,
        (MIN_VALID_CREATE_AT,),
    ):
        period = month_for(row["create_at"])
        if period > default_end_period:
            continue
        try:
            raw_tags = json.loads(row["tag"] or "[]")
        except json.JSONDecodeError:
            raw_tags = []
        normalized_tags = normalize_tags(raw_tags, synonyms, tag_stopwords)
        detail_tags = normalized_tags & selected_tags
        if not detail_tags:
            continue
        node = row["node"] or "未分类"
        title_terms = expand_content_families(
            cached_title_tokens(row), content_member_families
        ) & selected_content_terms
        if node.casefold() not in EXCLUDED_REPRESENTATIVE_NODES:
            post = {
                "id": row["id"], "period": period, "title": row["title"],
                "node": node, "tags": sorted(detail_tags),
                "create_at": row["create_at"], "clicks": row["clicks"],
                "reply_count": row["reply_count"],
                "favorite_count": row["favorite_count"],
                "thank_count": row["thank_count"], "votes": row["votes"],
                "author": row["author"],
            }
            score = engagement_score(row)
            post["score"] = round(score, 3)
            push_tag_representative_candidates(post_heaps, detail_tags, post, score)
            for tag in detail_tags:
                push_tag_monthly_representative_candidates(
                    monthly_post_heaps,
                    {tag},
                    post,
                    score,
                    limit=tag_monthly_representative_limit(
                        monthly_tag_counts.get((period, tag), 0)
                    ),
                )
        for tag in detail_tags:
            nodes[tag][node] += 1
            if row["author"]:
                authors[tag][row["author"]] += 1
            for other in detail_tags:
                if other != tag:
                    related[tag][other] += 1
            for term in title_terms:
                related_content[tag][term] += 1
    source.close()

    posts_by_tag = group_tag_representative_posts(post_heaps)
    monthly_posts_by_tag = group_tag_monthly_representative_posts(
        monthly_post_heaps
    )

    buckets = {bucket: {"details": {}} for bucket in bucket_names(TAG_DETAIL_BUCKET_COUNT)}
    monthly_buckets = {
        bucket: {"posts": {}}
        for bucket in bucket_names(TAG_PERIOD_POST_BUCKET_COUNT)
    }
    index_output = {
        "criteria": {
            "representative_posts_per_year": TAG_REPRESENTATIVE_POSTS_PER_YEAR,
            "representative_posts_per_month": TAG_REPRESENTATIVE_POSTS_PER_MONTH,
            "representative_posts_per_active_month": TAG_REPRESENTATIVE_POSTS_PER_ACTIVE_MONTH,
            "active_month_minimum_topics": TAG_REPRESENTATIVE_ACTIVE_MONTH_MIN_TOPICS,
            "representative_posts_per_very_active_month": TAG_REPRESENTATIVE_POSTS_PER_VERY_ACTIVE_MONTH,
            "very_active_month_minimum_topics": TAG_REPRESENTATIVE_VERY_ACTIVE_MONTH_MIN_TOPICS,
            "excluded_representative_nodes": sorted(EXCLUDED_REPRESENTATIVE_NODES),
        },
        "tags": {},
    }
    for tag in sorted(selected_tags):
        bucket = tag_detail_bucket(tag)
        period_post_bucket = tag_period_post_bucket(tag)
        detail = {
            "tag": tag,
            "total": tag_totals[tag],
            "rows": rows_by_tag[tag],
            "related": sorted(related[tag].items(), key=lambda item: (-item[1], item[0]))[:TAG_DETAIL_LIST_LIMIT],
            "related_content": sorted(
                related_content[tag].items(),
                key=lambda item: (-item[1], item[0].casefold(), item[0]),
            )[:TAG_DETAIL_LIST_LIMIT],
            "nodes": sorted(nodes[tag].items(), key=lambda item: (-item[1], item[0]))[:TAG_DETAIL_LIST_LIMIT],
            "authors": sorted(authors[tag].items(), key=lambda item: (-item[1], item[0]))[:TAG_DETAIL_LIST_LIMIT],
            "posts": posts_by_tag[tag],
        }
        buckets[bucket]["details"][tag] = detail
        monthly_buckets[period_post_bucket]["posts"][tag] = monthly_posts_by_tag[tag]
        index_output["tags"][tag] = {
            "bucket": bucket,
            "period_post_bucket": period_post_bucket,
            "total": tag_totals[tag],
        }

    for path in PUBLIC_DIR.glob("dynamic-tag-details-*.json"):
        path.unlink()
    for path in PUBLIC_DIR.glob("dynamic-tag-period-posts-*.json"):
        path.unlink()
    write_json(PUBLIC_DIR / "dynamic-tag-detail-index.json", index_output)
    for bucket, payload in buckets.items():
        write_json(PUBLIC_DIR / f"dynamic-tag-details-{bucket}.json", payload)
    for bucket, payload in monthly_buckets.items():
        write_json(PUBLIC_DIR / f"dynamic-tag-period-posts-{bucket}.json", payload)
    legacy_path = PUBLIC_DIR / "dynamic-representative-posts.json"
    if legacy_path.exists():
        legacy_path.unlink()
    write_manifest("tag_details")
    print(
        f"Updated tag details: {len(selected_tags)} tags across {len(buckets)} shards; "
        f"monthly Top {TAG_REPRESENTATIVE_POSTS_PER_MONTH}-"
        f"{TAG_REPRESENTATIVE_POSTS_PER_VERY_ACTIVE_MONTH} posts across "
        f"{len(monthly_buckets)} lazy shards"
    )


def update_node_details(title_tokens_ready: bool = False):
    nodes_output = load_json(PUBLIC_DIR / "dynamic-nodes.json")
    default_end_period = load_json(
        PUBLIC_DIR / "dynamic-overview.json"
    )["metadata"]["default_end_period"]
    node_totals = defaultdict(int)
    node_rows = defaultdict(list)
    for row in nodes_output.get("rows", []):
        _, node, topic_count, *_ = row
        node_totals[node] += int(topic_count)
        node_rows[node].append(row)
    monthly_node_counts = {
        (row[0], node): int(row[2])
        for node, rows in node_rows.items()
        for row in rows
    }
    selected_nodes = {
        node for node, total in node_totals.items()
        if total >= NODE_DETAIL_MIN_TOPICS
    }

    topics_output = load_dynamic_topics()
    selected_tags = {item["tag"] for item in topics_output["tags"]}
    content_index = load_json(PUBLIC_DIR / "dynamic-content-hotspots-index.json")
    selected_content_terms = content_display_terms(content_index)
    _, content_member_families = content_family_config(ANALYSIS_DIR)
    synonyms = synonym_map()
    tag_stopwords = {
        str(tag).casefold() for tag in load_json(ANALYSIS_DIR / "tag_stopwords.json")
    }
    tags = defaultdict(lambda: defaultdict(int))
    content_terms = defaultdict(lambda: defaultdict(int))
    authors = defaultdict(lambda: defaultdict(int))
    post_heaps = defaultdict(list)
    annual_post_heaps: dict[tuple[str, str], list] = defaultdict(list)
    monthly_post_heaps: dict[tuple[str, str], list] = defaultdict(list)

    if not title_tokens_ready:
        sync_title_token_cache(SOURCE_DB, ANALYSIS_DIR, MIN_VALID_CREATE_AT)

    source = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    attach_title_token_cache(source, ANALYSIS_DIR)
    for row in source.execute(
        """
        SELECT topic.id, topic.author, topic.title, topic.node, topic.tag,
               topic.create_at, topic.clicks, topic.reply_count,
               topic.favorite_count, topic.thank_count, topic.votes,
               cached.tokens AS cached_tokens
        FROM topic
        LEFT JOIN token_cache.title_tokens AS cached ON cached.topic_id = topic.id
        WHERE topic.clicks >= 0 AND topic.create_at >= ?
        ORDER BY topic.id
        """,
        (MIN_VALID_CREATE_AT,),
    ):
        node = row["node"] or "未分类"
        if node not in selected_nodes:
            continue
        period = month_for(row["create_at"])
        if period > default_end_period:
            continue
        try:
            raw_tags = json.loads(row["tag"] or "[]")
        except json.JSONDecodeError:
            raw_tags = []
        normalized_tags = normalize_tags(raw_tags, synonyms, tag_stopwords)
        for tag in normalized_tags & selected_tags:
            tags[node][tag] += 1
        if row["author"]:
            authors[node][row["author"]] += 1
        if node.casefold() in EXCLUDED_REPRESENTATIVE_NODES:
            continue
        title_terms = expand_content_families(
            cached_title_tokens(row), content_member_families
        )
        for term in title_terms & selected_content_terms:
            content_terms[node][term] += 1
        post = {
            "id": row["id"], "title": row["title"], "node": node,
            "author": row["author"], "create_at": row["create_at"],
            "period": period, "tags": sorted(normalized_tags & selected_tags),
            "clicks": max(0, row["clicks"]),
            "reply_count": max(0, row["reply_count"]),
            "favorite_count": max(0, row["favorite_count"]),
            "thank_count": max(0, row["thank_count"]),
            "votes": max(0, row["votes"]),
        }
        score = engagement_score(row)
        post["score"] = round(score, 3)
        push_top(post_heaps[node], (score, row["id"], post), NODE_DETAIL_POST_LIMIT)
        push_top(
            annual_post_heaps[(node, period[:4])],
            (score, row["id"], post),
            NODE_REPRESENTATIVE_POSTS_PER_YEAR,
        )
        push_top(
            monthly_post_heaps[(node, period)],
            (score, row["id"], post),
            node_monthly_representative_limit(
                monthly_node_counts.get((period, node), 0)
            ),
        )
    source.close()

    annual_posts_by_node = group_tag_monthly_representative_posts(
        annual_post_heaps
    )
    monthly_posts_by_node = group_tag_monthly_representative_posts(
        monthly_post_heaps
    )

    buckets = {bucket: {"details": {}} for bucket in bucket_names(NODE_DETAIL_BUCKET_COUNT)}
    period_buckets = {
        bucket: {"posts": {}}
        for bucket in bucket_names(NODE_PERIOD_POST_BUCKET_COUNT)
    }
    index_output = {
        "criteria": {
            "minimum_topics": NODE_DETAIL_MIN_TOPICS,
            "observed_node_count": len(node_totals),
            "included_node_count": len(selected_nodes),
            "included_share": round(len(selected_nodes) / len(node_totals), 4),
            "detail_limit": NODE_DETAIL_LIST_LIMIT,
            "representative_post_limit": NODE_DETAIL_POST_LIMIT,
            "representative_posts_per_year": NODE_REPRESENTATIVE_POSTS_PER_YEAR,
            "representative_posts_per_month": NODE_REPRESENTATIVE_POSTS_PER_MONTH,
            "representative_posts_per_active_month": NODE_REPRESENTATIVE_POSTS_PER_ACTIVE_MONTH,
            "active_month_minimum_topics": NODE_REPRESENTATIVE_ACTIVE_MONTH_MIN_TOPICS,
            "representative_posts_per_very_active_month": NODE_REPRESENTATIVE_POSTS_PER_VERY_ACTIVE_MONTH,
            "very_active_month_minimum_topics": NODE_REPRESENTATIVE_VERY_ACTIVE_MONTH_MIN_TOPICS,
            "excluded_representative_nodes": sorted(EXCLUDED_REPRESENTATIVE_NODES),
        },
        "nodes": {},
    }
    for node in sorted(selected_nodes, key=lambda item: (-node_totals[item], item.casefold())):
        bucket = node_detail_bucket(node)
        period_post_bucket = node_period_post_bucket(node)
        period_posts = dict(annual_posts_by_node.get(node, {}))
        period_posts.update(monthly_posts_by_node.get(node, {}))
        detail = {
            "node": node,
            "total": node_totals[node],
            "rows": node_rows[node],
            "tags": sorted(tags[node].items(), key=lambda item: (-item[1], item[0]))[:NODE_DETAIL_LIST_LIMIT],
            "content_terms": sorted(
                content_terms[node].items(),
                key=lambda item: (-item[1], item[0].casefold(), item[0]),
            )[:NODE_DETAIL_LIST_LIMIT],
            "authors": sorted(authors[node].items(), key=lambda item: (-item[1], item[0].casefold()))[:NODE_DETAIL_LIST_LIMIT],
            "posts": [
                post
                for score, _, post in sorted(post_heaps[node], reverse=True)
            ],
        }
        buckets[bucket]["details"][node] = detail
        period_buckets[period_post_bucket]["posts"][node] = period_posts
        index_output["nodes"][node] = {
            "bucket": bucket,
            "period_post_bucket": period_post_bucket,
            "total": node_totals[node],
        }

    for path in PUBLIC_DIR.glob("dynamic-node-details-*.json"):
        path.unlink()
    for path in PUBLIC_DIR.glob("dynamic-node-period-posts-*.json"):
        path.unlink()
    node_label_config = load_json(ANALYSIS_DIR / "node_labels.json")
    write_json(
        PUBLIC_DIR / "dynamic-node-metadata.json",
        {
            "source_url": node_label_config["source_url"],
            "minimum_topics": NODE_DETAIL_MIN_TOPICS,
            "labels": node_label_config["labels"],
            "analyzed_nodes": sorted(selected_nodes),
        },
    )
    write_json(PUBLIC_DIR / "dynamic-node-detail-index.json", index_output)
    for bucket, payload in buckets.items():
        write_json(PUBLIC_DIR / f"dynamic-node-details-{bucket}.json", payload)
    for bucket, payload in period_buckets.items():
        write_json(PUBLIC_DIR / f"dynamic-node-period-posts-{bucket}.json", payload)
    write_manifest("node_details")
    print(
        f"Updated node details: {len(selected_nodes)} nodes across {len(buckets)} shards; "
        f"monthly Top {NODE_REPRESENTATIVE_POSTS_PER_MONTH}-"
        f"{NODE_REPRESENTATIVE_POSTS_PER_VERY_ACTIVE_MONTH} and annual Top "
        f"{NODE_REPRESENTATIVE_POSTS_PER_YEAR} posts across "
        f"{len(period_buckets)} lazy shards"
    )


def build_member_rank_rows(
    source: sqlite3.Connection,
    limit: int = MEMBER_RANKING_LIMIT,
    default_end_period: str | None = None,
) -> list[list]:
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

    if default_end_period is None:
        default_end_period = previous_period(
            datetime.now(LOCAL_TIMEZONE).strftime("%Y-%m")
        )
    for grain, period_sql, period_filter in (
        ("month", "period", ""),
        ("year", "substr(period, 1, 4)", f"WHERE period <= '{default_end_period}'"),
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
        thanks_period_filter = f"AND period <= '{default_end_period}'" if grain == "year" else ""
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
        DROP TABLE IF EXISTS topic_group_tag_period;
        DROP TABLE IF EXISTS topic_group_term_period;
        DROP TABLE IF EXISTS topic_group_topic_period;
        DROP TABLE IF EXISTS topic_group_node_period;
        DROP TABLE IF EXISTS representative_post;
        DROP TABLE IF EXISTS first_reply_period;
        DROP TABLE IF EXISTS comment_age_period;
        DROP TABLE IF EXISTS long_tail_period;
        DROP TABLE IF EXISTS discussion_structure_period;
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
        CREATE TABLE topic_group_topic_period (
            period TEXT NOT NULL,
            group_name TEXT NOT NULL,
            topic TEXT NOT NULL,
            topic_count INTEGER NOT NULL,
            PRIMARY KEY (period, group_name, topic)
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
        CREATE TABLE discussion_structure_period (
            period TEXT PRIMARY KEY,
            replied_topic_count INTEGER NOT NULL,
            comment_count INTEGER NOT NULL,
            commenter_count INTEGER NOT NULL,
            author_participated_count INTEGER NOT NULL,
            mention_comment_count INTEGER NOT NULL
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


def build(rebuild_topic_derivatives: bool = True):
    current_period = datetime.now(LOCAL_TIMEZONE).strftime("%Y-%m")
    groups = prepare_topic_groups(load_json(ANALYSIS_DIR / "topic_groups.json"))
    synonyms = synonym_map()
    tag_stopwords = {
        str(tag).casefold() for tag in load_json(ANALYSIS_DIR / "tag_stopwords.json")
    }
    period_metrics = defaultdict(lambda: [0, 0, 0, 0, 0, 0])
    topic_activity = defaultdict(int)
    nodes = defaultdict(lambda: [0, 0, 0])
    tags = defaultdict(lambda: [0, 0, 0])
    tag_totals = defaultdict(int)
    group_period = defaultdict(lambda: [0, 0, 0])
    group_topic_period = defaultdict(int)
    monthly_score_heaps: dict[str, list] = defaultdict(list)
    monthly_post_heaps: dict[tuple[str, str], list] = defaultdict(list)
    annual_score_heaps: dict[str, list] = defaultdict(list)
    annual_post_heaps: dict[tuple[str, str], list] = defaultdict(list)
    engagement_period = defaultdict(lambda: [0, 0, 0, 0, 0, 0])
    interaction_heaps: dict[str, list] = defaultdict(list)

    source = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    latest_topic_at = source.execute(
        "SELECT MAX(create_at) FROM topic WHERE clicks >= 0 AND create_at >= ?",
        (MIN_VALID_CREATE_AT,),
    ).fetchone()[0]
    data_as_of = max(
        latest_topic_at or 0,
        source.execute("SELECT MAX(create_at) FROM comment").fetchone()[0] or 0,
    )
    default_end_candidate = source_complete_through(
        latest_topic_at, data_as_of, current_period
    )
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
            matched_topics = matching_group_topics(normalized_tags, group)
            if matches_topic_group(node, normalized_tags, group, matched_topics):
                values = group_period[(period, group_name)]
                values[0] += 1
                values[1] += max(0, row["reply_count"])
                values[2] += int(bool(matched_topics))
                for topic in matched_topics:
                    group_topic_period[(period, group_name, topic)] += 1

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
        post["score"] = round(score, 3)
        if node.casefold() not in EXCLUDED_REPRESENTATIVE_NODES:
            push_top(monthly_score_heaps[period], (score, row["id"], post))
            if period <= default_end_candidate:
                year = period[:4]
                push_top(annual_score_heaps[year], (score, row["id"], post))
            for metric in MONTHLY_POST_METRICS:
                push_top(
                    monthly_post_heaps[(period, metric)],
                    (max(0, row[metric]), row["id"], post),
                )
                if period <= default_end_candidate:
                    push_top(
                        annual_post_heaps[(period[:4], metric)],
                        (max(0, row[metric]), row["id"], post),
                    )

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

    discussion_structure_period = {
        period: (replied_topics, comments, commenters, author_participated, mentions)
        for period, replied_topics, comments, commenters, author_participated, mentions
        in source.execute(
            """
            WITH topic_structure AS (
                SELECT strftime('%Y-%m', t.create_at, 'unixepoch', '+8 hours') AS period,
                       t.id,
                       COUNT(c.id) AS comment_count,
                       COUNT(DISTINCT c.commenter) AS commenter_count,
                       MAX(CASE WHEN c.commenter = t.author THEN 1 ELSE 0 END) AS author_participated,
                       SUM(CASE WHEN INSTR(c.content, '@') > 0 THEN 1 ELSE 0 END) AS mention_count
                FROM topic t
                JOIN comment c ON c.topic_id = t.id
                  AND c.create_at >= t.create_at
                  AND c.create_at - t.create_at < 604800
                WHERE t.clicks >= 0 AND t.create_at >= ? AND t.create_at <= ?
                GROUP BY t.id
            )
            SELECT period, COUNT(*), SUM(comment_count), SUM(commenter_count),
                   SUM(author_participated), SUM(mention_count)
            FROM topic_structure
            GROUP BY period
            ORDER BY period
            """,
            (MIN_VALID_CREATE_AT, seven_day_cutoff),
        )
    }

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
    monthly_comment_heaps = build_monthly_comment_heaps(
        source, default_end_candidate
    )
    annual_comment_heaps = build_annual_comment_heaps(source, default_end_candidate)
    member_rank_rows = build_member_rank_rows(
        source, default_end_period=default_end_candidate
    )
    annual_activity = build_annual_activity(source, default_end_candidate)
    scale_distribution_output = build_scale_distribution(
        source, tags, nodes, default_end_candidate
    )
    source.close()

    configured_topic_names = {
        str(topic).casefold()
        for group in groups.values()
        for topic in group.get("topics", [])
    }
    group_topic_tags = {
        tag
        for tag, total in tag_totals.items()
        if total >= 20 and tag.casefold() in configured_topic_names
    }
    selected_tag_items = select_topic_tags(
        tag_totals,
        focused_tags=FOCUSED_TAGS | group_topic_tags,
    )
    top_tags = {tag for tag, _ in selected_tag_items}
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
            (period, group_name, *values[:2])
            for (period, group_name), values in sorted(group_period.items())
        ],
    )
    analytics.executemany(
        "INSERT INTO topic_group_topic_period VALUES (?, ?, ?, ?)",
        [
            (period, group_name, topic, topic_count)
            for (period, group_name, topic), topic_count in sorted(group_topic_period.items())
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
        "INSERT INTO discussion_structure_period VALUES (?, ?, ?, ?, ?, ?)",
        [
            (period, *values)
            for period, values in sorted(discussion_structure_period.items())
        ],
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
    incomplete_periods = [period for period in periods if period > default_end_candidate]
    complete_periods = [period for period in periods if period <= default_end_candidate]
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
            "participant_count": scale_distribution_output["metadata"]["counts"]["participants"],
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
    }
    overview_activity_output = {
        "rows": [
            list(row) for row in analytics.execute("SELECT * FROM activity_period ORDER BY period, weekday, hour")
        ],
    }
    nodes_output = {
        "rows": [list(row) for row in analytics.execute("SELECT * FROM node_period ORDER BY period, node")]
    }
    topics_output = {
        "tags": [
            {"tag": tag, "total": total}
            for tag, total in selected_tag_items
        ],
        "rows": [list(row) for row in analytics.execute("SELECT * FROM tag_period ORDER BY period, tag")],
        "groups": topic_group_definitions(groups),
        "group_metadata": {
            "classification_basis": ["original_topics", "nodes"],
            "excluded_nodes": sorted(TOPIC_GROUP_EXCLUDED_NODES),
            "item_display_rule": {
                "minimum_count": 3,
                "minimum_share": 0.01,
                "absolute_count": 100,
            },
            "topic_coverage_row_schema": ["period", "group_name", "matched_topic_count"],
        },
        "group_rows": [list(row) for row in analytics.execute("SELECT * FROM topic_group_period ORDER BY period, group_name")],
        "group_topic_match_rows": [
            [period, group_name, values[2]]
            for (period, group_name), values in sorted(group_period.items())
            if values[2]
        ],
        "group_topic_rows": [
            list(row) for row in analytics.execute(
                "SELECT * FROM topic_group_topic_period ORDER BY period, group_name, topic"
            )
        ],
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
        "discussion_structure_rows": [
            list(row) for row in analytics.execute(
                "SELECT * FROM discussion_structure_period ORDER BY period"
            )
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
    topic_row_shards: dict[str, list] = defaultdict(list)
    for row in topics_output["rows"]:
        topic_row_shards[row[0][:4]].append(row)
    topic_group_topic_shards: dict[str, list] = defaultdict(list)
    for row in topics_output["group_topic_rows"]:
        topic_group_topic_shards[row[0][:4]].append(row)
    for path in PUBLIC_DIR.glob("dynamic-topic-rows-*.json"):
        path.unlink()
    topic_index_output = {
        key: value
        for key, value in topics_output.items()
        if key not in {"rows", "group_topic_rows"}
    }
    topic_index_output["row_shards"] = {}
    for year, rows in sorted(topic_row_shards.items()):
        name = f"dynamic-topic-rows-{year}.json"
        write_json(
            PUBLIC_DIR / name,
            {
                "rows": rows,
                "group_topic_rows": topic_group_topic_shards.get(year, []),
            },
        )
        topic_index_output["row_shards"][year] = name

    for name, payload in (
        ("dynamic-overview.json", overview),
        ("dynamic-overview-activity.json", overview_activity_output),
        ("dynamic-nodes.json", nodes_output),
        ("dynamic-topics.json", topic_index_output),
        ("dynamic-lifecycle.json", lifecycle_output),
        ("dynamic-community.json", community_output),
        ("dynamic-engagement.json", engagement_output),
        ("dynamic-scale-distribution.json", scale_distribution_output),
    ):
        write_json(PUBLIC_DIR / name, payload)
    write_monthly_rankings(
        monthly_score_heaps,
        monthly_post_heaps,
        monthly_comment_heaps,
        build_monthly_summaries(topics_output, nodes_output, community_output),
    )
    annual_summaries = build_annual_summaries(
        topics_output, nodes_output, community_output, overview["metadata"]["default_end_period"]
    )
    for year, activity in annual_activity.items():
        annual_summaries.setdefault(
            year, {"tags": [], "content": [], "nodes": [], "activity": {}}
        )["activity"] = activity
    write_annual_rankings(
        annual_score_heaps,
        annual_post_heaps,
        annual_comment_heaps,
        annual_summaries,
    )
    analytics.close()
    if rebuild_topic_derivatives:
        update_content_hotspots(write_component=False)
    else:
        print("Reused title hotspot outputs; topic facts are unchanged")
        refresh_period_ranking_content()
    update_observations(write_component=False)
    if rebuild_topic_derivatives:
        update_tag_details(title_tokens_ready=True)
        update_node_details(title_tokens_ready=True)
    else:
        print("Reused topic and node detail shards; topic facts are unchanged")
    update_member_profiles()
    update_about_coverage(write_component=False)
    write_manifest("full", full_build=True)
    print(
        f"Built {ANALYTICS_DB}: {len(periods)} periods, "
        f"{len(nodes)} node rows, {len(top_tags)} tags"
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
    print("--representative-only now rebuilds topic details and their per-topic representative posts")
    update_tag_details()
    update_node_details(title_tokens_ready=True)


def update_community_rankings(limit: int = MEMBER_RANKING_LIMIT):
    output_path = PUBLIC_DIR / "dynamic-community.json"
    output = load_json(output_path)
    overview = load_json(PUBLIC_DIR / "dynamic-overview.json")
    source = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro", uri=True)
    output["rank_rows"] = build_member_rank_rows(
        source,
        limit,
        overview["metadata"]["default_end_period"],
    )
    source.close()
    write_json(output_path, output)
    write_manifest("community")
    update_member_profiles()
    print(f"Updated member rankings: {len(output['rank_rows'])} period ranking rows")


def update_monthly_rankings():
    score_heaps: dict[str, list] = defaultdict(list)
    metric_heaps: dict[tuple[str, str], list] = defaultdict(list)
    overview = load_json(PUBLIC_DIR / "dynamic-overview.json")
    default_end_period = overview["metadata"]["default_end_period"]
    source = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    for row in source.execute(
        """
        SELECT id, author, title, node, create_at, clicks, reply_count,
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
        period = month_for(row["create_at"])
        if period > default_end_period:
            continue
        score = engagement_score(row)
        post = {
            "id": row["id"], "period": period, "author": row["author"],
            "title": row["title"], "node": node, "create_at": row["create_at"],
            "clicks": row["clicks"], "reply_count": row["reply_count"],
            "favorite_count": row["favorite_count"], "thank_count": row["thank_count"],
            "votes": row["votes"], "score": round(score, 3),
        }
        push_top(score_heaps[period], (score, row["id"], post))
        for metric in MONTHLY_POST_METRICS:
            push_top(
                metric_heaps[(period, metric)],
                (max(0, row[metric]), row["id"], post),
            )
    comment_heaps = build_monthly_comment_heaps(source, default_end_period)
    source.close()
    write_monthly_rankings(
        score_heaps,
        metric_heaps,
        comment_heaps,
        build_monthly_summaries(
            load_dynamic_topics(),
            load_json(PUBLIC_DIR / "dynamic-nodes.json"),
            load_json(PUBLIC_DIR / "dynamic-community.json"),
        ),
    )
    refresh_period_ranking_content()
    write_manifest("monthly_rankings")
    print(f"Updated monthly rankings: {len(score_heaps)} periods")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--engagement-only", action="store_true")
    parser.add_argument("--community-only", action="store_true")
    parser.add_argument("--tag-details-only", action="store_true")
    parser.add_argument("--node-details-only", action="store_true")
    parser.add_argument("--representative-only", action="store_true")
    parser.add_argument("--member-profiles-only", action="store_true")
    parser.add_argument("--observations-only", action="store_true")
    parser.add_argument("--monthly-rankings-only", action="store_true")
    parser.add_argument("--content-hotspots-only", action="store_true")
    parser.add_argument("--topic-groups-only", action="store_true")
    parser.add_argument("--if-changed", action="store_true")
    parser.add_argument("--interaction-limit", type=int, default=INTERACTION_POST_RANKING_LIMIT)
    parser.add_argument("--comment-limit", type=int, default=COMMENT_RANKING_LIMIT)
    parser.add_argument("--member-limit", type=int, default=MEMBER_RANKING_LIMIT)
    args = parser.parse_args()
    if args.engagement_only:
        update_engagement_rankings(args.interaction_limit, args.comment_limit)
    elif args.community_only:
        update_community_rankings(args.member_limit)
        update_about_coverage()
    elif args.tag_details_only:
        update_tag_details()
        update_node_details(title_tokens_ready=True)
        update_about_coverage()
    elif args.node_details_only:
        update_node_details()
        update_about_coverage()
    elif args.representative_only:
        update_representative_posts()
        update_about_coverage()
    elif args.member_profiles_only:
        update_member_profiles()
        update_about_coverage()
    elif args.observations_only:
        update_observations()
    elif args.monthly_rankings_only:
        update_monthly_rankings()
    elif args.content_hotspots_only:
        update_content_hotspots()
        update_about_coverage()
    elif args.topic_groups_only:
        update_topic_groups()
    elif args.if_changed:
        changes = source_changes_since_full_build()
        if changes == set():
            print("Analysis source facts unchanged; skipped analytics build")
        else:
            build(
                rebuild_topic_derivatives=(
                    changes is None
                    or "topic" in changes
                    or "analysis" in changes
                )
            )
    else:
        build()
