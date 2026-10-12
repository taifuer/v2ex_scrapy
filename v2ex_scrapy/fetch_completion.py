"""Track parsed and committed pages separately from HTTP response snapshots."""

import time
import hashlib
from uuid import uuid4

from sqlalchemy import delete, select

from v2ex_scrapy.items import CommentPageState, TopicCrawlState

ATTEMPT_META = "v2ex_fetch_attempt"
PAGE_META = "v2ex_comment_page"


def begin_attempt(session, topic_id: int, now: int | None = None) -> str:
    state = session.get(TopicCrawlState, topic_id)
    if state is None:
        state = TopicCrawlState(topic_id=topic_id, verified_at=0)
        session.add(state)
    state.attempt = uuid4().hex
    state.started_at = int(time.time()) if now is None else now
    state.completed_at = 0
    state.expected_pages = 0
    state.full_refresh = False
    session.execute(delete(CommentPageState).where(CommentPageState.topic_id == topic_id))
    session.add(CommentPageState(topic_id=topic_id, page=1, attempt=state.attempt, status="pending"))
    session.flush()
    return state.attempt


def plan_pages(session, topic_id: int, attempt: str, pages: list[int], total: int) -> None:
    state = session.get(TopicCrawlState, topic_id)
    if state is None or state.attempt != attempt:
        return
    pages = sorted(set(pages))
    state.expected_pages = len(pages)
    state.full_refresh = pages == list(range(1, total + 1))
    for page in pages:
        if session.get(CommentPageState, (topic_id, page)) is None:
            session.add(CommentPageState(topic_id=topic_id, page=page, attempt=attempt, status="pending"))
    session.flush()


def finish_page(session, topic_id: int, page: int, attempt: str, *, success: bool, now: int | None = None) -> None:
    state = session.get(TopicCrawlState, topic_id, populate_existing=True)
    item = session.get(CommentPageState, (topic_id, page), populate_existing=True)
    if state is None or item is None or state.attempt != attempt or item.attempt != attempt:
        return
    timestamp = int(time.time()) if now is None else now
    item.status = "persisted" if success else "failed"
    item.completed_at = timestamp if success else 0
    session.flush()
    pages = session.scalars(select(CommentPageState).where(CommentPageState.topic_id == topic_id)).all()
    complete = state.expected_pages > 0 and len(pages) == state.expected_pages and all(row.status == "persisted" for row in pages)
    state.completed_at = timestamp if complete else 0
    if complete and state.full_refresh:
        state.verified_at = timestamp


def completion_states(conn, start_id: int, end_id: int) -> dict[int, dict]:
    """Old databases have no evidence of completed pagination, not zero failures."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='topic_crawl_state'").fetchone():
        return {}
    return {
        row[0]: dict(zip(("started_at", "completed_at", "verified_at", "full_refresh"), row[1:]))
        for row in conn.execute(
            "SELECT topic_id, started_at, completed_at, verified_at, full_refresh FROM topic_crawl_state WHERE topic_id BETWEEN ? AND ?",
            (start_id, end_id),
        )
    }


def collection_fingerprint(conn) -> str | None:
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='topic_crawl_state'").fetchone():
        return None
    digest = hashlib.sha256()
    found = False
    for row in conn.execute("SELECT topic_id, attempt, completed_at, verified_at, full_refresh FROM topic_crawl_state ORDER BY topic_id"):
        digest.update(repr(tuple(row)).encode())
        found = True
    return digest.hexdigest() if found else None
