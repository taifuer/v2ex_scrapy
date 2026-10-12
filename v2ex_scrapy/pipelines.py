# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


# useful for handling different item types with a single interface

from typing import Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

# don't remove
from v2ex_scrapy.DB import DB
from v2ex_scrapy.fetch_completion import finish_page
from v2ex_scrapy.items import CommentItem, MemberItem, PagePersisted, TopicItem, TopicSupplementItem

ItemsType = TopicItem | CommentItem | MemberItem | TopicSupplementItem


class TutorialScrapyPipeline:
    BATCH = 10

    def __init__(self):
        # Connect to SQLite database
        self.db = DB()
        self.data: dict[Any, list[ItemsType]] = {
            TopicItem: [],
            CommentItem: [],
            MemberItem: [],
            TopicSupplementItem: [],
        }

    def process_item(
        self,
        item: ItemsType | Any,
        spider,
    ):
        if isinstance(item, PagePersisted):
            # A page is complete only after every preceding item has committed.
            self.save_all()
            finish_page(self.db.session, item.topic_id, item.page, item.attempt, success=True)
            self.db.session.commit()
            return item
        if isinstance(item, (TopicItem, CommentItem, MemberItem, TopicSupplementItem)):
            item_type = type(item)
            self.data[item_type].append(item)
            if len(self.data[item_type]) >= self.BATCH:
                self.process_it(self.data[item_type])
                self.data[item_type] = []
        return item

    def process_it(self, items: list[ItemsType]):
        if len(items) == 0:
            return
        if isinstance(items[0], TopicItem):
            self.process_topics(items)  # type: ignore[arg-type]
            return
        if isinstance(items[0], MemberItem):
            self.process_members(items)  # type: ignore[arg-type]
            return
        if isinstance(items[0], CommentItem):
            self.process_comments(items)  # type: ignore[arg-type]
            return
        if isinstance(items[0], TopicSupplementItem):
            self.process_supplements(items)  # type: ignore[arg-type]
            return
        self.commit_items(items)

    def process_supplements(self, items: list[TopicSupplementItem]):
        try:
            for item in items:
                matching = self.db.session.query(TopicSupplementItem).filter_by(
                    topic_id=item.topic_id, content=item.content,
                )
                if item.create_at > 0:
                    # A verified refetch replaces only the exact unknown-time copy.
                    matching.filter(TopicSupplementItem.create_at == 0).delete()
                elif matching.filter(TopicSupplementItem.create_at > 0).first():
                    continue
                self.db.session.merge(item)
            self.db.session.commit()
        except SQLAlchemyError:
            self.db.session.rollback()
            raise

    def process_topics(self, items: list[TopicItem]):
        try:
            for item in items:
                existing = self.db.session.get(TopicItem, item.id_)
                if existing is None:
                    self.db.session.add(item)
                    continue

                if item.clicks < 0:
                    continue

                existing.author = item.author
                existing.title = item.title
                if item.content != "":
                    existing.content = item.content
                if item.node != "":
                    existing.node = item.node
                if len(item.tag) > 0:
                    existing.tag = item.tag
                existing.clicks = item.clicks
                existing.votes = item.votes
                existing.create_at = item.create_at
                if item.thank_count >= 0:
                    existing.thank_count = item.thank_count
                if item.favorite_count >= 0:
                    existing.favorite_count = item.favorite_count
                existing.reply_count = item.reply_count
            self.db.session.commit()
        except SQLAlchemyError:
            self.db.session.rollback()
            raise

    def process_comments(self, items: list[CommentItem]):
        try:
            for item in items:
                existing = self.db.session.get(CommentItem, item.id_)
                if existing is None:
                    self.db.session.add(item)
                    continue
                existing.topic_id = item.topic_id
                existing.commenter = item.commenter
                existing.content = item.content
                existing.thank_count = item.thank_count
                existing.create_at = item.create_at
                existing.no = item.no
            self.db.session.commit()
        except SQLAlchemyError:
            self.db.session.rollback()
            raise

    def commit_items(self, items: list[ItemsType]):
        try:
            self.db.session.add_all(items)
            self.db.session.commit()
        except IntegrityError:
            self.db.session.rollback()
            self.commit_items_one_by_one(items)
        except SQLAlchemyError:
            self.db.session.rollback()
            raise

    def commit_items_one_by_one(self, items: list[ItemsType]):
        for item in items:
            try:
                self.db.session.add(item)
                self.db.session.commit()
            except IntegrityError:
                self.db.session.rollback()
            except SQLAlchemyError:
                self.db.session.rollback()
                raise

    def process_members(self, items: list[MemberItem]):
        try:
            for item in items:
                e = (
                    self.db.session.query(MemberItem)
                    .where(MemberItem.username == item.username)
                    .first()
                )
                if e is None:
                    self.db.session.add_all([item])
                elif item.uid is not None and item.uid > 0:
                    canonical = self.db.session.get(MemberItem, (item.uid, item.username))
                    if canonical is not None:
                        e = canonical
                    self.db.session.query(MemberItem).filter(
                        MemberItem.username == item.username, MemberItem.uid <= 0,
                        MemberItem.uid != e.uid,
                    ).delete(synchronize_session="fetch")
                    e.uid = item.uid
                    if item.avatar_url:
                        e.avatar_url = item.avatar_url
                    if item.create_at > 0:
                        e.create_at = item.create_at
                    if item.social_link:
                        e.social_link = item.social_link
            self.db.session.commit()
        except SQLAlchemyError:
            self.db.session.rollback()
            raise

    def save_all(self):
        for key, values in self.data.items():
            self.process_it(values)
            self.data[key] = []

    def close_spider(self, spider):
        self.save_all()
        self.db.close()
