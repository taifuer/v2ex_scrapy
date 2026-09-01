from pathlib import Path

import scrapy
import scrapy.http.response.html

from v2ex_scrapy.DB import DB
from v2ex_scrapy.items import TopicItem
from v2ex_scrapy.spiders.CommonSpider import CommonSpider
from v2ex_scrapy.utils import parse_bool, parse_id_ranges, parse_int


class V2exSpider(scrapy.Spider):
    name = "v2ex"
    FORCE_UPDATE_TOPIC = False
    UPDATE_COMMENT = True
    UPDATE_EMPTY_NODE = True
    DEFAULT_START_ID = 1
    DEFAULT_END_ID = 1000000

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.db = DB()
        self.max_existing_topic_id = self.db.get_max_topic_id()
        self.start_id = parse_int(kwargs.get("start_id"), self.DEFAULT_START_ID)
        self.end_id = parse_int(kwargs.get("end_id"), self.DEFAULT_END_ID)
        self.explicit_topic_selection = kwargs.get("topic_ids") is not None
        self.topic_ids = parse_id_ranges(kwargs.get("topic_ids"))
        topic_ids_file = kwargs.get("topic_ids_file")
        if topic_ids_file:
            self.explicit_topic_selection = True
            self.topic_ids = parse_id_ranges(
                Path(str(topic_ids_file)).read_text(encoding="utf-8")
            )
        self.force_update_topic = parse_bool(
            kwargs.get("force_update"), self.FORCE_UPDATE_TOPIC
        )
        self.update_empty_node = parse_bool(
            kwargs.get("update_empty_node"), self.UPDATE_EMPTY_NODE
        )
        self.crawl_members = parse_bool(kwargs.get("crawl_members"), True)
        self.crawl_purpose = str(kwargs.get("crawl_purpose", "crawl"))[:80]
        self.refresh_comments = parse_bool(
            kwargs.get("refresh_comments"), self.force_update_topic
        )
        self.common_spider = CommonSpider(
            self.logger,
            update_comment=self.UPDATE_COMMENT,
            crawl_members=self.crawl_members,
            refresh_existing_comments=self.refresh_comments,
            parse_comment_callback=self.parse_comment,
            parse_member_callback=self.parse_member,
            member_errback=self.member_err,
        )
        if self.topic_ids:
            self.logger.info(f"crawl {len(self.topic_ids)} explicitly selected topic ids")
        elif self.explicit_topic_selection:
            self.logger.info("explicit topic selection is empty; no topic requests")
        else:
            self.logger.info(f"start from topic id {self.start_id}, end at {self.end_id}")

    def start_requests(self):
        topic_ids = (
            self.topic_ids
            if self.explicit_topic_selection
            else range(self.start_id, self.end_id + 1)
        )
        for i in topic_ids:
            if self.should_crawl_topic(i):
                yield scrapy.Request(
                    url=f"https://www.v2ex.com/t/{i}",
                    callback=self.parse_topic,
                    errback=self.parse_topic_err,
                    cb_kwargs={"topic_id": i},
                    meta={
                        "dont_redirect": True,
                        "handle_httpstatus_list": [301, 302],
                    },
                )
            else:
                self.logger.info(f"skip topic {i}")

    def should_crawl_topic(self, topic_id: int) -> bool:
        if self.force_update_topic or topic_id > self.max_existing_topic_id:
            return True
        if not self.db.exist(TopicItem, topic_id):
            return True
        if self.update_empty_node and self.db.topic_has_empty_node(topic_id):
            return True
        return self.db.get_topic_comment_count(
            topic_id
        ) > self.db.get_comment_count_by_topic(topic_id)

    def parse_topic(self, response, topic_id: int):
        for item in self.common_spider.parse_topic(response, topic_id):
            yield item

    def parse_topic_err(self, failure):
        for item in self.common_spider.parse_topic_err(failure):
            yield item

    def parse_comment(self, response, topic_id: int):
        for item in self.common_spider.parse_comment(response, topic_id):
            yield item

    def parse_member(self, response, username: str):
        for item in self.common_spider.parse_member(response, username):
            yield item

    def member_err(self, failure):
        for item in self.common_spider.member_err(failure):
            yield item
