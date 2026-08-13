import sqlite3
import uuid
from pathlib import Path


TRACKING_SCHEMA_VERSION = 1
MIN_TRACKED_CREATE_AT = 1262304000
TRACKED_COMPONENTS = ("topic", "comment", "member")

_TRIGGER_NAMES = tuple(
    f"analysis_track_{component}_{operation}"
    for component in TRACKED_COMPONENTS
    for operation in ("insert", "update", "delete")
)


def _valid_topic(prefix: str) -> str:
    return f"{prefix}.clicks >= 0 AND {prefix}.create_at >= {MIN_TRACKED_CREATE_AT}"


def _valid_created(prefix: str) -> str:
    return f"{prefix}.create_at >= {MIN_TRACKED_CREATE_AT}"


def _trigger_statements() -> dict[str, str]:
    topic_old = _valid_topic("OLD")
    topic_new = _valid_topic("NEW")
    comment_old = _valid_created("OLD")
    comment_new = _valid_created("NEW")
    member_old = _valid_created("OLD")
    member_new = _valid_created("NEW")
    return {
        "analysis_track_topic_insert": f"""
            CREATE TRIGGER analysis_track_topic_insert
            AFTER INSERT ON topic
            WHEN {topic_new}
            BEGIN
                UPDATE analysis_change_state
                SET revision = revision + 1,
                    row_count = row_count + 1,
                    max_id = MAX(max_id, NEW.id),
                    max_create_at = MAX(max_create_at, NEW.create_at)
                WHERE component = 'topic';
            END
        """,
        "analysis_track_topic_update": f"""
            CREATE TRIGGER analysis_track_topic_update
            AFTER UPDATE OF id, author, title, node, tag, create_at, clicks,
                            reply_count, favorite_count, thank_count, votes ON topic
            WHEN (({topic_old}) != ({topic_new})) OR
                 (({topic_new}) AND (
                    OLD.id IS NOT NEW.id OR OLD.author IS NOT NEW.author OR
                    OLD.title IS NOT NEW.title OR OLD.node IS NOT NEW.node OR
                    OLD.tag IS NOT NEW.tag OR OLD.create_at IS NOT NEW.create_at OR
                    OLD.clicks IS NOT NEW.clicks OR
                    OLD.reply_count IS NOT NEW.reply_count OR
                    OLD.favorite_count IS NOT NEW.favorite_count OR
                    OLD.thank_count IS NOT NEW.thank_count OR
                    OLD.votes IS NOT NEW.votes
                 ))
            BEGIN
                UPDATE analysis_change_state
                SET revision = revision + 1,
                    row_count = row_count
                        + CASE WHEN {topic_new} THEN 1 ELSE 0 END
                        - CASE WHEN {topic_old} THEN 1 ELSE 0 END,
                    max_id = CASE
                        WHEN ({topic_new}) AND NEW.id >= max_id THEN NEW.id
                        WHEN ({topic_old}) AND OLD.id = max_id
                             AND (NOT ({topic_new}) OR NEW.id < OLD.id)
                        THEN COALESCE((
                            SELECT MAX(id) FROM topic
                            WHERE clicks >= 0 AND create_at >= {MIN_TRACKED_CREATE_AT}
                        ), 0)
                        ELSE max_id
                    END,
                    max_create_at = CASE
                        WHEN ({topic_new}) AND NEW.create_at >= max_create_at
                        THEN NEW.create_at
                        WHEN ({topic_old}) AND OLD.create_at = max_create_at
                             AND (NOT ({topic_new}) OR NEW.create_at < OLD.create_at)
                        THEN COALESCE((
                            SELECT MAX(create_at) FROM topic
                            WHERE clicks >= 0 AND create_at >= {MIN_TRACKED_CREATE_AT}
                        ), 0)
                        ELSE max_create_at
                    END
                WHERE component = 'topic';
            END
        """,
        "analysis_track_topic_delete": f"""
            CREATE TRIGGER analysis_track_topic_delete
            AFTER DELETE ON topic
            WHEN {topic_old}
            BEGIN
                UPDATE analysis_change_state
                SET revision = revision + 1,
                    row_count = row_count - 1,
                    max_id = CASE WHEN OLD.id = max_id THEN COALESCE((
                        SELECT MAX(id) FROM topic
                        WHERE clicks >= 0 AND create_at >= {MIN_TRACKED_CREATE_AT}
                    ), 0) ELSE max_id END,
                    max_create_at = CASE WHEN OLD.create_at = max_create_at THEN COALESCE((
                        SELECT MAX(create_at) FROM topic
                        WHERE clicks >= 0 AND create_at >= {MIN_TRACKED_CREATE_AT}
                    ), 0) ELSE max_create_at END
                WHERE component = 'topic';
            END
        """,
        "analysis_track_comment_insert": f"""
            CREATE TRIGGER analysis_track_comment_insert
            AFTER INSERT ON comment
            WHEN {comment_new}
            BEGIN
                UPDATE analysis_change_state
                SET revision = revision + 1,
                    row_count = row_count + 1,
                    max_id = MAX(max_id, NEW.id),
                    max_create_at = MAX(max_create_at, NEW.create_at)
                WHERE component = 'comment';
            END
        """,
        "analysis_track_comment_update": f"""
            CREATE TRIGGER analysis_track_comment_update
            AFTER UPDATE OF id, topic_id, commenter, content, thank_count,
                            create_at, no ON comment
            WHEN (({comment_old}) != ({comment_new})) OR
                 (({comment_new}) AND (
                    OLD.id IS NOT NEW.id OR OLD.topic_id IS NOT NEW.topic_id OR
                    OLD.commenter IS NOT NEW.commenter OR
                    OLD.content IS NOT NEW.content OR
                    OLD.thank_count IS NOT NEW.thank_count OR
                    OLD.create_at IS NOT NEW.create_at OR OLD.no IS NOT NEW.no
                 ))
            BEGIN
                UPDATE analysis_change_state
                SET revision = revision + 1,
                    row_count = row_count
                        + CASE WHEN {comment_new} THEN 1 ELSE 0 END
                        - CASE WHEN {comment_old} THEN 1 ELSE 0 END,
                    max_id = CASE
                        WHEN ({comment_new}) AND NEW.id >= max_id THEN NEW.id
                        WHEN ({comment_old}) AND OLD.id = max_id
                             AND (NOT ({comment_new}) OR NEW.id < OLD.id)
                        THEN COALESCE((
                            SELECT MAX(id) FROM comment
                            WHERE create_at >= {MIN_TRACKED_CREATE_AT}
                        ), 0)
                        ELSE max_id
                    END,
                    max_create_at = CASE
                        WHEN ({comment_new}) AND NEW.create_at >= max_create_at
                        THEN NEW.create_at
                        WHEN ({comment_old}) AND OLD.create_at = max_create_at
                             AND (NOT ({comment_new}) OR NEW.create_at < OLD.create_at)
                        THEN COALESCE((
                            SELECT MAX(create_at) FROM comment
                            WHERE create_at >= {MIN_TRACKED_CREATE_AT}
                        ), 0)
                        ELSE max_create_at
                    END
                WHERE component = 'comment';
            END
        """,
        "analysis_track_comment_delete": f"""
            CREATE TRIGGER analysis_track_comment_delete
            AFTER DELETE ON comment
            WHEN {comment_old}
            BEGIN
                UPDATE analysis_change_state
                SET revision = revision + 1,
                    row_count = row_count - 1,
                    max_id = CASE WHEN OLD.id = max_id THEN COALESCE((
                        SELECT MAX(id) FROM comment
                        WHERE create_at >= {MIN_TRACKED_CREATE_AT}
                    ), 0) ELSE max_id END,
                    max_create_at = CASE WHEN OLD.create_at = max_create_at THEN COALESCE((
                        SELECT MAX(create_at) FROM comment
                        WHERE create_at >= {MIN_TRACKED_CREATE_AT}
                    ), 0) ELSE max_create_at END
                WHERE component = 'comment';
            END
        """,
        "analysis_track_member_insert": f"""
            CREATE TRIGGER analysis_track_member_insert
            AFTER INSERT ON member
            WHEN {member_new}
            BEGIN
                UPDATE analysis_change_state
                SET revision = revision + 1,
                    row_count = row_count + 1,
                    max_id = MAX(max_id, NEW.uid),
                    max_create_at = MAX(max_create_at, NEW.create_at)
                WHERE component = 'member';
            END
        """,
        "analysis_track_member_update": f"""
            CREATE TRIGGER analysis_track_member_update
            AFTER UPDATE OF uid, username, create_at ON member
            WHEN (({member_old}) != ({member_new})) OR
                 (({member_new}) AND (
                    OLD.uid IS NOT NEW.uid OR OLD.username IS NOT NEW.username OR
                    OLD.create_at IS NOT NEW.create_at
                 ))
            BEGIN
                UPDATE analysis_change_state
                SET revision = revision + 1,
                    row_count = row_count
                        + CASE WHEN {member_new} THEN 1 ELSE 0 END
                        - CASE WHEN {member_old} THEN 1 ELSE 0 END,
                    max_id = CASE
                        WHEN ({member_new}) AND NEW.uid >= max_id THEN NEW.uid
                        WHEN ({member_old}) AND OLD.uid = max_id
                             AND (NOT ({member_new}) OR NEW.uid < OLD.uid)
                        THEN COALESCE((
                            SELECT MAX(uid) FROM member
                            WHERE create_at >= {MIN_TRACKED_CREATE_AT}
                        ), 0)
                        ELSE max_id
                    END,
                    max_create_at = CASE
                        WHEN ({member_new}) AND NEW.create_at >= max_create_at
                        THEN NEW.create_at
                        WHEN ({member_old}) AND OLD.create_at = max_create_at
                             AND (NOT ({member_new}) OR NEW.create_at < OLD.create_at)
                        THEN COALESCE((
                            SELECT MAX(create_at) FROM member
                            WHERE create_at >= {MIN_TRACKED_CREATE_AT}
                        ), 0)
                        ELSE max_create_at
                    END
                WHERE component = 'member';
            END
        """,
        "analysis_track_member_delete": f"""
            CREATE TRIGGER analysis_track_member_delete
            AFTER DELETE ON member
            WHEN {member_old}
            BEGIN
                UPDATE analysis_change_state
                SET revision = revision + 1,
                    row_count = row_count - 1,
                    max_id = CASE WHEN OLD.uid = max_id THEN COALESCE((
                        SELECT MAX(uid) FROM member
                        WHERE create_at >= {MIN_TRACKED_CREATE_AT}
                    ), 0) ELSE max_id END,
                    max_create_at = CASE WHEN OLD.create_at = max_create_at THEN COALESCE((
                        SELECT MAX(create_at) FROM member
                        WHERE create_at >= {MIN_TRACKED_CREATE_AT}
                    ), 0) ELSE max_create_at END
                WHERE component = 'member';
            END
        """,
    }


