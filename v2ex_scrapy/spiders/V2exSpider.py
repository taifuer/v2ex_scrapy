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
        self.topic_ids = parse_id_ranges(kwargs.get("topic_ids"))
        self.force_update_topic = parse_bool(
            kwargs.get("force_update"), self.FORCE_UPDATE_TOPIC
        )
        self.update_empty_node = parse_bool(
            kwargs.get("update_empty_node"), self.UPDATE_EMPTY_NODE
        )
        self.common_spider = CommonSpider(
            self.logger, update_comment=self.UPDATE_COMMENT
        )
        if self.topic_ids:
            self.logger.info(f"crawl {len(self.topic_ids)} explicitly selected topic ids")
        else:
            self.logger.info(f"start from topic id {self.start_id}, end at {self.end_id}")

    def start_requests(self):
        topic_ids = self.topic_ids or range(self.start_id, self.end_id + 1)
        for i in topic_ids:
            if self.should_crawl_topic(i):
                yield scrapy.Request(
                    url=f"https://www.v2ex.com/t/{i}",
                    callback=self.common_spider.parse_topic,
                    errback=self.common_spider.parse_topic_err,
                    cb_kwargs={"topic_id": i},
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
