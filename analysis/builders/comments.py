from __future__ import annotations

import sqlite3
from collections import defaultdict

from v2ex_scrapy.analysis_policy import REPRESENTATIVE_COMMENT_MIN_THANKS
from v2ex_scrapy.change_tracking import MIN_TRACKED_CREATE_AT

from .common import comment_text, month_for
from .rankings import push_top


EXCLUDED_THANK_USERS = frozenset({"usdc"})


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
        WHERE c.create_at >= ? AND c.thank_count >= ? AND t.clicks >= 0
          AND LOWER(c.commenter) NOT IN ({placeholders})
        """,
        (MIN_TRACKED_CREATE_AT, REPRESENTATIVE_COMMENT_MIN_THANKS, *EXCLUDED_THANK_USERS),
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


def build_annual_comment_heaps(
    source: sqlite3.Connection,
    default_end_period: str,
) -> dict[str, list]:
    heaps: dict[str, list] = defaultdict(list)
    placeholders = ",".join("?" for _ in EXCLUDED_THANK_USERS)
    for row in source.execute(
        f"""
        SELECT c.id, c.topic_id, c.commenter, c.thank_count, c.no, t.title,
               c.content, c.create_at
        FROM comment c
        JOIN topic t ON t.id = c.topic_id
        WHERE c.create_at >= ? AND c.thank_count >= ? AND t.clicks >= 0
          AND LOWER(c.commenter) NOT IN ({placeholders})
        """,
        (MIN_TRACKED_CREATE_AT, REPRESENTATIVE_COMMENT_MIN_THANKS, *EXCLUDED_THANK_USERS),
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