def read_change_tracking_state(connection: sqlite3.Connection) -> dict | None:
    try:
        metadata = dict(connection.execute(
            "SELECT key, value FROM analysis_change_metadata"
        ).fetchall())
        if (
            int(metadata.get("schema_version", 0)) != TRACKING_SCHEMA_VERSION
            or not metadata.get("database_id")
        ):
            return None
        rows = connection.execute(
            """
            SELECT component, revision, row_count, max_id, max_create_at
            FROM analysis_change_state
            ORDER BY component
            """
        ).fetchall()
    except (sqlite3.OperationalError, ValueError):
        return None
    if {row[0] for row in rows} != set(TRACKED_COMPONENTS):
        return None
    return {
        "schema_version": TRACKING_SCHEMA_VERSION,
        "database_id": metadata["database_id"],
        **{
            row[0]: {
                "revision": int(row[1]),
                "count": int(row[2]),
                "max_id": int(row[3]),
                "max_create_at": int(row[4]),
            }
            for row in rows
        },
    }


def ensure_change_tracking(connection: sqlite3.Connection) -> dict:
    connection.execute("PRAGMA busy_timeout = 60000")
    state = read_change_tracking_state(connection)
    trigger_names = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger' AND name LIKE 'analysis_track_%'"
        )
    }
    if state is not None and trigger_names == set(_TRIGGER_NAMES):
        return state

    old_revisions = {
        row[0]: int(row[1])
        for row in connection.execute(
            """
            SELECT component, revision FROM analysis_change_state
            WHERE component IN ('topic', 'comment', 'member')
            """
        ).fetchall()
    } if connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'analysis_change_state'"
    ).fetchone() else {}
    old_database_id = None
    if connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'analysis_change_metadata'"
    ).fetchone():
        row = connection.execute(
            "SELECT value FROM analysis_change_metadata WHERE key = 'database_id'"
        ).fetchone()
        old_database_id = row[0] if row else None

    statements = _trigger_statements()
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_change_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_change_state (
                component TEXT PRIMARY KEY,
                revision INTEGER NOT NULL,
                row_count INTEGER NOT NULL,
                max_id INTEGER NOT NULL,
                max_create_at INTEGER NOT NULL
            )
            """
        )
        for name in _TRIGGER_NAMES:
            connection.execute(f"DROP TRIGGER IF EXISTS {name}")
        connection.execute("DELETE FROM analysis_change_state")
        baselines = {
            "topic": connection.execute(
                f"""
                SELECT COUNT(*), COALESCE(MAX(id), 0), COALESCE(MAX(create_at), 0)
                FROM topic
                WHERE clicks >= 0 AND create_at >= {MIN_TRACKED_CREATE_AT}
                """
            ).fetchone(),
            "comment": connection.execute(
                f"""
                SELECT COUNT(*), COALESCE(MAX(id), 0), COALESCE(MAX(create_at), 0)
                FROM comment WHERE create_at >= {MIN_TRACKED_CREATE_AT}
                """
            ).fetchone(),
            "member": connection.execute(
                f"""
                SELECT COUNT(*), COALESCE(MAX(uid), 0), COALESCE(MAX(create_at), 0)
                FROM member WHERE create_at >= {MIN_TRACKED_CREATE_AT}
                """
            ).fetchone(),
        }
        connection.executemany(
            "INSERT INTO analysis_change_state VALUES (?, ?, ?, ?, ?)",
            [
                (
                    component,
                    old_revisions.get(component, 0) + 1,
                    int(values[0]),
                    int(values[1]),
                    int(values[2]),
                )
                for component, values in baselines.items()
            ],
        )
        connection.execute(
            "INSERT OR REPLACE INTO analysis_change_metadata VALUES ('schema_version', ?)",
            (str(TRACKING_SCHEMA_VERSION),),
        )
        connection.execute(
            "INSERT OR REPLACE INTO analysis_change_metadata VALUES ('database_id', ?)",
            (old_database_id or uuid.uuid4().hex,),
        )
        for name in _TRIGGER_NAMES:
            connection.execute(statements[name])
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    state = read_change_tracking_state(connection)
    if state is None:
        raise RuntimeError("failed to initialize analytics source change tracking")
    return state


def ensure_change_tracking_path(database: str | Path) -> dict:
    connection = sqlite3.connect(database, timeout=60)
    try:
        return ensure_change_tracking(connection)
    finally:
        connection.close()
