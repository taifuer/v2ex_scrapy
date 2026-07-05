# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


# useful for handling different item types with a single interface

from typing import Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

# don't remove
from v2ex_scrapy.DB import DB
from v2ex_scrapy.items import CommentItem, MemberItem, TopicItem, TopicSupplementItem

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
        self.commit_items(items)

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
                existing.thank_count = item.thank_count
                existing.favorite_count = item.favorite_count
                existing.reply_count = item.reply_count
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
                elif e.uid is None:
                    e.uid = item.uid
            self.db.session.commit()
        except SQLAlchemyError:
            self.db.session.rollback()
            raise

    def save_all(self):
        for _, v in self.data.items():
            self.process_it(v)

    def close_spider(self, spider):
        self.save_all()
        self.db.close()
