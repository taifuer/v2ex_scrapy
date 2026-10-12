"""Separate elapsed observation windows from verified comment collection."""


def prepare_lifecycle_source(conn, data_as_of: int, minimum_created_at: int) -> dict:
    tracked = bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='topic_crawl_state'"
    ).fetchone())
    coverage = {}
    for days in (7, 30):
        window = days * 86400
        cutoff = data_as_of - window
        conn.execute(f"DROP VIEW IF EXISTS temp.lifecycle_topics_{days}d")
        condition = "1"
        if tracked:
            condition = f"""NOT EXISTS (SELECT 1 FROM topic_crawl_state s WHERE s.topic_id = t.id)
                OR EXISTS (SELECT 1 FROM topic_crawl_state s WHERE s.topic_id = t.id
                           AND s.verified_at >= t.create_at + {window})"""
        conn.execute(f"CREATE TEMP VIEW lifecycle_topics_{days}d AS SELECT t.* FROM topic t WHERE ({condition})")
        base = "t.clicks >= 0 AND t.create_at >= ? AND t.create_at <= ?"
        total = conn.execute(f"SELECT COUNT(*) FROM topic t WHERE {base}", (minimum_created_at, cutoff)).fetchone()[0]
        verified, legacy = 0, total
        if tracked:
            verified, legacy = conn.execute(f"""
                SELECT COALESCE(SUM(s.verified_at >= t.create_at + {window}), 0),
                       COALESCE(SUM(s.topic_id IS NULL), 0)
                FROM topic t LEFT JOIN topic_crawl_state s ON s.topic_id = t.id
                WHERE {base}
            """, (minimum_created_at, cutoff)).fetchone()
        coverage[str(days)] = {"elapsed_topics": total, "verified_topics": verified,
                               "legacy_unverified_topics": legacy,
                               "excluded_tracked_topics": total - verified - legacy}
    return coverage
