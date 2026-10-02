import sqlite3
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class CommentGap:
    topic_id: int
    expected: int
    actual: int

    @property
    def gap(self) -> int:
        return self.expected - self.actual


def _comment_gaps_from_rows(rows) -> list[CommentGap]:
    return [
        CommentGap(topic_id=int(topic_id), expected=int(expected), actual=int(actual))
        for topic_id, expected, actual in rows
    ]


def find_all_comment_gaps(
    conn: sqlite3.Connection,
    end_id: int,
) -> list[CommentGap]:
    rows = conn.execute(
        """
        WITH comment_counts AS (
            SELECT topic_id, COUNT(*) AS actual
            FROM comment
            GROUP BY topic_id
        )
        SELECT topic.id,
               topic.reply_count,
               COALESCE(comment_counts.actual, 0) AS actual
        FROM topic
        LEFT JOIN comment_counts ON comment_counts.topic_id = topic.id
        WHERE topic.id <= ?
          AND topic.title != ''
          AND topic.create_at > 0
          AND topic.reply_count > COALESCE(comment_counts.actual, 0)
        ORDER BY topic.id
        """,
        (end_id,),
    ).fetchall()
    return _comment_gaps_from_rows(rows)


def filter_severe_comment_gaps(
    gaps: list[CommentGap],
    minimum_gap: int = 100,
    include_first_page_shortfall: bool = True,
) -> list[CommentGap]:
    minimum_gap = max(1, minimum_gap)
    return [
        item
        for item in gaps
        if item.gap >= minimum_gap
        or (
            include_first_page_shortfall
            and item.expected > 100
            and item.actual <= 100
        )
    ]


def find_comment_gaps(
    conn: sqlite3.Connection,
    end_id: int,
    minimum_gap: int = 100,
    include_first_page_shortfall: bool = True,
) -> list[CommentGap]:
    return filter_severe_comment_gaps(
        find_all_comment_gaps(conn, end_id),
        minimum_gap=minimum_gap,
        include_first_page_shortfall=include_first_page_shortfall,
    )


def source_quality_summary(
    conn: sqlite3.Connection,
    comment_gaps: list[CommentGap] | None = None,
) -> dict:
    topic_row = conn.execute(
        """
        SELECT COUNT(*) AS total,
               SUM(create_at > 0) AS valid_time,
               SUM(create_at <= 0) AS placeholders,
               SUM(create_at > 0 AND title = '') AS empty_title,
               SUM(create_at > 0 AND title != '' AND author = '') AS empty_author,
               SUM(create_at > 0 AND title != '' AND node = '') AS empty_node,
               SUM(create_at > 0 AND title != '' AND tag = '[]') AS no_tags,
               SUM(create_at > 0 AND title != '' AND thank_count < 0) AS unknown_thanks,
               SUM(create_at > 0 AND title != '' AND favorite_count < 0) AS unknown_favorites,
               MAX(id) AS max_id,
               MAX(create_at) AS max_create_at
        FROM topic
        """
    ).fetchone()
    comment_row = conn.execute(
        """
        SELECT COUNT(*) AS total,
               SUM(content = '') AS empty_content,
               SUM(commenter = '' OR commenter = '-1') AS invalid_commenter,
               SUM(no < 0) AS invalid_number,
               SUM(create_at <= 0) AS invalid_time,
               SUM(thank_count < 0) AS unknown_thanks,
               MAX(id) AS max_id,
               MAX(create_at) AS max_create_at
        FROM comment
        """
    ).fetchone()
    member_row = conn.execute(
        """
        SELECT COUNT(*) AS total,
               SUM(uid >= 0 AND username != '') AS valid,
               SUM(uid < 0 OR username = '') AS placeholders,
               MAX(uid) AS max_uid,
               MAX(create_at) AS max_create_at
        FROM member
        """
    ).fetchone()
    def values(columns: tuple[str, ...], row: sqlite3.Row | tuple) -> dict:
        return {key: int(value or 0) for key, value in zip(columns, row)}

    topics = values(
        (
            "total",
            "valid_time",
            "placeholders",
            "empty_title",
            "empty_author",
            "empty_node",
            "no_tags",
            "unknown_thanks",
            "unknown_favorites",
            "max_id",
            "max_create_at",
        ),
        topic_row,
    )
    if comment_gaps is None:
        comment_gaps = find_all_comment_gaps(conn, end_id=topics["max_id"])
    gap_row = (
        len(comment_gaps),
        sum(item.gap for item in comment_gaps),
        sum(item.gap == 1 for item in comment_gaps),
        sum(item.gap >= 100 for item in comment_gaps),
        sum(item.expected > 100 and item.actual <= 100 for item in comment_gaps),
    )

    return {
        "topics": topics,
        "comments": values(
            (
                "total",
                "empty_content",
                "invalid_commenter",
                "invalid_number",
                "invalid_time",
                "unknown_thanks",
                "max_id",
                "max_create_at",
            ),
            comment_row,
        ),
        "members": values(
            ("total", "valid", "placeholders", "max_uid", "max_create_at"),
            member_row,
        ),
        "comment_gaps": values(
            (
                "topics",
                "comments",
                "one_comment_topics",
                "large_gap_topics",
                "first_page_shortfalls",
            ),
            gap_row,
        ),
    }


