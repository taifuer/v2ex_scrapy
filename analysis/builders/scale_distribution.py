from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime

from v2ex_scrapy.change_tracking import MIN_TRACKED_CREATE_AT

from .common import LOCAL_TIMEZONE, month_for, period_end_timestamp, threshold_rows


EXCLUDED_THANK_USERS = frozenset({"usdc"})
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
    topic_params = (MIN_TRACKED_CREATE_AT, cutoff)
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
