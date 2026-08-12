#!/usr/bin/env python3
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = ROOT / "analysis" / "v2ex-analysis" / "public"
PERIOD_RE = re.compile(r"^\d{4}-\d{2}$")
LOCAL_TIMEZONE = timezone(timedelta(hours=8))


def load(name: str):
    with (PUBLIC_DIR / name).open(encoding="utf-8") as fp:
        return json.load(fp)


def require(condition: bool, message: str):
    if not condition:
        raise ValueError(message)


def month_index(period: str) -> int:
    year, month = map(int, period.split("-"))
    return year * 12 + month - 1


def post_year(post: dict) -> str:
    if post.get("period"):
        return str(post["period"])[:4]
    return datetime.fromtimestamp(post["create_at"], LOCAL_TIMEZONE).strftime("%Y")


def validate():
    manifest = load("dynamic-manifest.json")
    require(manifest["schema_version"] == 29, "unsupported analytics schema version")
    require("full_build_source" in manifest, "manifest has no full-build source fingerprint")

    overview = load("dynamic-overview.json")
    periods = overview["periods"]
    require(periods and all(PERIOD_RE.match(row["period"]) for row in periods), "invalid overview periods")
    metadata = overview["metadata"]
    require(metadata["default_end_period"] <= metadata["end_period"], "default period exceeds data range")
    if metadata.get("incomplete_periods"):
        require(metadata["default_end_period"] < metadata["end_period"], "incomplete period was not excluded by default")
    overview_activity = load("dynamic-overview-activity.json")["rows"]
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
    for year, name in topics["row_shards"].items():
        require(name == f"dynamic-topic-rows-{year}.json", f"invalid topic row shard: {year}")
        payload = load(name)
        rows = payload["rows"]
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
    require(topic_rows, "topic trend rows missing")
    require({row[1] for row in topic_group_topic_rows} == topic_group_names, "topic group topic rows missing")

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
    require(content_index["metadata"]["ranking_limit"] == 30, "invalid content hotspot ranking limit")
    require(content_index["metadata"]["representative_posts_per_year"] == 10, "invalid content representative post limit")
    require(content_index["metadata"]["representative_posts_per_month"] == 3, "invalid monthly content representative post limit")
    require(content_index["metadata"].get("representative_posts_per_active_month") == 5, "invalid active-month content representative post limit")
    require(content_index["metadata"].get("active_month_minimum_topics") == 20, "invalid active-month content threshold")
    require(content_index["metadata"].get("representative_posts_per_very_active_month") == 10, "invalid very-active-month content representative post limit")
    require(content_index["metadata"].get("very_active_month_minimum_topics") == 100, "invalid very-active-month content threshold")
    require(
        content_index["metadata"].get("detail_entity_criteria") == {
            "monthly": {"titles": 8, "authors": 5, "nodes": 2},
            "annual": {"titles": 30, "authors": 15, "nodes": 2},
        },
        "invalid confirmed content detail criteria",
    )
    require(content_index["terms"], "content hotspot terms missing")
    reviewed_entities = {
        "OpenWrt", "WireGuard", "Tailscale", "Steam", "Notion", "飞书", "抖音",
        "小红书", "Bilibili", "Jellyfin", "Telegram", "YouTube", "Facebook",
        "Microsoft", "React Native",
    }
    require(reviewed_entities <= set(content_index["terms"]), "reviewed content entity missing")
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
        "AI Agent": ["Agent", "智能体"],
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
    for year, name in content_index["year_shards"].items():
        require(name == f"dynamic-content-hotspots-{year}.json", f"invalid content hotspot shard: {year}")
        payload = load(name)
        rows = payload["rows"]
        annual_rows = payload.get("annual_rows", [])
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
    require(content_rows, "content hotspot rows missing")
    require({row[1] for row in content_group_rows} == content_group_ids, "content group rows missing")
    require({row[1] for row in content_group_term_rows} == content_group_ids, "content group term rows missing")
    require({row[1] for row in content_rows} == set(content_index["terms"]), "content hotspot term index mismatch")
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
    for term, entry in content_index["terms"].items():
        require(isinstance(entry.get("ranked"), bool), f"content rank flag missing: {term}")
        require(isinstance(entry.get("confirmed"), bool), f"content confirmation flag missing: {term}")
        require(entry["ranked"] or entry["confirmed"], f"unqualified content detail term: {term}")
        bucket = entry["bucket"]
        if bucket not in content_detail_shards:
            content_detail_shards[bucket] = load(f"dynamic-content-term-details-{bucket}.json")
        detail = content_detail_shards[bucket]["details"].get(term)
        require(detail is not None and detail["term"] == term, f"content term detail missing: {term}")
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
        period_posts = content_period_post_shards[period_post_bucket].get("posts", {}).get(term)
        require(isinstance(period_posts, dict) and period_posts, f"content monthly posts missing: {term}")
        detail_period_counts = {row[0]: row[2] for row in detail["rows"] if row[2] > 0}
        detail_periods = set(detail_period_counts)
        require(set(period_posts) <= detail_periods, f"content monthly post period mismatch: {term}")
        for period, posts in period_posts.items():
            require(PERIOD_RE.match(period) is not None, f"invalid content post period: {term} {period}")
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
    require(len(list(PUBLIC_DIR.glob("dynamic-content-term-details-*.json"))) == 64, "invalid content detail shard count")
    require(len(list(PUBLIC_DIR.glob("dynamic-content-period-posts-*.json"))) == 128, "invalid content period post shard count")
    content_audit = (ROOT / "analysis" / "content_hotspot_audit.md").read_text(encoding="utf-8")
    require(
        f"数据截至 {metadata['default_end_period']}" in content_audit,
        "content hotspot audit is stale",
    )

    community = load("dynamic-community.json")
    require(all(len(row) == 6 for row in community["rank_rows"]), "invalid member ranking row")
    require(not any(row[2] == "thanks" and row[4].casefold() == "usdc" for row in community["rank_rows"]), "excluded member leaked into thanks ranking")

    member_index = load("dynamic-member-profile-index.json")
    require(0 < len(member_index["members"]) <= 2500, "invalid member profile candidate count")
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
        comments = comment_shards[comment_bucket]["comments"].get(username, [])
        require(len(comments) <= 20, f"too many member representative comments: {username}")
        require(all(comment["thank_count"] > 0 for comment in comments), f"unthanked member comment: {username}")
        require(all("content" in comment and comment.get("create_at") for comment in comments), f"invalid member comment: {username}")
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
    require(len(engagement["top_comments"]) == 500, "hot comment ranking does not contain Top 500")

    require(not (PUBLIC_DIR / "dynamic-representative-posts.json").exists(), "legacy representative post payload still exists")

    monthly_index = load("dynamic-monthly-rankings-index.json")
    require(monthly_index["limit"] == 100, "invalid monthly ranking limit")
    require(monthly_index["post_metrics"] == ["score", "favorite_count", "thank_count", "clicks"], "invalid monthly post metrics")
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
        post_ids = {post["id"] for post in payload["posts"]}
        require(not any(post["node"].casefold() == "promotions" for post in payload["posts"]), f"promotion post leaked into {period}")
        for metric in monthly_index["post_metrics"]:
            ranking = payload["post_rankings"][metric]
            require(0 < len(ranking) <= 100 and len(ranking) == len(set(ranking)), f"invalid {metric} ranking: {period}")
            require(set(ranking) <= post_ids, f"monthly post payload missing ranked id: {period}")
        comments = payload["comments"]
        require(len(comments) <= 100, f"too many monthly comments: {period}")
        require(not any(comment["commenter"].casefold() == "usdc" for comment in comments), f"excluded commenter leaked into {period}")
        require(all(comment.get("create_at") and "content" in comment for comment in comments), f"invalid monthly comment: {period}")
    complete_periods = {row["period"] for row in periods if row["period"] <= metadata["default_end_period"]}
    require(complete_periods <= monthly_periods, "monthly ranking period missing")

    annual_index = load("dynamic-annual-rankings-index.json")
    require(annual_index["limit"] == 100, "invalid annual ranking limit")
    require(annual_index["post_metrics"] == monthly_index["post_metrics"], "annual post metrics differ from monthly")
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
        require(len(payload["comments"]) <= 100, f"too many annual comments: {year}")

    detail_index = load("dynamic-tag-detail-index.json")
    require(set(detail_index["tags"]) == {item["tag"] for item in topics["tags"]}, "tag detail index does not match topic tags")
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
        detail = shard_cache[bucket]["details"].get(tag)
        require(detail is not None and detail["tag"] == tag, f"tag detail missing: {tag}")
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
        for period, monthly_posts in period_posts.items():
            require(
                PERIOD_RE.match(period) and period <= metadata["default_end_period"],
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
        len(list(PUBLIC_DIR.glob("dynamic-tag-period-posts-*.json"))) == 128,
        "invalid monthly topic post shard count",
    )

    node_detail_index = load("dynamic-node-detail-index.json")
    node_criteria = node_detail_index["criteria"]
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
    node_period_representative_count = 0
    node_representative_count = 0
    for node, entry in node_detail_index["nodes"].items():
        bucket = entry["bucket"]
        if bucket not in node_detail_shards:
            node_detail_shards[bucket] = load(f"dynamic-node-details-{bucket}.json")
        detail = node_detail_shards[bucket]["details"].get(node)
        require(detail is not None and detail["node"] == node, f"node detail missing: {node}")
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
        period_posts = node_period_post_shards[period_post_bucket].get("posts", {}).get(node)
        require(isinstance(period_posts, dict), f"node period posts missing: {node}")
        monthly_counts = {row[0]: int(row[2]) for row in detail["rows"]}
        for period, posts in period_posts.items():
            is_month = bool(PERIOD_RE.match(period))
            is_year = bool(re.match(r"^\d{4}$", period))
            require(is_month or is_year, f"invalid node representative period: {node} {period}")
            require(
                period <= (metadata["default_end_period"] if is_month else metadata["default_end_period"][:4]),
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
