from __future__ import annotations

import heapq
import math
from collections import defaultdict


MONTHLY_RANKING_LIMIT = 100
TAG_REPRESENTATIVE_POSTS_PER_YEAR = 10
TAG_REPRESENTATIVE_POSTS_PER_MONTH = 3
TAG_REPRESENTATIVE_POSTS_PER_ACTIVE_MONTH = 5
TAG_REPRESENTATIVE_ACTIVE_MONTH_MIN_TOPICS = 20
TAG_REPRESENTATIVE_POSTS_PER_VERY_ACTIVE_MONTH = 10
TAG_REPRESENTATIVE_VERY_ACTIVE_MONTH_MIN_TOPICS = 100
NODE_REPRESENTATIVE_POSTS_PER_YEAR = 10
NODE_REPRESENTATIVE_POSTS_PER_MONTH = 3
NODE_REPRESENTATIVE_POSTS_PER_ACTIVE_MONTH = 5
NODE_REPRESENTATIVE_ACTIVE_MONTH_MIN_TOPICS = 20
NODE_REPRESENTATIVE_POSTS_PER_VERY_ACTIVE_MONTH = 10
NODE_REPRESENTATIVE_VERY_ACTIVE_MONTH_MIN_TOPICS = 100
ENTITY_REPRESENTATIVE_COMMENTS_PER_YEAR = 10
ENTITY_REPRESENTATIVE_COMMENTS_PER_MONTH = 3
ENTITY_REPRESENTATIVE_COMMENTS_PER_ACTIVE_MONTH = 5
ENTITY_REPRESENTATIVE_COMMENT_ACTIVE_MONTH_MIN_TOPICS = 20
ENTITY_REPRESENTATIVE_COMMENTS_PER_VERY_ACTIVE_MONTH = 10
ENTITY_REPRESENTATIVE_COMMENT_VERY_ACTIVE_MONTH_MIN_TOPICS = 100


def engagement_score(row) -> float:
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


def entity_monthly_representative_comment_limit(topic_count: int) -> int:
    if topic_count >= ENTITY_REPRESENTATIVE_COMMENT_VERY_ACTIVE_MONTH_MIN_TOPICS:
        return ENTITY_REPRESENTATIVE_COMMENTS_PER_VERY_ACTIVE_MONTH
    if topic_count >= ENTITY_REPRESENTATIVE_COMMENT_ACTIVE_MONTH_MIN_TOPICS:
        return ENTITY_REPRESENTATIVE_COMMENTS_PER_ACTIVE_MONTH
    return ENTITY_REPRESENTATIVE_COMMENTS_PER_MONTH


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


def percent_change(current: float, previous: float) -> float:
    return ((current - previous) / previous * 100) if previous else 0.0
