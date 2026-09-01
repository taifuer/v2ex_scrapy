from __future__ import annotations

import sqlite3
from datetime import datetime

from v2ex_scrapy.change_tracking import MIN_TRACKED_CREATE_AT

from .common import LOCAL_TIMEZONE, previous_period


MEMBER_RANKING_LIMIT = 10
MEMBER_CONCENTRATION_LIMITS = (10, 50, 100)


def build_member_ranking_data(
    source: sqlite3.Connection,
    limit: int = MEMBER_RANKING_LIMIT,
    default_end_period: str | None = None,
) -> tuple[list[list], list[list]]:
    source.execute("PRAGMA temp_store = FILE")
    source.executescript(
        f"""
        DROP TABLE IF EXISTS temp.member_topic_period;
        DROP TABLE IF EXISTS temp.member_comment_period;
        CREATE TEMP TABLE member_topic_period AS
        SELECT strftime('%Y-%m', create_at, 'unixepoch', '+8 hours') AS period,
               author AS username,
               COUNT(*) AS topic_count
        FROM topic
        WHERE clicks >= 0 AND create_at >= {MIN_TRACKED_CREATE_AT} AND author != ''
        GROUP BY 1, 2;
        CREATE TEMP TABLE member_comment_period AS
        SELECT strftime('%Y-%m', create_at, 'unixepoch', '+8 hours') AS period,
               commenter AS username,
               COUNT(*) AS comment_count
        FROM comment
        WHERE create_at >= {MIN_TRACKED_CREATE_AT} AND commenter != ''
        GROUP BY 1, 2;
        """
    )

    rows: list[list] = []
    concentration: dict[tuple[str, str, str], list[int]] = {}
    query_limit = max(limit, *MEMBER_CONCENTRATION_LIMITS)

    def append_rankings(grain: str, metric: str, values_sql: str, parameters=()):
        ranking_sql = f"""
            WITH values_by_member AS ({values_sql}),
            ranked AS (
                SELECT period, username, value,
                       ROW_NUMBER() OVER (
                           PARTITION BY period
                           ORDER BY value DESC, username COLLATE NOCASE
                       ) AS position,
                       SUM(value) OVER (PARTITION BY period) AS total
                FROM values_by_member
                WHERE value > 0
            )
            SELECT period, position, username, value, total
            FROM ranked
            WHERE position <= ?
            ORDER BY period, position
        """
        for period, position, username, value, total in source.execute(
            ranking_sql, (*parameters, query_limit)
        ):
            position = int(position)
            value = int(value)
            if position <= limit:
                rows.append([grain, period, metric, position, username, value])
            key = (grain, period, metric)
            bucket = concentration.setdefault(key, [int(total), 0, 0, 0])
            for index, concentration_limit in enumerate(MEMBER_CONCENTRATION_LIMITS, start=1):
                if position <= concentration_limit:
                    bucket[index] += value

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

    source.executescript(
        """
        DROP TABLE temp.member_topic_period;
        DROP TABLE temp.member_comment_period;
        """
    )
    periods = sorted({(grain, period) for grain, period, _ in concentration})
    concentration_rows = []
    for grain, period in periods:
        topic_values = concentration.get((grain, period, "topics"), [0, 0, 0, 0])
        comment_values = concentration.get((grain, period, "comments"), [0, 0, 0, 0])
        concentration_rows.append([grain, period, *topic_values, *comment_values])
    return rows, concentration_rows


def build_member_rank_rows(
    source: sqlite3.Connection,
    limit: int = MEMBER_RANKING_LIMIT,
    default_end_period: str | None = None,
) -> list[list]:
    rows, _ = build_member_ranking_data(source, limit, default_end_period)
    return rows
