"""Shared, fixed quality thresholds used by analytics and database indexes."""

REPRESENTATIVE_COMMENT_MIN_THANKS = 3
PERIOD_POST_METRIC_MINIMUMS = {"favorite_count": 5, "thank_count": 5}


def ensure_analysis_indexes(connection) -> None:
    """Create small partial indexes that accelerate offline analytics scans."""
    index_name = "ix_comment_representative_create_at"
    existing = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?",
        (index_name,),
    ).fetchone()
    predicate = f"wherethank_count>={REPRESENTATIVE_COMMENT_MIN_THANKS}"
    normalized_sql = "".join((existing[0] or "").lower().split()) if existing else ""
    if existing and predicate not in normalized_sql:
        connection.execute(f"DROP INDEX {index_name}")
    connection.execute(
        f"""
        CREATE INDEX IF NOT EXISTS {index_name}
        ON comment (create_at, topic_id)
        WHERE thank_count >= {REPRESENTATIVE_COMMENT_MIN_THANKS}
        """
    )
    connection.commit()
