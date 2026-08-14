import json
from dataclasses import dataclass
from typing import Type, Union

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Mapped, Session, mapped_column

from v2ex_scrapy.change_tracking import ensure_change_tracking
from v2ex_scrapy.items import (
    Base,
    CommentItem,
    CrawlRunItem,
    MemberItem,
    TopicFetchState,
    TopicItem,
)


@dataclass(kw_only=True)
class LogItem(Base):
    __tablename__ = "log"

    id_: Mapped[int] = mapped_column(name="id", primary_key=True, autoincrement="auto")
    url: Mapped[str] = mapped_column()
    status_code: Mapped[int] = mapped_column(nullable=False)
    create_at: Mapped[int] = mapped_column(nullable=False)


class DB:
    CRAWL_RUN_STALE_SECONDS = 6 * 60 * 60

    def __init__(self, database_name="v2ex.sqlite"):
        self.engine = create_engine(
            f"sqlite:///{database_name}",
            echo=False,
            connect_args={"timeout": 60},
            json_serializer=lambda x: json.dumps(x, ensure_ascii=False),
        )
        Base.metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS ix_topic_fetch_state_last_fetched_at
                    ON topic_fetch_state (last_fetched_at)
                    """
                )
            )
        raw_connection = self.engine.raw_connection()
        try:
            ensure_change_tracking(raw_connection.driver_connection)
        finally:
            raw_connection.close()
        self.session = Session(self.engine)

    def close(self):
        self.session.commit()
        self.session.close()

    def exist(
        self,
        type_: Union[Type[TopicItem], Type[CommentItem], Type[MemberItem]],
        q: Union[str, int],
    ) -> bool:
        if type_ == MemberItem:
            query = text(
                f"SELECT * FROM {type_.__tablename__} WHERE {'username' if type(q) == str else 'uid'} = :q"
            )
        else:
            query = text(f"SELECT * FROM {type_.__tablename__} WHERE id = :q")
        result = self.session.execute(query, {"q": q}).fetchone()
        return result is not None

    def get_max_topic_id(self) -> int:
        result = self.session.execute(text("SELECT max(id) FROM topic")).fetchone()
        if result is None or result[0] is None:
            return 1
        return int(result[0])

    def get_topic_comment_count(self, topic_id) -> int:
        result = self.session.execute(
            text("select reply_count from topic where id = :q"), {"q": topic_id}
        ).fetchone()
        if result is None or result[0] is None:
            return 0
        return int(result[0])

    def get_comment_count_by_topic(self, topic_id) -> int:
        result = self.session.execute(
            text("select count(*) from comment where topic_id = :q"), {"q": topic_id}
        ).fetchone()
        if result is None or result[0] is None:
            return 0
        return int(result[0])

    def topic_has_empty_node(self, topic_id) -> bool:
        result = self.session.execute(
            text("select node, clicks from topic where id = :q"), {"q": topic_id}
        ).fetchone()
        return result is not None and result[0] == "" and int(result[1]) >= 0

    def start_crawl_run(
        self, spider: str, started_at: int, configuration: str = "{}"
    ) -> int:
        self.session.execute(
            text(
                """
                UPDATE crawl_run
                SET finished_at = :started_at,
                    close_reason = 'interrupted'
                WHERE finished_at IS NULL
                  AND started_at < :stale_before
                """
            ),
            {
                "started_at": started_at,
                "stale_before": started_at - self.CRAWL_RUN_STALE_SECONDS,
            },
        )
        run = CrawlRunItem(
            spider=spider,
            started_at=started_at,
            configuration=configuration,
        )
        self.session.add(run)
        self.session.commit()
        return run.id_

    def finish_crawl_run(
        self,
        run_id: int,
        finished_at: int,
        close_reason: str,
        response_count: int,
        error_count: int,
    ) -> None:
        run = self.session.get(CrawlRunItem, run_id)
        if run is None:
            return
        run.finished_at = finished_at
        run.close_reason = close_reason
        run.response_count = response_count
        run.error_count = error_count
        self.session.commit()

    def update_crawl_run_progress(
        self,
        run_id: int,
        response_count: int,
        error_count: int,
    ) -> None:
        self.session.execute(
            text(
                """
                UPDATE crawl_run
                SET response_count = :response_count,
                    error_count = :error_count
                WHERE id = :run_id
                  AND finished_at IS NULL
                """
            ),
            {
                "run_id": run_id,
                "response_count": response_count,
                "error_count": error_count,
            },
        )

    def record_topic_fetch(
        self,
        topic_id: int,
        status_code: int,
        fetched_at: int,
        url: str,
    ) -> None:
        state = self.session.get(TopicFetchState, topic_id)
        if state is None:
            self.session.add(
                TopicFetchState(
                    topic_id=topic_id,
                    last_status_code=status_code,
                    last_fetched_at=fetched_at,
                    attempt_count=1,
                    last_url=url,
                )
            )
            return
        state.last_status_code = status_code
        state.last_fetched_at = fetched_at
        state.attempt_count += 1
        state.last_url = url