def crawl_tracking_summary(conn: sqlite3.Connection) -> dict:
    tables = {
        str(name)
        for (name,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if not {"crawl_run", "topic_fetch_state"}.issubset(tables):
        return {"tracked_topics": 0, "status_counts": {}, "latest_run": None}

    status_counts = {
        str(status): int(count)
        for status, count in conn.execute(
            """
            SELECT last_status_code, COUNT(*)
            FROM topic_fetch_state
            GROUP BY last_status_code
            ORDER BY last_status_code
            """
        ).fetchall()
    }
    latest = conn.execute(
        """
        SELECT id, spider, started_at, finished_at, close_reason,
               response_count, error_count, configuration
        FROM crawl_run
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    return {
        "tracked_topics": sum(status_counts.values()),
        "status_counts": status_counts,
        "latest_run": (
            {
                "id": int(latest[0]),
                "spider": str(latest[1]),
                "started_at": int(latest[2]),
                "finished_at": int(latest[3]) if latest[3] is not None else None,
                "close_reason": str(latest[4]),
                "response_count": int(latest[5]),
                "error_count": int(latest[6]),
                "configuration": str(latest[7]),
            }
            if latest
            else None
        ),
    }


def serialize_comment_gaps(gaps: list[CommentGap]) -> list[dict]:
    return [{**asdict(item), "gap": item.gap} for item in gaps]


def quality_metrics(summary: dict, severe_gaps: list[CommentGap]) -> dict[str, int]:
    return {
        "topics.empty_title": summary["topics"]["empty_title"],
        "topics.empty_author": summary["topics"]["empty_author"],
        "topics.empty_node": summary["topics"]["empty_node"],
        "topics.unknown_thanks": summary["topics"]["unknown_thanks"],
        "topics.unknown_favorites": summary["topics"]["unknown_favorites"],
        "comments.empty_content": summary["comments"]["empty_content"],
        "comments.invalid_commenter": summary["comments"]["invalid_commenter"],
        "comments.invalid_number": summary["comments"]["invalid_number"],
        "comments.invalid_time": summary["comments"]["invalid_time"],
        "comments.unknown_thanks": summary["comments"]["unknown_thanks"],
        "severe_comment_gaps.topics": len(severe_gaps),
        "severe_comment_gaps.comments": sum(item.gap for item in severe_gaps),
    }


def quality_regressions(
    metrics: dict[str, int], maximums: dict[str, int]
) -> list[dict[str, int | str]]:
    regressions = []
    for name, maximum in maximums.items():
        actual = metrics.get(name)
        if actual is not None and actual > int(maximum):
            regressions.append(
                {"metric": name, "actual": actual, "maximum": int(maximum)}
            )
    return regressions


def quality_anomalies(
    conn: sqlite3.Connection, summary: dict, severe_gaps: list[CommentGap]
) -> dict[str, dict[str, int]]:
    conditions = {
        "topics": {
            "empty_title": "create_at > 0 AND title = ''",
            "empty_author": "create_at > 0 AND title != '' AND author = ''",
            "empty_node": "create_at > 0 AND title != '' AND node = ''",
            "unknown_thanks": "create_at > 0 AND title != '' AND thank_count < 0",
            "unknown_favorites": "create_at > 0 AND title != '' AND favorite_count < 0",
        },
        "comments": {
            "empty_content": "content = ''",
            "invalid_commenter": "commenter = '' OR commenter = '-1'",
            "invalid_number": "no < 0",
            "invalid_time": "create_at <= 0",
            "unknown_thanks": "thank_count < 0",
        },
    }
    result = {"severe_comment_gaps": {str(item.topic_id): item.gap for item in severe_gaps}}
    for group, fields in conditions.items():
        table = "topic" if group == "topics" else "comment"
        # Avoid another comment-table scan when the summary has no anomalies.
        active = {name: clause for name, clause in fields.items() if summary[group][name]}
        result.update({f"{group}.{name}": {} for name in fields})
        if not active:
            continue
        selection = ", ".join(f"({clause})" for clause in active.values())
        where = " OR ".join(f"({clause})" for clause in active.values())
        for record_id, *flags in conn.execute(f"SELECT id, {selection} FROM {table} WHERE {where}"):
            for name, flagged in zip(active, flags):
                if flagged:
                    result[f"{group}.{name}"][str(record_id)] = 1
    return result


def anomaly_regressions(
    current: dict[str, dict[str, int]], baseline: dict[str, dict[str, int]]
) -> list[dict]:
    return [
        {"metric": metric, "id": int(record_id), "actual": severity,
         "maximum": baseline.get(metric, {}).get(record_id, 0)}
        for metric, records in current.items()
        for record_id, severity in records.items()
        if severity > baseline.get(metric, {}).get(record_id, 0)
    ]


def supplement_quality_summary(conn: sqlite3.Connection) -> dict:
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='topic_supplement'"
    ).fetchone():
        return {"available": False}
    row = conn.execute(
        """
        SELECT COUNT(*), SUM(s.create_at <= 0),
               SUM(s.create_at > 0 AND s.create_at < t.create_at),
               COUNT(DISTINCT s.topic_id)
        FROM topic_supplement s LEFT JOIN topic t ON t.id = s.topic_id
        """
    ).fetchone()
    return {
        "available": True,
        **dict(zip(("total", "unknown_time", "before_topic_time", "topics"),
                   (int(value or 0) for value in row))),
        "interpretation": "Historical supplement times require source verification; valid-looking dates are not proof of accuracy.",
    }
