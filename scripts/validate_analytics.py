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
    require(manifest["schema_version"] == 5, "unsupported analytics schema version")
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
    require(all(len(row) == 5 for row in topics["rows"]), "invalid topic trend row")

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
    for username, entry in member_index["members"].items():
        bucket = entry["bucket"]
        if bucket not in profile_shards:
            profile_shards[bucket] = load(f"dynamic-member-profiles-{bucket}.json")
        profile = profile_shards[bucket]["profiles"].get(username)
        require(profile is not None and profile["username"] == username, f"member profile missing: {username}")
        require(all(len(row) == 5 and PERIOD_RE.match(row[0]) for row in profile["periods"]), f"invalid member periods: {username}")
        require(len(profile["posts"]) <= 8, f"too many member representative posts: {username}")
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

    engagement = load("dynamic-engagement.json")
    require(all(len(posts) == 200 for posts in engagement["top_posts"].values()), "hot post ranking does not contain Top 200")
    require(all(post.get("create_at") for posts in engagement["top_posts"].values() for post in posts), "ranked post timestamp missing")
    require(all(comment.get("create_at") for comment in engagement["top_comments"]), "ranked comment timestamp missing")
    require(len(engagement["top_comments"]) == 500, "hot comment ranking does not contain Top 500")

    representative = load("dynamic-representative-posts.json")["representative_posts"]
    require(not any(post["node"].casefold() == "promotions" for post in representative), "promotion node leaked into representative posts")

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
