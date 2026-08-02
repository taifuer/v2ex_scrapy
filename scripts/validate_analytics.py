#!/usr/bin/env python3
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = ROOT / "analysis" / "v2ex-analysis" / "public"
PERIOD_RE = re.compile(r"^\d{4}-\d{2}$")


def load(name: str):
    with (PUBLIC_DIR / name).open(encoding="utf-8") as fp:
        return json.load(fp)


def require(condition: bool, message: str):
    if not condition:
        raise ValueError(message)


def month_index(period: str) -> int:
    year, month = map(int, period.split("-"))
    return year * 12 + month - 1


def validate():
    manifest = load("dynamic-manifest.json")
    require(manifest["schema_version"] == 14, "unsupported analytics schema version")
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

    topics = load("dynamic-topics.json")
    require(len(topics["tags"]) <= 500, "topic tag limit exceeded")
    topic_names = {item["tag"] for item in topics["tags"]}
    require({"投资", "理财", "股票", "基金"} <= topic_names, "focused topic tag missing")
    topic_rows = []
    for year, name in topics["row_shards"].items():
        require(name == f"dynamic-topic-rows-{year}.json", f"invalid topic row shard: {year}")
        rows = load(name)["rows"]
        require(all(len(row) == 5 and row[0].startswith(f"{year}-") for row in rows), f"invalid topic trend row: {year}")
        topic_rows.extend(rows)
    require(topic_rows, "topic trend rows missing")

    content_index = load("dynamic-content-hotspots-index.json")
    require(content_index["metadata"]["default_end_period"] == metadata["default_end_period"], "content hotspot period is stale")
    require(content_index["metadata"]["ranking_limit"] == 30, "invalid content hotspot ranking limit")
    require(content_index["metadata"]["representative_posts_per_year"] == 10, "invalid content representative post limit")
    require(content_index["terms"], "content hotspot terms missing")
    require(
        len({term.casefold() for term in content_index["terms"]}) == len(content_index["terms"]),
        "case-duplicate content hotspot term",
    )
    content_rows = []
    for year, name in content_index["year_shards"].items():
        require(name == f"dynamic-content-hotspots-{year}.json", f"invalid content hotspot shard: {year}")
        payload = load(name)
        rows = payload["rows"]
        annual_rows = payload.get("annual_rows", [])
        require(all(len(row) == 12 and row[0].startswith(f"{year}-") for row in rows), f"invalid content hotspot row: {year}")
        require(all(len(row) == 12 and row[0] == year for row in annual_rows), f"invalid annual content hotspot row: {year}")
        require(annual_rows, f"annual content hotspot rows missing: {year}")
        content_rows.extend(rows)
    require(content_rows, "content hotspot rows missing")
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
    for term, entry in content_index["terms"].items():
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
        require(not any(post["node"].casefold() == "promotions" for post in detail["posts"]), f"promotion post leaked into content detail: {term}")
    require(len(list(PUBLIC_DIR.glob("dynamic-content-term-details-*.json"))) == 64, "invalid content detail shard count")
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
        require("members" not in payload["summary"], f"legacy annual member ranking remains: {year}")
        require(not any(post["node"].casefold() == "promotions" for post in payload["posts"]), f"promotion post leaked into annual {year}")
        require(len(payload["comments"]) <= 100, f"too many annual comments: {year}")

    detail_index = load("dynamic-tag-detail-index.json")
    require(set(detail_index["tags"]) == {item["tag"] for item in topics["tags"]}, "tag detail index does not match topic tags")
    shard_cache = {}
    for tag, entry in detail_index["tags"].items():
        bucket = entry["bucket"]
        if bucket not in shard_cache:
            shard_cache[bucket] = load(f"dynamic-tag-details-{bucket}.json")
        detail = shard_cache[bucket]["details"].get(tag)
        require(detail is not None and detail["tag"] == tag, f"tag detail missing: {tag}")
        require(
            all(len(row) == 5 and row[1] == tag and PERIOD_RE.match(row[0]) for row in detail["rows"]),
            f"invalid tag detail trend: {tag}",
        )
    tag_representative_count = 0
    for payload in shard_cache.values():
        posts = payload.get("representative_posts", [])
        tag_representative_count += len(posts)
        require(not any(post["node"].casefold() == "promotions" for post in posts), "promotion node leaked into representative posts")
        bucket_tags = set(payload["details"])
        require(
            all(bucket_tags & set(post.get("tags", [])) for post in posts),
            "representative post does not match its tag shard",
        )
    require(tag_representative_count > 0, "tag representative posts missing")
    require(len(list(PUBLIC_DIR.glob("dynamic-tag-details-*.json"))) == 64, "invalid tag detail shard count")

    node_detail_index = load("dynamic-node-detail-index.json")
    require(node_detail_index["criteria"]["minimum_topics"] == 20, "invalid node detail threshold")
    require(node_detail_index["criteria"]["representative_post_limit"] == 100, "invalid node post limit")
    node_detail_shards = {}
    for node, entry in node_detail_index["nodes"].items():
        bucket = entry["bucket"]
        if bucket not in node_detail_shards:
            node_detail_shards[bucket] = load(f"dynamic-node-details-{bucket}.json")
        detail = node_detail_shards[bucket]["details"].get(node)
        require(detail is not None and detail["node"] == node, f"node detail missing: {node}")
        require(all(len(row) == 5 and row[1] == node and PERIOD_RE.match(row[0]) for row in detail["rows"]), f"invalid node trend: {node}")
        require(len(detail["tags"]) <= 20 and len(detail["authors"]) <= 20, f"node detail list too long: {node}")
        require(len(detail["posts"]) <= 100, f"too many node representative posts: {node}")
        require(not any(post["node"].casefold() == "promotions" for post in detail["posts"]), f"promotion post leaked into node detail: {node}")
    require(len(list(PUBLIC_DIR.glob("dynamic-node-details-*.json"))) == 64, "invalid node detail shard count")
    require(len(list(PUBLIC_DIR.glob("dynamic-member-profiles-*.json"))) == 64, "invalid member profile shard count")

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
