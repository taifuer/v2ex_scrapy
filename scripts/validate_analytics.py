#!/usr/bin/env python3
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v2ex_scrapy.analysis_policy import (  # noqa: E402
    PERIOD_POST_METRIC_MINIMUMS,
    REPRESENTATIVE_COMMENT_MIN_THANKS,
)

PUBLIC_DIR = ROOT / "analysis" / "v2ex-analysis" / "public"
PERIOD_RE = re.compile(r"^\d{4}-\d{2}$")
LOCAL_TIMEZONE = timezone(timedelta(hours=8))


def load(name: str):
    with (PUBLIC_DIR / name).open(encoding="utf-8") as fp:
        return json.load(fp)


def require(condition: bool, message: str):
    if not condition:
        raise ValueError(message)


def validate_stage_hotspots(
    payload: dict,
    entity: str,
    valid_keys: set[str],
    start_period: str,
    end_period: str,
):
    require(
        payload.get("row_schema") == [
            "key", "start_period", "peak_period", "end_period", "peak_count",
            "peak_share_percent", "baseline_share_percent", "lift", "score",
        ],
        f"invalid stage hotspot schema: {entity}",
    )
    expected_rules = {
        "month": {
            "baseline_periods": 12,
            "minimum_history": 6,
            "minimum_count": 20,
            "minimum_lift": 1.8,
            "minimum_share_delta": 0.0003,
        },
        "year": {
            "baseline_periods": 3,
            "minimum_history": 2,
            "minimum_count": 50,
            "minimum_lift": 1.5,
            "minimum_share_delta": 0.0005,
        },
    }
    require(payload.get("rules") == expected_rules, f"invalid stage hotspot rules: {entity}")
    for grain, rules in expected_rules.items():
        rows = payload.get(grain)
        require(isinstance(rows, list) and rows, f"stage hotspots missing: {entity} {grain}")
        seen = set()
        lower = start_period if grain == "month" else start_period[:4]
        upper = end_period if grain == "month" else end_period[:4]
        pattern = PERIOD_RE if grain == "month" else re.compile(r"^\d{4}$")
        for row in rows:
            require(len(row) == 9, f"invalid stage hotspot row: {entity} {grain}")
            key, start, peak, end, count, peak_share, baseline_share, lift, score = row
            require(key in valid_keys, f"unknown stage hotspot key: {entity} {key}")
            require(
                pattern.match(start) and pattern.match(peak) and pattern.match(end),
                f"invalid stage hotspot period: {entity} {key}",
            )
            require(
                lower <= start <= peak <= end <= upper,
                f"stage hotspot period is out of range: {entity} {key}",
            )
            require(
                count >= rules["minimum_count"]
                and peak_share > baseline_share >= 0
                and (lift is None or lift >= rules["minimum_lift"])
                and score > 0,
                f"invalid stage hotspot values: {entity} {key}",
            )
            signature = (key, start, peak, end)
            require(signature not in seen, f"duplicate stage hotspot: {entity} {signature}")
            seen.add(signature)


def month_index(period: str) -> int:
    year, month = map(int, period.split("-"))
    return year * 12 + month - 1


def post_year(post: dict) -> str:
    if post.get("period"):
        return str(post["period"])[:4]
    return datetime.fromtimestamp(post["create_at"], LOCAL_TIMEZONE).strftime("%Y")


def has_comment_content(comment: dict) -> bool:
    return isinstance(comment.get("content"), str) and bool(comment["content"].strip())


def validate_no_legacy_representative_comments(detail: dict, entity: str):
    require("comments" not in detail, f"legacy representative comments remain: {entity}")
    require("comment_summary" not in detail, f"legacy comment summary remains: {entity}")


def validate_comment_criteria(criteria: dict, entity: str):
    require(
        "representative_comment_limit" not in criteria,
        f"legacy representative comment limit remains: {entity}",
    )
    require(
        "representative_comments_require_thank" not in criteria,
        f"legacy representative comment threshold remains: {entity}",
    )
    require(
        criteria.get("representative_comment_minimum_thanks")
        == REPRESENTATIVE_COMMENT_MIN_THANKS,
        f"invalid representative comment threshold: {entity}",
    )
    require(
        criteria.get("excluded_representative_comment_nodes") == ["promotions"],
        f"invalid representative comment node exclusions: {entity}",
    )
    require(
        criteria.get("excluded_representative_comment_users") == ["usdc"],
        f"invalid representative comment user exclusions: {entity}",
    )
    require(
        criteria.get("representative_comments_per_year") == 10,
        f"invalid annual representative comment limit: {entity}",
    )
    require(
        criteria.get("representative_comments_per_month") == 3
        and criteria.get("representative_comments_per_active_month") == 5
        and criteria.get("representative_comments_per_very_active_month") == 10,
        f"invalid monthly representative comment limits: {entity}",
    )
    require(
        criteria.get("representative_comment_active_month_minimum_topics") == 20
        and criteria.get("representative_comment_very_active_month_minimum_topics") == 100,
        f"invalid monthly representative comment thresholds: {entity}",
    )
    require(
        criteria.get("representative_comment_period_basis") == "topic_create_at",
        f"invalid representative comment period basis: {entity}",
    )
    require(
        criteria.get("representative_comment_bucket_count") == 2048,
        f"invalid representative comment bucket count: {entity}",
    )


def validate_period_representative_comments(
    payload: dict,
    entity: str,
    monthly_counts: dict[str, int],
    default_end_period: str,
    preview_end_period: str,
):
    rankings = payload.get("comment_rankings", {}).get(entity)
    comment_payloads = payload.get("comment_payloads")
    require(isinstance(rankings, dict), f"period comment rankings missing: {entity}")
    require(isinstance(comment_payloads, dict), f"period comment payloads missing: {entity}")
    valid_years = {period[:4] for period in monthly_counts}
    for period, ranking in rankings.items():
        is_month = PERIOD_RE.match(period) is not None
        is_year = re.match(r"^\d{4}$", period) is not None
        require(is_month or is_year, f"invalid representative comment period: {entity} {period}")
        require(
            period in (monthly_counts if is_month else valid_years),
            f"representative comment period has no related posts: {entity} {period}",
        )
        require(
            period <= (preview_end_period if is_month else default_end_period[:4]),
            f"future representative comment period: {entity} {period}",
        )
        if is_month:
            topic_count = monthly_counts[period]
            limit = 10 if topic_count >= 100 else 5 if topic_count >= 20 else 3
        else:
            limit = 10
        ids = ranking.get("ids")
        require(isinstance(ids, list) and 0 < len(ids) <= limit, f"invalid period comment count: {entity} {period}")
        require(len(set(ids)) == len(ids), f"duplicate period comment: {entity} {period}")
        comments = [comment_payloads.get(str(comment_id)) for comment_id in ids]
        require(all(isinstance(comment, dict) for comment in comments), f"period comment payload missing: {entity} {period}")
        require(
            all(
                comment.get("id") == comment_id
                and isinstance(comment.get("topic_id"), int)
                and isinstance(comment.get("no"), int)
                and isinstance(comment.get("create_at"), int)
                and PERIOD_RE.match(comment.get("topic_period", "")) is not None
                and (comment["topic_period"] == period if is_month else comment["topic_period"].startswith(period))
                and comment.get("thank_count", 0)
                >= REPRESENTATIVE_COMMENT_MIN_THANKS
                and comment.get("commenter", "").casefold() != "usdc"
                and has_comment_content(comment)
                for comment_id, comment in zip(ids, comments)
            ),
            f"invalid period representative comment: {entity} {period}",
        )
        require(
            comments == sorted(
                comments,
                key=lambda comment: (comment["thank_count"], comment["id"]),
                reverse=True,
            ),
            f"period representative comments are not ranked: {entity} {period}",
        )
        require(
            isinstance(ranking.get("thanked_comments"), int)
            and ranking["thanked_comments"] >= len(ids),
            f"invalid period thanked comment summary: {entity} {period}",
        )
        require(
            isinstance(ranking.get("comment_thanks"), int)
            and ranking["comment_thanks"]
            >= sum(comment["thank_count"] for comment in comments),
            f"invalid period comment thank summary: {entity} {period}",
        )


