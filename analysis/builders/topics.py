from __future__ import annotations


TOP_TAG_LIMIT = 500
FOCUSED_TAGS = frozenset({"投资", "理财", "股票", "基金"})
TOPIC_GROUP_EXCLUDED_NODES = frozenset({"promotions", "cosub", "free", "deals", "tuan"})


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
