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


def validate():
    manifest = load("dynamic-manifest.json")
    require(manifest["schema_version"] == 6, "unsupported analytics schema version")
    require("full_build_source" in manifest, "manifest has no full-build source fingerprint")

    overview = load("dynamic-overview.json")
    periods = overview["periods"]
    require(periods and all(PERIOD_RE.match(row["period"]) for row in periods), "invalid overview periods")
    metadata = overview["metadata"]
    require(metadata["default_end_period"] <= metadata["end_period"], "default period exceeds data range")
    if metadata.get("incomplete_periods"):
        require(metadata["default_end_period"] < metadata["end_period"], "incomplete period was not excluded by default")

    topics = load("dynamic-topics.json")
    require(len(topics["tags"]) <= 500, "topic tag limit exceeded")
    require({"投资", "理财", "股票", "基金"} <= {item["tag"] for item in topics["tags"]}, "focused topic tag missing")
    topic_rows = []
    for year, name in topics["row_shards"].items():
        require(name == f"dynamic-topic-rows-{year}.json", f"invalid topic row shard: {year}")
        rows = load(name)["rows"]
        require(all(len(row) == 5 and row[0].startswith(f"{year}-") for row in rows), f"invalid topic trend row: {year}")
        topic_rows.extend(rows)
    require(topic_rows, "topic trend rows missing")

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
    require(all(item.get("stats") and item.get("links") for item in observations["observations"]), "observation evidence missing")
    invitation = next((item for item in observations["observations"] if item["id"] == "invitation-system"), None)
    require(invitation and invitation.get("source", {}).get("url") == "https://www.v2ex.com/t/1037849", "invitation source missing")
    require(observations["metadata"]["analysis_start"] == "2016-07", "observation window is not ten years")

    events = load("dynamic-events.json")["events"]
    require(events and all(PERIOD_RE.match(item["period"]) for item in events), "invalid community events")
    require(all(item.get("title") and item.get("url") for item in events), "community event evidence missing")

    engagement = load("dynamic-engagement.json")
    require(all(len(posts) == 200 for posts in engagement["top_posts"].values()), "hot post ranking does not contain Top 200")
    require(all(post.get("create_at") for posts in engagement["top_posts"].values() for post in posts), "ranked post timestamp missing")
    require(all(comment.get("create_at") for comment in engagement["top_comments"]), "ranked comment timestamp missing")
    require(len(engagement["top_comments"]) == 500, "hot comment ranking does not contain Top 500")

    representative = load("dynamic-representative-posts.json")["representative_posts"]
    require(not any(post["node"].casefold() == "promotions" for post in representative), "promotion node leaked into representative posts")

    monthly_index = load("dynamic-monthly-rankings-index.json")
    require(monthly_index["limit"] == 100, "invalid monthly ranking limit")
    require(monthly_index["post_metrics"] == ["score", "favorite_count", "thank_count", "clicks"], "invalid monthly post metrics")
    monthly_periods = set()
    for year, name in monthly_index["years"].items():
        require(name == f"dynamic-monthly-rankings-{year}.json", f"invalid monthly shard name: {year}")
        months = load(name)["months"]
        for period, payload in months.items():
            require(period.startswith(f"{year}-") and PERIOD_RE.match(period), f"invalid monthly ranking period: {period}")
            monthly_periods.add(period)
            summary = payload["summary"]
            require(len(summary["tags"]) <= 20, f"too many monthly tags: {period}")
            require(len(summary["nodes"]) <= 20, f"too many monthly nodes: {period}")
            require(len(summary["members"]) <= 20, f"too many monthly members: {period}")
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

    annual = load("dynamic-annual-rankings.json")
    require(annual["limit"] == 100, "invalid annual ranking limit")
    require(annual["post_metrics"] == monthly_index["post_metrics"], "annual post metrics differ from monthly")
    require(metadata["default_end_period"][:4] in annual["years"], "current annual profile missing")
    for year, payload in annual["years"].items():
        require(len(payload["summary"]["tags"]) <= 20, f"too many annual tags: {year}")
        require(len(payload["summary"]["nodes"]) <= 20, f"too many annual nodes: {year}")
        require(len(payload["summary"]["members"]) <= 20, f"too many annual members: {year}")
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

    for name, size in manifest["files"].items():
        path = PUBLIC_DIR / name
        require(path.exists() and path.stat().st_size == size, f"manifest file mismatch: {name}")
    require(not (PUBLIC_DIR / "dynamic-title-tokens.json").exists(), "unused title-token output still exists")
    print(f"Validated analytics schema v{manifest['schema_version']}: {len(manifest['files'])} files, {len(detail_index['tags'])} tag details")


if __name__ == "__main__":
    validate()