def validate():
    manifest = load("dynamic-manifest.json")
    require(manifest["schema_version"] == 38, "unsupported analytics schema version")
    require("full_build_source" in manifest, "manifest has no full-build source fingerprint")

    overview = load("dynamic-overview.json")
    periods = overview["periods"]
    require(periods and all(PERIOD_RE.match(row["period"]) for row in periods), "invalid overview periods")
    metadata = overview["metadata"]
    require(metadata["default_end_period"] <= metadata["end_period"], "default period exceeds data range")
    require(
        str(metadata.get("topic_data_through", ""))[:7] == metadata["end_period"],
        "topic data cutoff does not match the latest period",
    )
    if metadata.get("incomplete_periods"):
        require(metadata["default_end_period"] < metadata["end_period"], "incomplete period was not excluded by default")
        require(
            metadata["incomplete_periods"]
            == [row["period"] for row in periods if row["period"] > metadata["default_end_period"]],
            "incomplete period metadata is inconsistent",
        )
    overview_activity_index = load("dynamic-overview-activity.json")
    require(
        "rows" not in overview_activity_index,
        "overview activity index still contains the complete payload",
    )
    overview_activity = []
    for year, name in overview_activity_index.get("row_shards", {}).items():
        require(
            name == f"dynamic-overview-activity-rows-{year}.json",
            f"invalid overview activity shard: {year}",
        )
        rows = load(name).get("rows", [])
        require(
            rows and all(len(row) == 5 and row[0].startswith(f"{year}-") for row in rows),
            f"invalid overview activity rows: {year}",
        )
        overview_activity.extend(rows)
    require(
        overview_activity and all(len(row) == 5 and PERIOD_RE.match(row[0]) for row in overview_activity),
        "invalid overview activity rows",
    )

    distribution = load("dynamic-scale-distribution.json")
    distribution_metadata = distribution.get("metadata", {})
    require(distribution_metadata.get("scope") == "complete_history", "invalid scale distribution scope")
    require(distribution_metadata.get("start_period") == metadata["start_period"], "scale distribution start is stale")
    require(distribution_metadata.get("end_period") == metadata["default_end_period"], "scale distribution end is stale")
    require(
        metadata.get("participant_count") == distribution_metadata.get("counts", {}).get("participants"),
        "overview participant count does not match scale distribution",
    )
    require(
        set(distribution.get("post_metrics", {})) == {"favorites", "thanks", "clicks"},
        "invalid post distribution metrics",
    )
    require(
        set(distribution.get("entity_metrics", {})) == {"topics", "nodes"},
        "invalid entity distribution metrics",
    )
    require(
        set(distribution.get("member_metrics", {})) == {"topics", "comments", "thanks"},
        "invalid member distribution metrics",
    )
    distribution_metrics = [
        *distribution["post_metrics"].values(),
        distribution["comment_thanks"],
        *distribution["entity_metrics"].values(),
        *distribution["member_metrics"].values(),
    ]
    for metric in distribution_metrics:
        rows = metric.get("rows", [])
        require(rows and all(row["threshold"] > 0 and row["count"] >= 0 for row in rows), f"invalid distribution rows: {metric.get('id')}")
        require(
            all(rows[index]["threshold"] > rows[index + 1]["threshold"] for index in range(len(rows) - 1)),
            f"distribution thresholds are not descending: {metric.get('id')}",
        )
        require(
            all(rows[index]["count"] <= rows[index + 1]["count"] for index in range(len(rows) - 1)),
            f"distribution counts are not cumulative: {metric.get('id')}",
        )
    require("vote" not in json.dumps(distribution), "vote distribution should not be exported")

    topics = load("dynamic-topics.json")
    require(len(topics["tags"]) <= 500, "topic tag limit exceeded")
    topic_names = {item["tag"] for item in topics["tags"]}
    require(
        len({name.casefold() for name in topic_names}) == len(topic_names),
        "case-duplicate topic tag",
    )
    compact_topic_names = defaultdict(set)
    for name in topic_names:
        compact = re.sub(
            r"[\s._-]+", "", unicodedata.normalize("NFKC", name).casefold()
        )
        compact_topic_names[compact].add(name)
    near_duplicate_topics = [
        sorted(names) for names in compact_topic_names.values() if len(names) > 1
    ]
    require(
        not near_duplicate_topics,
        f"near-duplicate topic tags: {near_duplicate_topics}",
    )
    topic_group_names = {item["name"] for item in topics["groups"]}
    topic_group_topics = {item["name"]: set(item.get("topics", [])) for item in topics["groups"]}
    require(len(topic_group_names) == 10, "invalid topic group count")
    require(
        all(
            item.get("label")
            and item.get("description")
            and item.get("topics")
            and item.get("nodes")
            and "terms" not in item
            for item in topics["groups"]
        ),
        "topic group metadata is incomplete",
    )
    require(
        set(topics.get("group_metadata", {}).get("excluded_nodes", []))
        == {"promotions", "cosub", "free", "deals", "tuan"},
        "invalid topic group node exclusions",
    )
    require(
        topics.get("group_metadata", {}).get("classification_basis")
        == ["original_topics", "nodes"],
        "invalid topic group classification basis",
    )
    require(
        topics.get("group_metadata", {}).get("item_display_rule")
        == {"minimum_count": 3, "minimum_share": 0.01, "absolute_count": 100},
        "invalid topic group topic threshold",
    )
    require(
        topics.get("group_metadata", {}).get("topic_coverage_row_schema")
        == ["period", "group_name", "matched_topic_count"],
        "invalid topic group coverage schema",
    )
    group_totals = {(row[0], row[1]): row[2] for row in topics.get("group_rows", [])}
    group_topic_match_rows = topics.get("group_topic_match_rows", [])
    require(
        all(
            len(row) == 3
            and PERIOD_RE.match(row[0])
            and row[1] in topic_group_names
            and 0 < row[2] <= group_totals.get((row[0], row[1]), 0)
            for row in group_topic_match_rows
        ),
        "invalid topic group coverage rows",
    )
    require(
        {row[1] for row in group_topic_match_rows} == topic_group_names,
        "topic group coverage rows missing",
    )
    linked_node_names = set()
    require({"投资", "理财", "股票", "基金"} <= topic_names, "focused topic tag missing")
    topic_rows = []
    topic_group_topic_rows = []
    topic_stage_hotspots = {
        **topics.get("stage_hotspots", {}),
        "month": [],
        "year": [],
    }
    for year, name in topics["row_shards"].items():
        require(name == f"dynamic-topic-rows-{year}.json", f"invalid topic row shard: {year}")
        payload = load(name)
        rows = payload["rows"]
        if topics.get("evolution_shards"):
            evolution_name = topics["evolution_shards"].get(year)
            require(evolution_name == f"dynamic-topic-evolution-{year}.json", f"invalid topic evolution shard: {year}")
            evolution = load(evolution_name)
            require(evolution.get("rows") == [row[:4] for row in rows], f"topic evolution counts differ: {year}")
            require(evolution.get("stage_hotspots") == payload.get("stage_hotspots"), f"topic stage hotspots differ: {year}")
            group_name = topics.get("group_shards", {}).get(year)
            require(group_name == f"dynamic-topic-groups-{year}.json", f"invalid topic group shard: {year}")
            require(load(group_name).get("group_topic_rows") == payload.get("group_topic_rows", []), f"topic group counts differ: {year}")
        require(all(len(row) == 5 and row[0].startswith(f"{year}-") for row in rows), f"invalid topic trend row: {year}")
        topic_rows.extend(rows)
        require("group_term_rows" not in payload, f"legacy topic group terms remain: {year}")
        require("group_node_rows" not in payload, f"legacy topic group nodes remain: {year}")
        group_topic_rows = payload.get("group_topic_rows", [])
        require(
            all(
                len(row) == 4
                and row[0].startswith(f"{year}-")
                and row[1] in topic_group_names
                and row[2] in topic_group_topics[row[1]]
                and row[3] > 0
                for row in group_topic_rows
            ),
            f"invalid topic group topic row: {year}",
        )
        topic_group_topic_rows.extend(group_topic_rows)
        topic_stage_hotspots["month"].extend(
            payload.get("stage_hotspots", {}).get("month", [])
        )
        topic_stage_hotspots["year"].extend(
            payload.get("stage_hotspots", {}).get("year", [])
        )
    require(topic_rows, "topic trend rows missing")
    require({row[1] for row in topic_group_topic_rows} == topic_group_names, "topic group topic rows missing")
    validate_stage_hotspots(
        topic_stage_hotspots,
        "topics",
        topic_names,
        metadata["start_period"],
        metadata["end_period"],
    )

    node_index = load("dynamic-nodes.json")
    require("rows" not in node_index, "node index still contains the complete trend payload")
    node_rows = []
    for year, name in node_index.get("row_shards", {}).items():
        require(name == f"dynamic-node-rows-{year}.json", f"invalid node row shard: {year}")
        rows = load(name).get("rows", [])
        require(
            rows and all(len(row) == 5 and row[0].startswith(f"{year}-") for row in rows),
            f"invalid node trend row: {year}",
        )
        node_rows.extend(rows)
    require(node_rows, "node trend rows missing")

    search_suggestions = load("dynamic-search-suggestions.json")
    suggestion_metadata = search_suggestions.get("metadata", {})
    require(suggestion_metadata.get("to_period") == metadata["default_end_period"], "search suggestions are stale")
    require(suggestion_metadata.get("months") == 12, "invalid search suggestion window")
    require(suggestion_metadata.get("limit_per_type") == 5, "invalid search suggestion limit")
    topic_suggestions = search_suggestions.get("topics", [])
    content_suggestions = search_suggestions.get("content", [])
    require(len(topic_suggestions) == 5 and len(content_suggestions) == 5, "search suggestions are incomplete")
    suggestion_names = [item.get("value", "").casefold() for item in [*topic_suggestions, *content_suggestions]]
    require(len(suggestion_names) == len(set(suggestion_names)), "search suggestions overlap")
    require(
        all(item.get("value") in topic_names and item.get("count", 0) > 0 for item in topic_suggestions),
        "invalid topic search suggestion",
    )

    content_index = load("dynamic-content-hotspots-index.json")
    require(content_index["metadata"]["default_end_period"] == metadata["default_end_period"], "content hotspot period is stale")
    require(content_index["metadata"].get("preview_end_period") == metadata["end_period"], "content hotspot preview period is stale")
    require(metadata["end_period"] in content_index.get("period_totals", {}), "latest content hotspot period is missing")
    require(content_index["metadata"]["ranking_limit"] == 30, "invalid content hotspot ranking limit")
    require(content_index["metadata"]["representative_posts_per_year"] == 10, "invalid content representative post limit")
    require(content_index["metadata"]["representative_posts_per_month"] == 3, "invalid monthly content representative post limit")
    require(content_index["metadata"].get("representative_posts_per_active_month") == 5, "invalid active-month content representative post limit")
    require(content_index["metadata"].get("active_month_minimum_topics") == 20, "invalid active-month content threshold")
    require(content_index["metadata"].get("representative_posts_per_very_active_month") == 10, "invalid very-active-month content representative post limit")
    require(content_index["metadata"].get("very_active_month_minimum_topics") == 100, "invalid very-active-month content threshold")
    require(
        content_index["metadata"].get("detail_entity_criteria") == {
            "global": {"titles": 20, "authors": 15, "nodes": 3},
            "low_volume_global": {"titles": 10, "authors": 8, "nodes": 3},
        },
        "invalid confirmed content detail criteria",
    )
    require(content_index["terms"], "content hotspot terms missing")
    reviewed_entities = {
        "OpenWrt", "WireGuard", "Tailscale", "Steam", "Notion", "飞书", "抖音",
        "小红书", "Bilibili", "Jellyfin", "Telegram", "YouTube", "Facebook",
        "Microsoft", "React Native", "A股", "标普", "纳指", "纳斯达克",
        "基金", "定投", "Electron", "eSIM", "Home Assistant", "Lovable",
        "Giffgaff", "量化", "充值", "续费", "退款", "封号", "风控", "中转",
        "梯子", "钱包", "性价比", "英语", "地图", "书籍", "架构", "日志",
        "编辑器", "IDE", "CLI", "原生", "云原生", "协作", "国产", "界面",
    }
    require(reviewed_entities <= set(content_index["terms"]), "reviewed content entity missing")
    require(
        all(item.get("total", 0) >= 10 for item in content_index["terms"].values()),
        "content detail index contains a term below the hard minimum",
    )
    require(
        all(content_index["terms"][term].get("confirmed") for term in reviewed_entities),
        "reviewed content entity is not confirmed",
    )
    require(
        all(item.get("value") in content_index["terms"] and item.get("count", 0) > 0 for item in content_suggestions),
        "invalid content search suggestion",
    )
    require(
        len({term.casefold() for term in content_index["terms"]}) == len(content_index["terms"]),
        "case-duplicate content hotspot term",
    )
    require(
        {
            "GPT", "GPT-4", "GPT-5", "GPT-5.6 Sol", "AI Agent", "Agent",
            "智能体", "Copilot", "Prompt", "提示词",
        } <= set(content_index["terms"])
        and "GitHub Copilot" not in content_index["terms"],
        "content term families or aliases are incomplete",
    )
    expected_content_families = {
        "GPT": ["GPT-4", "GPT-5", "GPT-5.6 Sol"],
        "Agent": ["AI Agent", "智能体"],
        "Prompt": ["提示词"],
    }
    content_families = {
        item.get("term"): item.get("members", [])
        for item in content_index.get("content_families", [])
    }
    require(content_families == expected_content_families, "invalid content family definitions")
    family_members = {
        member for members in expected_content_families.values() for member in members
    }
    require(
        set(content_index["metadata"].get("ranking_excluded_terms", [])) == family_members,
        "content family members are not excluded from primary rankings",
    )
    require(
        all(
            content_index["terms"][member].get("family") == family
            and not content_index["terms"][member].get("ranked")
            for family, members in expected_content_families.items()
            for member in members
        ),
        "content family member metadata is invalid",
    )
    require(
        all(
            content_index["terms"][family].get("family_members") == members
            for family, members in expected_content_families.items()
        ),
        "content family aggregate metadata is invalid",
    )
    content_groups = content_index.get("content_groups", [])
    content_group_ids = {group["id"] for group in content_groups}
    require(len(content_groups) == 10, "invalid content group count")
    require(len(content_group_ids) == len(content_groups), "duplicate content group id")
    require(
        all(
            group.get("label")
            and group.get("color")
            and group.get("description")
            and len(group.get("terms", [])) >= 8
            for group in content_groups
        ),
        "invalid content group definition",
    )
    content_group_terms = {
        group["id"]: set(group["terms"])
        for group in content_groups
    }
    require(
        not family_members & content_group_terms.get("ai-models", set()),
        "content family members must not duplicate aggregate group items",
    )
    content_group_metadata = content_index.get("content_group_metadata", {})
    require(
        content_group_metadata.get("row_schema") == ["period", "group_id", "topic_count"],
        "invalid content group row schema",
    )
    require(
        content_group_metadata.get("term_row_schema") == ["period", "group_id", "term", "topic_count"],
        "invalid content group term schema",
    )
    require(
        content_group_metadata.get("item_display_rule")
        == {"minimum_count": 3, "minimum_share": 0.01, "absolute_count": 100},
        "invalid content group term threshold",
    )
    content_rows = []
    content_group_rows = []
    content_group_term_rows = []
    content_stage_hotspots = {
        **content_index.get("stage_hotspots", {}),
        "month": [],
        "year": [],
    }
    for year, name in content_index["year_shards"].items():
        require(name == f"dynamic-content-hotspots-{year}.json", f"invalid content hotspot shard: {year}")
        payload = load(name)
        rows = payload["rows"]
        annual_rows = payload.get("annual_rows", [])
        if content_index.get("evolution_shards"):
            evolution_name = content_index["evolution_shards"].get(year)
            require(evolution_name == f"dynamic-content-evolution-{year}.json", f"invalid content evolution shard: {year}")
            evolution = load(evolution_name)
            expected_counts = [row[:3] for row in rows if content_index["terms"].get(row[1], {}).get("ranked") is not False]
            require(evolution.get("counts") == expected_counts, f"content evolution counts differ: {year}")
            require(evolution.get("rows") == [row for row in rows if 0 < row[9] <= 30], f"monthly content ranks differ: {year}")
            require(evolution.get("annual_rows") == [row for row in annual_rows if 0 < row[9] <= 30], f"annual content ranks differ: {year}")
            require(evolution.get("stage_hotspots") == payload.get("stage_hotspots"), f"content stage hotspots differ: {year}")
            group_name = content_index.get("group_shards", {}).get(year)
            require(group_name == f"dynamic-content-groups-{year}.json", f"invalid content group shard: {year}")
            groups = load(group_name)
            require(all(groups.get(key) == payload.get(key, []) for key in ("group_rows", "group_term_rows")), f"content group counts differ: {year}")
        require(all(len(row) == 12 and row[0].startswith(f"{year}-") for row in rows), f"invalid content hotspot row: {year}")
        require(all(len(row) == 12 and row[0] == year for row in annual_rows), f"invalid annual content hotspot row: {year}")
        require(annual_rows, f"annual content hotspot rows missing: {year}")
        group_rows = payload.get("group_rows", [])
        group_term_rows = payload.get("group_term_rows", [])
        require(
            all(len(row) == 3 and row[0].startswith(f"{year}-") and row[1] in content_group_ids and row[2] > 0 for row in group_rows),
            f"invalid content group row: {year}",
        )
        require(
            all(
                len(row) == 4
                and row[0].startswith(f"{year}-")
                and row[1] in content_group_ids
                and row[2] in content_group_terms[row[1]]
                and row[3] > 0
                for row in group_term_rows
            ),
            f"invalid content group term row: {year}",
        )
        content_rows.extend(rows)
        content_group_rows.extend(group_rows)
        content_group_term_rows.extend(group_term_rows)
        content_stage_hotspots["month"].extend(
            payload.get("stage_hotspots", {}).get("month", [])
        )
        content_stage_hotspots["year"].extend(
            payload.get("stage_hotspots", {}).get("year", [])
        )
    require(content_rows, "content hotspot rows missing")
    require({row[1] for row in content_group_rows} == content_group_ids, "content group rows missing")
    require({row[1] for row in content_group_term_rows} == content_group_ids, "content group term rows missing")
    require({row[1] for row in content_rows} == set(content_index["terms"]), "content hotspot term index mismatch")
    validate_stage_hotspots(
        content_stage_hotspots,
        "content",
        {
            term
            for term, item in content_index["terms"].items()
            if item.get("ranked")
        },
        metadata["start_period"],
        metadata["end_period"],
    )
    with (ROOT / "analysis" / "content_stopwords.txt").open(encoding="utf-8") as fp:
        content_stopwords = {
            line.strip().casefold()
            for line in fp
            if line.strip() and not line.lstrip().startswith("#")
        }
    leaked_stopwords = {
        term for term in content_index["terms"] if term.casefold() in content_stopwords
    }
    require(not leaked_stopwords, f"content stopword leaked into hotspot terms: {sorted(leaked_stopwords)}")
    content_detail_shards = {}
    content_period_post_shards = {}
    content_period_comment_shards = {}
    content_details = {}
    validate_comment_criteria(content_index["metadata"], "content")
    for term, entry in content_index["terms"].items():
        require(isinstance(entry.get("ranked"), bool), f"content rank flag missing: {term}")
        require(isinstance(entry.get("confirmed"), bool), f"content confirmation flag missing: {term}")
        require(entry["ranked"] or entry["confirmed"], f"unqualified content detail term: {term}")
        bucket = entry["bucket"]
        if bucket not in content_detail_shards:
            content_detail_shards[bucket] = load(f"dynamic-content-term-details-{bucket}.json")
        detail = content_detail_shards[bucket]["details"].get(term)
        require(detail is not None and detail["term"] == term, f"content term detail missing: {term}")
        validate_no_legacy_representative_comments(detail, f"content:{term}")
        content_details[term] = detail
        rows = detail["rows"]
        require(entry["total"] == detail["total"], f"content index total mismatch: {term}")
        require(detail["total"] == sum(row[2] for row in rows), f"content monthly total mismatch: {term}")
        require(
            rows
            and entry["first_period"] == rows[0][0]
            and entry["last_period"] == rows[-1][0],
            f"content period bounds mismatch: {term}",
        )
        require(
            [row[0] for row in rows] == sorted({row[0] for row in rows}),
            f"duplicate or unsorted content periods: {term}",
        )
        require(detail.get("author_total", 0) > 0, f"content term author coverage missing: {term}")
        require(detail.get("node_total", 0) > 0, f"content term node coverage missing: {term}")
        require(all(row[1] == term and len(row) == 12 for row in detail["rows"]), f"invalid content term trend: {term}")
        require(
            all(len(row) == 12 and len(row[0]) == 4 and row[1] == term for row in detail.get("annual_rows", [])),
            f"invalid annual content term trend: {term}",
        )
        require(detail.get("authors"), f"content term authors missing: {term}")
        related_terms = detail.get("related_terms", [])
        require(len(related_terms) <= 20, f"too many related content terms: {term}")
        require(all(item[0] != term and item[0] in content_index["terms"] and item[1] > 0 for item in related_terms), f"invalid related content term: {term}")
        require(
            related_terms == sorted(related_terms, key=lambda item: (-item[1], item[0].casefold(), item[0])),
            f"related content terms are not ranked: {term}",
        )
        related_topics = detail.get("topics", [])
        require(len(related_topics) <= 20, f"too many related topics: {term}")
        require(
            all(item[0] in topic_names and item[1] > 0 for item in related_topics),
            f"invalid related topic: {term}",
        )
        require(
            related_topics == sorted(related_topics, key=lambda item: (-item[1], item[0].casefold(), item[0])),
            f"related topics are not ranked: {term}",
        )
        linked_node_names.update(item[0] for item in detail.get("nodes", []))
        linked_node_names.update(post["node"] for post in detail.get("posts", []) if post.get("node"))
        require(
            all(set(post.get("tags", [])) <= topic_names for post in detail.get("posts", [])),
            f"content post exposes a topic without detail: {term}",
        )
        require(
            not any(
                post["node"].casefold() == "promotions"
                for post in detail["posts"]
            ),
            f"promotion post leaked into content detail: {term}",
        )
        require(
            all(
                count <= content_index["metadata"]["representative_posts_per_year"]
                for count in Counter(
                    post_year(post) for post in detail["posts"]
                ).values()
            ),
            f"too many annual content representative posts: {term}",
        )
        period_post_bucket = entry.get("period_post_bucket")
        require(isinstance(period_post_bucket, str), f"content period post bucket missing: {term}")
        if period_post_bucket not in content_period_post_shards:
            content_period_post_shards[period_post_bucket] = load(
                f"dynamic-content-period-posts-{period_post_bucket}.json"
            )
        require(
            "comment_rankings" not in content_period_post_shards[period_post_bucket]
            and "comment_payloads" not in content_period_post_shards[period_post_bucket],
            f"content comments leaked into post shard: {term}",
        )
        period_comment_bucket = entry.get("period_comment_bucket")
        require(isinstance(period_comment_bucket, str), f"content period comment bucket missing: {term}")
        if period_comment_bucket not in content_period_comment_shards:
            content_period_comment_shards[period_comment_bucket] = load(
                f"dynamic-content-period-comments-{period_comment_bucket}.json"
            )
        period_posts = content_period_post_shards[period_post_bucket].get("posts", {}).get(term)
        require(isinstance(period_posts, dict) and period_posts, f"content monthly posts missing: {term}")
        detail_period_counts = {row[0]: row[2] for row in detail["rows"] if row[2] > 0}
        validate_period_representative_comments(
            content_period_comment_shards[period_comment_bucket],
            term,
            detail_period_counts,
            metadata["default_end_period"],
            metadata["end_period"],
        )
        detail_periods = set(detail_period_counts)
        require(set(period_posts) <= detail_periods, f"content monthly post period mismatch: {term}")
        for period, posts in period_posts.items():
            require(
                PERIOD_RE.match(period) is not None and period <= metadata["end_period"],
                f"invalid content post period: {term} {period}",
            )
            monthly_limit = (
                10
                if detail_period_counts[period] >= 100
                else 5 if detail_period_counts[period] >= 20 else 3
            )
            require(0 < len(posts) <= monthly_limit, f"too many monthly content representative posts: {term} {period}")
            require(len({post["id"] for post in posts}) == len(posts), f"duplicate monthly content post: {term} {period}")
            require(
                all(post.get("period") == period for post in posts),
                f"monthly content post timestamp mismatch: {term} {period}",
            )
            require(
                posts == sorted(posts, key=lambda post: (post["score"], post["id"]), reverse=True),
                f"monthly content posts are not ranked: {term} {period}",
            )
            require(
                all(post.get("node", "").casefold() != "promotions" for post in posts),
                f"promotion post leaked into monthly content detail: {term}",
            )
            require(
                all(set(post.get("tags", [])) <= topic_names for post in posts),
                f"monthly content post exposes a topic without detail: {term}",
            )
            linked_node_names.update(post["node"] for post in posts if post.get("node"))
    for family, members in expected_content_families.items():
        family_detail = content_details[family]
        family_counts = {row[0]: row[2] for row in family_detail["rows"]}
        for member in members:
            member_detail = content_details[member]
            require(
                family_detail["total"] >= member_detail["total"],
                f"content family total is below member total: {family} < {member}",
            )
            require(
                all(family_counts.get(row[0], 0) >= row[2] for row in member_detail["rows"]),
                f"content family period is below member count: {family} < {member}",
            )
    require(len(list(PUBLIC_DIR.glob("dynamic-content-term-details-*.json"))) == 64, "invalid content detail shard count")
    require(len(list(PUBLIC_DIR.glob("dynamic-content-period-posts-*.json"))) == 256, "invalid content period post shard count")
    require(
        len(list(PUBLIC_DIR.glob("dynamic-content-period-comments-*.json")))
        == len(content_period_comment_shards),
        "invalid content period comment shard count",
    )
    content_audit = (ROOT / "analysis" / "content_hotspot_audit.md").read_text(encoding="utf-8")
    require(
        f"数据截至 {metadata['default_end_period']}" in content_audit,
        "content hotspot audit is stale",
    )

    community = load("dynamic-community.json")
    require(all(len(row) == 6 for row in community["rank_rows"]), "invalid member ranking row")
    require(
        all(row[2] in {"topics", "comments"} and 1 <= row[3] <= 10 for row in community["rank_rows"]),
        "invalid member evolution ranking",
    )
    require(
        community.get("rank_criteria") == {
            "evolution_limit": 10,
            "metrics": ["topics", "comments"],
        },
        "invalid member ranking criteria",
    )
    require(
        all(len(community.get(key, [])) <= 10 for key in ("top_topic_authors", "top_commenters", "top_thanked")),
        "member cumulative ranking exceeds Top 10",
    )
    require(
        community.get("concentration_criteria") == {
            "limits": [10, 50, 100],
            "metrics": ["topics", "comments"],
        },
        "invalid member concentration criteria",
    )
    concentration_rows = community.get("concentration_rows", [])
    require(concentration_rows, "missing member concentration rows")
    require(all(len(row) == 10 for row in concentration_rows), "invalid member concentration row")
    for row in concentration_rows:
        grain, period, topic_total, topic_top10, topic_top50, topic_top100, comment_total, comment_top10, comment_top50, comment_top100 = row
        require(grain in {"month", "year"}, f"invalid member concentration grain: {grain}")
        require(
            (grain == "month" and PERIOD_RE.match(period))
            or (grain == "year" and re.fullmatch(r"\d{4}", period)),
            f"invalid member concentration period: {grain} {period}",
        )
        require(
            0 <= topic_top10 <= topic_top50 <= topic_top100 <= topic_total,
            f"invalid topic concentration totals: {grain} {period}",
        )
        require(
            0 <= comment_top10 <= comment_top50 <= comment_top100 <= comment_total,
            f"invalid comment concentration totals: {grain} {period}",
        )
    monthly_concentration = {row[1]: row for row in concentration_rows if row[0] == "month"}
    for period in overview["periods"]:
        row = monthly_concentration.get(period["period"])
        require(row is not None, f"missing monthly member concentration: {period['period']}")
        require(row[2] == period["topic_count"], f"topic concentration denominator mismatch: {period['period']}")
        require(row[6] == period["comment_count"], f"comment concentration denominator mismatch: {period['period']}")

    member_index = load("dynamic-member-profile-index.json")
    require(0 < len(member_index["members"]) <= 2500, "invalid member profile candidate count")
    require(member_index["criteria"].get("direction_period") == "year", "invalid member direction period")
    require(
        member_index["criteria"].get("representative_comment_minimum_thanks")
        == REPRESENTATIVE_COMMENT_MIN_THANKS,
        "invalid member representative comment threshold",
    )
    require(
        "representative_comments_require_thank" not in member_index["criteria"],
        "legacy member representative comment threshold remains",
    )
    member_direction_limit = member_index["criteria"].get("direction_limit")
    require(member_direction_limit == 10, "invalid member direction limit")
    require(member_index["criteria"].get("includes_default_range_top_10") is True, "invalid member profile coverage")
    require(
        member_index["criteria"].get("comment_direction_basis") == "distinct_topics",
        "invalid member comment direction basis",
    )
    default_profile_members = {
        row[4] for row in community["rank_rows"]
        if row[0] == "month"
        and member_index["criteria"]["default_start_period"] <= row[1] <= member_index["criteria"]["default_end_period"]
        and row[4].casefold() != "usdc"
    }
    require(default_profile_members <= set(member_index["members"]), "default-range ranked member missing from profiles")
    profile_shards = {}
    comment_shards = {}
    for username, entry in member_index["members"].items():
        bucket = entry["bucket"]
        if bucket not in profile_shards:
            profile_shards[bucket] = load(f"dynamic-member-profiles-{bucket}.json")
        comment_bucket = entry["comment_bucket"]
        if comment_bucket not in comment_shards:
            comment_shards[comment_bucket] = load(f"dynamic-member-comments-{comment_bucket}.json")
        profile = profile_shards[bucket]["profiles"].get(username)
        require(profile is not None and profile["username"] == username, f"member profile missing: {username}")
        require(all(len(row) == 5 and PERIOD_RE.match(row[0]) for row in profile["periods"]), f"invalid member periods: {username}")
        require(len(profile["posts"]) <= 20, f"too many member representative posts: {username}")
        linked_node_names.update(node for node, _ in profile.get("topic_nodes", []))
        linked_node_names.update(node for node, _ in profile.get("comment_nodes", []))
        require(
            all(tag in topic_names and count > 0 for tag, count in profile.get("tags", [])),
            f"invalid member topic: {username}",
        )
        require(len(profile.get("content_terms", [])) <= 20, f"too many member content terms: {username}")
        require(
            all(term in content_index["terms"] and count > 0 for term, count in profile.get("content_terms", [])),
            f"invalid member content term: {username}",
        )
        for row in profile.get("direction_years", []):
            require(
                len(row) == 6
                and re.match(r"^\d{4}$", row[0])
                and row[1] in {"topics", "comments"}
                and row[2] > 0,
                f"invalid member direction row: {username}",
            )
            nodes, tags, terms = row[3:]
            require(
                all(isinstance(items, list) and len(items) <= member_direction_limit for items in (nodes, tags, terms)),
                f"too many member direction items: {username} {row[0]}",
            )
            require(
                all(count > 0 for items in (nodes, tags, terms) for _, count in items),
                f"invalid member direction count: {username} {row[0]}",
            )
            require(
                all(tag in topic_names for tag, _ in tags),
                f"invalid member direction topic: {username} {row[0]}",
            )
            require(
                all(term in content_index["terms"] for term, _ in terms),
                f"invalid member direction content term: {username} {row[0]}",
            )
            linked_node_names.update(node for node, _ in nodes)
        comments = comment_shards[comment_bucket]["comments"].get(username, [])
        require(len(comments) <= 20, f"too many member representative comments: {username}")
        require(
            all(
                comment["thank_count"] >= REPRESENTATIVE_COMMENT_MIN_THANKS
                for comment in comments
            ),
            f"low-thank member comment: {username}",
        )
        require(all(has_comment_content(comment) and comment.get("create_at") for comment in comments), f"invalid member comment: {username}")
        require(username.casefold() != "usdc" or not comments, "excluded member comments were exported")
    leaders = {
        member["username"]
        for key in ("top_topic_authors", "top_commenters", "top_thanked")
        for member in community[key]
        if member["username"].casefold() != "usdc"
    }
    require(leaders <= set(member_index["members"]), "overall leader missing from member profiles")

    observations = load("dynamic-observations.json")
    require(observations["metadata"]["analysis_end"] == metadata["default_end_period"], "observation period is stale")
    require(len(observations["observations"]) >= 10, "too few offline observations")
    observation_ids = [item["id"] for item in observations["observations"]]
    require(len(observation_ids) == len(set(observation_ids)), "duplicate observation id")
    require(
        {"content-rebalance", "subscription-collaboration", "interaction-value-split", "comment-language"}
        <= set(observation_ids),
        "content-focused observation missing",
    )
    require(all(item.get("stats") and item.get("links") for item in observations["observations"]), "observation evidence missing")
    presentation = observations.get("presentation", {})
    presentation_scope = presentation.get("scope", {})
    require(
        presentation_scope.get("start_period") == metadata["start_period"]
        and presentation_scope.get("end_period") == metadata["default_end_period"]
        and presentation_scope.get("participants") == metadata["participant_count"]
        and presentation_scope.get("topics") == sum(
            row["topic_count"]
            for row in periods
            if row["period"] <= metadata["default_end_period"]
        )
        and presentation_scope.get("comments") == sum(
            row["comment_count"]
            for row in periods
            if row["period"] <= metadata["default_end_period"]
        ),
        "presentation scope is stale",
    )
    require(
        len(presentation.get("nodes", [])) == 10
        and all(item.get("topics", 0) > 0 and item.get("share", 0) > 0 for item in presentation["nodes"]),
        "presentation nodes are incomplete",
    )
    presentation_charts = presentation.get("charts", {})
    slides = presentation.get("slides", [])
    slide_ids = [slide["id"] for slide in slides]
    require(len(slides) == 20 and len(set(slide_ids)) == 20, "presentation must have 20 distinct pages")
    require(slides[0]["type"] == "cover" and slides[-1]["type"] == "explore", "presentation opening or exploration page missing")
    require(len(presentation_charts) >= 10, "presentation chart data is incomplete")
    for chart_id, chart in presentation_charts.items():
        categories = chart.get("categories", [])
        series = chart.get("series", [])
        require(chart.get("kind") in {"line", "small_multiples", "hourly_bars", "grouped_bar", "horizontal_bar"}, f"unsupported presentation chart: {chart_id}")
        require(bool(categories) and bool(series), f"empty presentation chart: {chart_id}")
        require(all(len(item["values"]) == len(categories) for item in series), f"presentation series length mismatch: {chart_id}")
        require(all(isinstance(value, (int, float)) and value >= 0 for item in series for value in item["values"]), f"invalid presentation chart value: {chart_id}")
        require(set(chart.get("partial", [])) <= set(categories), f"invalid partial presentation periods: {chart_id}")
    for slide in slides:
        require(all(slide.get(key) for key in ("id", "type", "chapter", "title", "summary")), f"incomplete presentation page: {slide['id']}")
        if slide["type"] == "chart":
            require(slide.get("chart") in presentation_charts, f"missing presentation chart: {slide['id']}")
        for takeaway in [*slide.get("takeaways", []), *slide.get("panels", [])]:
            if takeaway.get("chart"):
                require(takeaway["chart"] in presentation_charts, "missing presentation summary chart")
        require(len(slide.get("posts", [])) <= 3, f"too many presentation cases: {slide['id']}")
        for post in slide.get("posts", []):
            require(bool(post.get("title")) and post.get("url") == f"https://www.v2ex.com/t/{post['id']}", "invalid presentation post")
            require(all(post.get(key) is None or post[key] >= 0 for key in ("clicks", "favorites", "thanks", "replies")), "invalid presentation interaction snapshot")
        for comment in slide.get("comments", []):
            require(bool(comment.get("text")) and (comment.get("thanks") is None or comment["thanks"] >= 0), "invalid presentation comment")
            require(comment.get("url") == f"https://www.v2ex.com/t/{comment['topic_id']}#r_{comment['id']}", "invalid presentation comment link")
    require(
        presentation.get("topic_shifts", {}).get("ai_change", 0) > 0
        and presentation.get("topic_shifts", {}).get("engineering_change", 0) < 0
        and presentation.get("topic_shifts", {}).get("apple_share", 0) > 0,
        "presentation topic shifts are incomplete",
    )
    require(
        presentation.get("interaction", {}).get("ranking_size") == 20
        and presentation.get("rhythm", {}).get("within_1h_share", 0) > 0,
        "presentation evidence is incomplete",
    )
    ai_observation = next((item for item in observations["observations"] if item["id"] == "ai-waves"), None)
    require(
        ai_observation
        and any("view=content-detail" in link.get("href", "") for link in ai_observation["links"]),
        "AI observation is missing title-content evidence",
    )
    invitation = next((item for item in observations["observations"] if item["id"] == "invitation-system"), None)
    require(invitation and invitation.get("source", {}).get("url") == "https://www.v2ex.com/t/1037849", "invitation source missing")
    require(
        month_index(observations["metadata"]["analysis_end"])
        - month_index(observations["metadata"]["analysis_start"])
        == 119,
        "observation window is not 120 months",
    )
    require("community_signals" not in observations, "retired community signals remain in observations")
    require(
        not list(PUBLIC_DIR.glob("dynamic-community-signal-posts-*.json")),
        "retired community signal post shards remain",
    )

    events = load("dynamic-events.json")["events"]
    require(events and all(PERIOD_RE.match(item["period"]) for item in events), "invalid community events")
    require(all(item.get("title") and item.get("url") for item in events), "community event evidence missing")

    lifecycle = load("dynamic-lifecycle.json")
    structure_rows = lifecycle.get("discussion_structure_rows", [])
    require(structure_rows and all(len(row) == 6 for row in structure_rows), "discussion structure rows missing")
    require(
        all(0 <= row[4] <= row[1] and 0 <= row[5] <= row[2] for row in structure_rows),
        "invalid discussion structure ratio inputs",
    )
    engagement = load("dynamic-engagement.json")
    require(all(len(posts) == 200 for posts in engagement["top_posts"].values()), "hot post ranking does not contain Top 200")
    require(all(post.get("create_at") for posts in engagement["top_posts"].values() for post in posts), "ranked post timestamp missing")
    require(all(comment.get("create_at") for comment in engagement["top_comments"]), "ranked comment timestamp missing")
    require(all(has_comment_content(comment) for comment in engagement["top_comments"]), "ranked comment content missing")
    require(len(engagement["top_comments"]) == 500, "hot comment ranking does not contain Top 500")

    require(not (PUBLIC_DIR / "dynamic-representative-posts.json").exists(), "legacy representative post payload still exists")

    monthly_index = load("dynamic-monthly-rankings-index.json")
    require(monthly_index["limit"] == 100, "invalid monthly ranking limit")
    require(monthly_index["post_metrics"] == ["score", "favorite_count", "thank_count", "clicks"], "invalid monthly post metrics")
    require(
        monthly_index.get("post_metric_minimums") == PERIOD_POST_METRIC_MINIMUMS,
        "invalid monthly post metric minimums",
    )
    monthly_periods = set()
    for period, name in monthly_index["periods"].items():
        require(PERIOD_RE.match(period), f"invalid monthly ranking period: {period}")
        require(name == f"dynamic-monthly-ranking-{period}.json", f"invalid monthly shard name: {period}")
        shard = load(name)
        require(shard["period"] == period, f"monthly shard period mismatch: {period}")
        payload = shard["ranking"]
        monthly_periods.add(period)
        summary = payload["summary"]
        require(len(summary["tags"]) <= 20, f"too many monthly tags: {period}")
        require(len(summary["content"]) <= 20, f"too many monthly content terms: {period}")
        require(len(summary["nodes"]) <= 20, f"too many monthly nodes: {period}")
        require(all(item["name"] in topic_names for item in summary["tags"]), f"monthly topic has no detail: {period}")
        require(all(item["name"] in content_index["terms"] for item in summary["content"]), f"monthly content has no detail: {period}")
        linked_node_names.update(item["name"] for item in summary["nodes"])
        require("members" not in summary, f"legacy monthly member ranking remains: {period}")
        require(
            all(len(summary["activity"][metric]) == 3 for metric in ("authors", "commenters")),
            f"invalid monthly activity summary: {period}",
        )
        posts_by_id = {post["id"]: post for post in payload["posts"]}
        post_ids = set(posts_by_id)
        require(not any(post["node"].casefold() == "promotions" for post in payload["posts"]), f"promotion post leaked into {period}")
        for metric in monthly_index["post_metrics"]:
            ranking = payload["post_rankings"][metric]
            require(len(ranking) <= 100 and len(ranking) == len(set(ranking)), f"invalid {metric} ranking: {period}")
            require(metric == "thank_count" or ranking, f"empty {metric} ranking: {period}")
            require(set(ranking) <= post_ids, f"monthly post payload missing ranked id: {period}")
            if metric == "thank_count":
                require(
                    all(
                        posts_by_id[post_id]["thank_count"] >= 5
                        for post_id in ranking
                    ),
                    f"low-thank monthly post: {period}",
                )
        comments = payload["comments"]
        require(len(comments) <= 100, f"too many monthly comments: {period}")
        require(not any(comment["commenter"].casefold() == "usdc" for comment in comments), f"excluded commenter leaked into {period}")
        require(
            all(
                comment.get("create_at")
                and has_comment_content(comment)
                and comment.get("thank_count", 0)
                >= REPRESENTATIVE_COMMENT_MIN_THANKS
                for comment in comments
            ),
            f"invalid monthly comment: {period}",
        )
    expected_monthly_periods = {row["period"] for row in periods if row["period"] <= metadata["end_period"]}
    require(expected_monthly_periods == monthly_periods, "monthly ranking period mismatch")

    annual_index = load("dynamic-annual-rankings-index.json")
    require(annual_index["limit"] == 100, "invalid annual ranking limit")
    require(annual_index["post_metrics"] == monthly_index["post_metrics"], "annual post metrics differ from monthly")
    require(
        annual_index.get("post_metric_minimums") == monthly_index["post_metric_minimums"],
        "annual post metric minimums differ from monthly",
    )
    require(metadata["default_end_period"][:4] in annual_index["years"], "current annual profile missing")
    for year, name in annual_index["years"].items():
        require(name == f"dynamic-annual-ranking-{year}.json", f"invalid annual shard name: {year}")
        shard = load(name)
        require(shard["year"] == year, f"annual shard year mismatch: {year}")
        payload = shard["ranking"]
        require(len(payload["summary"]["tags"]) <= 20, f"too many annual tags: {year}")
        require(len(payload["summary"]["content"]) <= 20, f"too many annual content terms: {year}")
        require(len(payload["summary"]["nodes"]) <= 20, f"too many annual nodes: {year}")
        require(all(item["name"] in topic_names for item in payload["summary"]["tags"]), f"annual topic has no detail: {year}")
        require(all(item["name"] in content_index["terms"] for item in payload["summary"]["content"]), f"annual content has no detail: {year}")
        linked_node_names.update(item["name"] for item in payload["summary"]["nodes"])
        require("members" not in payload["summary"], f"legacy annual member ranking remains: {year}")
        require(not any(post["node"].casefold() == "promotions" for post in payload["posts"]), f"promotion post leaked into annual {year}")
        require(
            all(
                datetime.fromtimestamp(post["create_at"], LOCAL_TIMEZONE).strftime("%Y-%m")
                <= metadata["default_end_period"]
                for post in payload["posts"]
            ),
            f"incomplete-period post leaked into annual {year}",
        )
        require(
            all(
                datetime.fromtimestamp(comment["create_at"], LOCAL_TIMEZONE).strftime("%Y-%m")
                <= metadata["default_end_period"]
                for comment in payload["comments"]
            ),
            f"incomplete-period comment leaked into annual {year}",
        )
        annual_posts_by_id = {post["id"]: post for post in payload["posts"]}
        annual_post_ids = set(annual_posts_by_id)
        for metric in annual_index["post_metrics"]:
            ranking = payload["post_rankings"][metric]
            require(len(ranking) <= 100 and len(ranking) == len(set(ranking)), f"invalid annual {metric} ranking: {year}")
            require(metric == "thank_count" or ranking, f"empty annual {metric} ranking: {year}")
            require(set(ranking) <= annual_post_ids, f"annual post payload missing ranked id: {year}")
            if metric == "thank_count":
                require(
                    all(
                        annual_posts_by_id[post_id]["thank_count"] >= 5
                        for post_id in ranking
                    ),
                    f"low-thank annual post: {year}",
                )
        require(len(payload["comments"]) <= 100, f"too many annual comments: {year}")
        require(
            all(
                comment.get("create_at")
                and has_comment_content(comment)
                and comment.get("thank_count", 0)
                >= REPRESENTATIVE_COMMENT_MIN_THANKS
                for comment in payload["comments"]
            ),
            f"invalid annual comment: {year}",
        )

    detail_index = load("dynamic-tag-detail-index.json")
    require(set(detail_index["tags"]) == {item["tag"] for item in topics["tags"]}, "tag detail index does not match topic tags")
    validate_comment_criteria(detail_index.get("criteria", {}), "topic")
    tag_post_limit = detail_index.get("criteria", {}).get("representative_posts_per_year")
    require(tag_post_limit == 10, "invalid topic representative post limit")
    tag_monthly_post_limit = detail_index.get("criteria", {}).get(
        "representative_posts_per_month"
    )
    require(tag_monthly_post_limit == 3, "invalid monthly topic post limit")
    tag_active_monthly_post_limit = detail_index.get("criteria", {}).get(
        "representative_posts_per_active_month"
    )
    require(tag_active_monthly_post_limit == 5, "invalid active-month topic post limit")
    tag_active_month_minimum = detail_index.get("criteria", {}).get(
        "active_month_minimum_topics"
    )
    require(tag_active_month_minimum == 20, "invalid active-month topic threshold")
    tag_very_active_monthly_post_limit = detail_index.get("criteria", {}).get(
        "representative_posts_per_very_active_month"
    )
    require(tag_very_active_monthly_post_limit == 10, "invalid very-active-month topic post limit")
    tag_very_active_month_minimum = detail_index.get("criteria", {}).get(
        "very_active_month_minimum_topics"
    )
    require(tag_very_active_month_minimum == 100, "invalid very-active-month topic threshold")
    require(
        detail_index["criteria"].get("excluded_representative_nodes") == ["promotions"],
        "invalid topic representative post exclusions",
    )
    shard_cache = {}
    period_post_shard_cache = {}
    period_comment_shard_cache = {}
    tag_representative_count = 0
    tag_monthly_representative_count = 0
    for tag, entry in detail_index["tags"].items():
        bucket = entry["bucket"]
        if bucket not in shard_cache:
            shard_cache[bucket] = load(f"dynamic-tag-details-{bucket}.json")
        period_post_bucket = entry.get("period_post_bucket")
        require(
            isinstance(period_post_bucket, str),
            f"monthly topic post bucket missing: {tag}",
        )
        if period_post_bucket not in period_post_shard_cache:
            period_post_shard_cache[period_post_bucket] = load(
                f"dynamic-tag-period-posts-{period_post_bucket}.json"
            )
        require(
            "comment_rankings" not in period_post_shard_cache[period_post_bucket]
            and "comment_payloads" not in period_post_shard_cache[period_post_bucket],
            f"topic comments leaked into post shard: {tag}",
        )
        period_comment_bucket = entry.get("period_comment_bucket")
        require(isinstance(period_comment_bucket, str), f"topic period comment bucket missing: {tag}")
        if period_comment_bucket not in period_comment_shard_cache:
            period_comment_shard_cache[period_comment_bucket] = load(
                f"dynamic-tag-period-comments-{period_comment_bucket}.json"
            )
        detail = shard_cache[bucket]["details"].get(tag)
        require(detail is not None and detail["tag"] == tag, f"tag detail missing: {tag}")
        validate_no_legacy_representative_comments(detail, f"topic:{tag}")
        require(
            all(len(row) == 5 and row[1] == tag and PERIOD_RE.match(row[0]) for row in detail["rows"]),
            f"invalid tag detail trend: {tag}",
        )
        tag_period_counts = {row[0]: row[2] for row in detail["rows"]}
        require(all(item[0] in topic_names for item in detail.get("related", [])), f"related topic has no detail: {tag}")
        related_content = detail.get("related_content", [])
        require(len(related_content) <= 20, f"too many related content terms: {tag}")
        require(
            all(
                len(item) == 2
                and item[0] in content_index["terms"]
                and isinstance(item[1], int)
                and item[1] > 0
                for item in related_content
            ),
            f"invalid related content terms: {tag}",
        )
        require(
            related_content == sorted(
                related_content,
                key=lambda item: (-item[1], item[0].casefold(), item[0]),
            ),
            f"related content terms are not sorted: {tag}",
        )
        linked_node_names.update(item[0] for item in detail.get("nodes", []))
        posts = detail.get("posts", [])
        tag_representative_count += len(posts)
        require(
            not any(post["node"].casefold() == "promotions" for post in posts),
            "promotion node leaked into representative posts",
        )
        require(
            all(tag in set(post.get("tags", [])) for post in posts),
            f"representative post does not match topic: {tag}",
        )
        require(
            all(set(post.get("tags", [])) <= topic_names for post in posts),
            "representative post exposes a topic without detail",
        )
        require(
            all(
                count <= tag_post_limit
                for count in Counter(post_year(post) for post in posts).values()
            ),
            f"too many annual topic representative posts: {tag}",
        )
        linked_node_names.update(post["node"] for post in posts if post.get("node"))
        period_posts = period_post_shard_cache[period_post_bucket].get(
            "posts", {}
        ).get(tag)
        require(isinstance(period_posts, dict), f"monthly topic posts missing: {tag}")
        validate_period_representative_comments(
            period_comment_shard_cache[period_comment_bucket],
            tag,
            tag_period_counts,
            metadata["default_end_period"],
            metadata["end_period"],
        )
        for period, monthly_posts in period_posts.items():
            require(
                PERIOD_RE.match(period) and period <= metadata["end_period"],
                f"invalid monthly topic post period: {tag} {period}",
            )
            if tag_period_counts[period] >= tag_very_active_month_minimum:
                monthly_limit = tag_very_active_monthly_post_limit
            elif tag_period_counts[period] >= tag_active_month_minimum:
                monthly_limit = tag_active_monthly_post_limit
            else:
                monthly_limit = tag_monthly_post_limit
            require(0 < len(monthly_posts) <= monthly_limit, f"too many monthly topic posts: {tag} {period}")
            require(
                len({post["id"] for post in monthly_posts}) == len(monthly_posts),
                f"duplicate monthly topic post: {tag} {period}",
            )
            require(
                all(post.get("period") == period for post in monthly_posts),
                f"monthly topic post period mismatch: {tag} {period}",
            )
            require(
                all(tag in set(post.get("tags", [])) for post in monthly_posts),
                f"monthly representative post does not match topic: {tag}",
            )
            require(
                all(set(post.get("tags", [])) <= topic_names for post in monthly_posts),
                f"monthly topic post exposes unknown topic: {tag}",
            )
            require(
                not any(
                    post["node"].casefold() == "promotions"
                    for post in monthly_posts
                ),
                f"promotion post leaked into monthly topic posts: {tag}",
            )
            require(
                monthly_posts == sorted(
                    monthly_posts,
                    key=lambda post: (
                        post["score"],
                        post["create_at"],
                        post["id"],
                    ),
                    reverse=True,
                ),
                f"monthly topic posts are not sorted: {tag} {period}",
            )
            tag_monthly_representative_count += len(monthly_posts)
            linked_node_names.update(
                post["node"] for post in monthly_posts if post.get("node")
            )
    require(tag_representative_count > 0, "tag representative posts missing")
    require(
        tag_monthly_representative_count > tag_representative_count,
        "monthly topic representative posts are incomplete",
    )
    require(len(list(PUBLIC_DIR.glob("dynamic-tag-details-*.json"))) == 64, "invalid tag detail shard count")
    require(
        len(list(PUBLIC_DIR.glob("dynamic-tag-period-posts-*.json"))) == 256,
        "invalid monthly topic post shard count",
    )
    require(
        len(list(PUBLIC_DIR.glob("dynamic-tag-period-comments-*.json")))
        == len(period_comment_shard_cache),
        "invalid topic period comment shard count",
    )

    node_detail_index = load("dynamic-node-detail-index.json")
    node_criteria = node_detail_index["criteria"]
    validate_comment_criteria(node_criteria, "node")
    require(node_criteria["minimum_topics"] == 50, "invalid node detail threshold")
    require(node_criteria["included_node_count"] == len(node_detail_index["nodes"]), "invalid included node count")
    require(node_criteria["observed_node_count"] >= len(node_detail_index["nodes"]), "invalid observed node count")
    require(
        node_criteria["included_share"]
        == round(len(node_detail_index["nodes"]) / node_criteria["observed_node_count"], 4),
        "invalid included node share",
    )
    require(
        all(entry.get("total", 0) >= node_criteria["minimum_topics"] for entry in node_detail_index["nodes"].values()),
        "low-volume node leaked into detail index",
    )
    node_metadata = load("dynamic-node-metadata.json")
    require(node_metadata["minimum_topics"] == node_criteria["minimum_topics"], "node metadata threshold mismatch")
    require(set(node_metadata["analyzed_nodes"]) == set(node_detail_index["nodes"]), "node metadata index mismatch")
    require(
        set(node_detail_index["nodes"]) <= set(node_metadata.get("labels", {})),
        "analyzed node display name missing",
    )
    require(node_detail_index["criteria"]["representative_post_limit"] == 100, "invalid node post limit")
    node_yearly_post_limit = node_detail_index["criteria"]["representative_posts_per_year"]
    node_monthly_post_limit = node_detail_index["criteria"]["representative_posts_per_month"]
    node_active_monthly_post_limit = node_detail_index["criteria"]["representative_posts_per_active_month"]
    node_active_month_minimum = node_detail_index["criteria"]["active_month_minimum_topics"]
    node_very_active_monthly_post_limit = node_detail_index["criteria"]["representative_posts_per_very_active_month"]
    node_very_active_month_minimum = node_detail_index["criteria"]["very_active_month_minimum_topics"]
    node_detail_shards = {}
    node_period_post_shards = {}
    node_period_comment_shards = {}
    node_period_representative_count = 0
    node_representative_count = 0
    for node, entry in node_detail_index["nodes"].items():
        bucket = entry["bucket"]
        if bucket not in node_detail_shards:
            node_detail_shards[bucket] = load(f"dynamic-node-details-{bucket}.json")
        detail = node_detail_shards[bucket]["details"].get(node)
        require(detail is not None and detail["node"] == node, f"node detail missing: {node}")
        validate_no_legacy_representative_comments(detail, f"node:{node}")
        require(all(len(row) == 5 and row[1] == node and PERIOD_RE.match(row[0]) for row in detail["rows"]), f"invalid node trend: {node}")
        content_terms = detail.get("content_terms")
        require(isinstance(content_terms, list), f"node content terms missing: {node}")
        require(
            len(detail["tags"]) <= 20
            and len(content_terms) <= 20
            and len(detail["authors"]) <= 20,
            f"node detail list too long: {node}",
        )
        require(
            all(
                len(item) == 2
                and item[0] in content_index["terms"]
                and isinstance(item[1], int)
                and item[1] > 0
                for item in content_terms
            ),
            f"invalid node content terms: {node}",
        )
        require(
            content_terms == sorted(
                content_terms,
                key=lambda item: (-item[1], item[0].casefold(), item[0]),
            ),
            f"node content terms are not sorted: {node}",
        )
        require(len(detail["posts"]) <= 100, f"too many node representative posts: {node}")
        require(all(set(post.get("tags", [])) <= topic_names for post in detail["posts"]), f"node post exposes a topic without detail: {node}")
        require(not any(post["node"].casefold() == "promotions" for post in detail["posts"]), f"promotion post leaked into node detail: {node}")
        node_representative_count += len(detail["posts"])
        period_post_bucket = entry.get("period_post_bucket")
        require(period_post_bucket is not None, f"node period post bucket missing: {node}")
        if period_post_bucket not in node_period_post_shards:
            node_period_post_shards[period_post_bucket] = load(
                f"dynamic-node-period-posts-{period_post_bucket}.json"
            )
        require(
            "comment_rankings" not in node_period_post_shards[period_post_bucket]
            and "comment_payloads" not in node_period_post_shards[period_post_bucket],
            f"node comments leaked into post shard: {node}",
        )
        period_comment_bucket = entry.get("period_comment_bucket")
        require(isinstance(period_comment_bucket, str), f"node period comment bucket missing: {node}")
        if period_comment_bucket not in node_period_comment_shards:
            node_period_comment_shards[period_comment_bucket] = load(
                f"dynamic-node-period-comments-{period_comment_bucket}.json"
            )
        period_posts = node_period_post_shards[period_post_bucket].get("posts", {}).get(node)
        require(isinstance(period_posts, dict), f"node period posts missing: {node}")
        monthly_counts = {row[0]: int(row[2]) for row in detail["rows"]}
        validate_period_representative_comments(
            node_period_comment_shards[period_comment_bucket],
            node,
            monthly_counts,
            metadata["default_end_period"],
            metadata["end_period"],
        )
        for period, posts in period_posts.items():
            is_month = bool(PERIOD_RE.match(period))
            is_year = bool(re.match(r"^\d{4}$", period))
            require(is_month or is_year, f"invalid node representative period: {node} {period}")
            require(
                period <= (metadata["end_period"] if is_month else metadata["default_end_period"][:4]),
                f"future node representative period: {node} {period}",
            )
            if is_month:
                topic_count = monthly_counts.get(period, 0)
                if topic_count >= node_very_active_month_minimum:
                    limit = node_very_active_monthly_post_limit
                elif topic_count >= node_active_month_minimum:
                    limit = node_active_monthly_post_limit
                else:
                    limit = node_monthly_post_limit
            else:
                limit = node_yearly_post_limit
            require(0 < len(posts) <= limit, f"too many node period posts: {node} {period}")
            require(len({post["id"] for post in posts}) == len(posts), f"duplicate node period post: {node} {period}")
            require(
                all(post.get("node") == node for post in posts),
                f"node period post belongs to another node: {node} {period}",
            )
            require(
                all(
                    post.get("period") == period
                    if is_month
                    else str(post.get("period", "")).startswith(period)
                    for post in posts
                ),
                f"node representative post period mismatch: {node} {period}",
            )
            require(
                all(set(post.get("tags", [])) <= topic_names for post in posts),
                f"node period post exposes unknown topic: {node} {period}",
            )
            require(
                not any(post["node"].casefold() == "promotions" for post in posts),
                f"promotion post leaked into node period posts: {node} {period}",
            )
            require(
                posts == sorted(
                    posts,
                    key=lambda post: (post["score"], post["create_at"], post["id"]),
                    reverse=True,
                ),
                f"node period posts are not sorted: {node} {period}",
            )
            node_period_representative_count += len(posts)
    require(node_period_representative_count > node_representative_count, "node period representative posts are incomplete")
    require(len(list(PUBLIC_DIR.glob("dynamic-node-details-*.json"))) == 64, "invalid node detail shard count")
    require(len(list(PUBLIC_DIR.glob("dynamic-node-period-posts-*.json"))) == 256, "invalid node period post shard count")
    require(
        len(list(PUBLIC_DIR.glob("dynamic-node-period-comments-*.json")))
        == len(node_period_comment_shards),
        "invalid node period comment shard count",
    )
    require(len(list(PUBLIC_DIR.glob("dynamic-member-profiles-*.json"))) == 64, "invalid member profile shard count")

    require(
        metadata.get("analysis_coverage") == {
            "topics": len(detail_index["tags"]),
            "content_terms": len(content_index["terms"]),
            "nodes": len(node_detail_index["nodes"]),
            "members": len(member_index["members"]),
        },
        "about analysis coverage is stale",
    )

    for name, size in manifest["files"].items():
        path = PUBLIC_DIR / name
        require(path.exists() and path.stat().st_size == size, f"manifest file mismatch: {name}")
    require(not (PUBLIC_DIR / "dynamic-title-tokens.json").exists(), "unused title-token output still exists")
    print(
        f"Validated analytics schema v{manifest['schema_version']}: {len(manifest['files'])} files, "
        f"{len(detail_index['tags'])} tag details, {len(node_detail_index['nodes'])} node details, "
        f"{len(content_index['terms'])} content terms"
    )


if __name__ == "__main__":
    validate()
