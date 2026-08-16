import re

import scrapy
import scrapy.http.response.html
from scrapy.exceptions import CloseSpider

from v2ex_scrapy.items import TopicItem
from v2ex_scrapy.spiders.CommonSpider import CommonSpider


class V2exNodeTopicSpider(scrapy.Spider):
    name = "v2ex-node"

    UPDATE_TOPIC_WHEN_REPLY_CHANGE = True
    UPDATE_COMMENT = True  # only work when UPDATE_TOPIC_WHEN_REPLY_CHANGE = True
    URL = "https://www.v2ex.com/go/"

    def __init__(self, node="flamewar", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.node = node
        self.common_spider = CommonSpider(
            self.logger, update_comment=self.UPDATE_COMMENT
        )
        self.db = self.common_spider.db
        self.pending_pages: set[int] = set()
        self.topic_snapshot: dict[int, int] = {}
        self.snapshot_complete = False

    def start_requests(self):
        yield scrapy.Request(
            url=f"{self.URL}{self.node}",
            callback=self.parse_index,
            errback=self.parse_index_err,
        )

    @staticmethod
    def max_page(response: scrapy.http.response.html.HtmlResponse) -> int:
        pages = [1]
        for href in response.xpath('//a[contains(@href, "?p=")]/@href').getall():
            match = re.search(r"[?&]p=(\d+)", href)
            if match:
                pages.append(int(match.group(1)))
        for value in response.xpath(
            '//tr/td[@align="left" and @width="92%"]/a/text()'
        ).getall():
            if value.strip().isdigit():
                pages.append(int(value.strip()))
        return max(pages)

    @staticmethod
    def page_topics(
        response: scrapy.http.response.html.HtmlResponse,
    ) -> list[tuple[int, int]]:
        topics = []
        for href in response.xpath(
            '//span[contains(concat(" ", normalize-space(@class), " "), " item_title ")]/a/@href'
        ).getall():
            match = re.search(r"/t/(\d+)(?:[^#]*#reply(\d+))?", href)
            if not match:
                continue
            topics.append((int(match.group(1)), int(match.group(2) or 0)))
        return topics

    def parse_index(self, response: scrapy.http.response.html.HtmlResponse):
        page_count = self.max_page(response)
        self.pending_pages = set(range(1, page_count + 1))
        self.logger.info(
            "Snapshotting node %s across %d page(s) before fetching topics",
            self.node,
            page_count,
        )
        yield from self.collect_page(response, 1)
        for page in range(2, page_count + 1):
            yield scrapy.Request(
                url=f"{self.URL}{self.node}?p={page}",
                callback=self.parse_page,
                errback=self.parse_page_err,
                cb_kwargs={"page": page},
            )

    def parse_index_err(self, failure):
        self.logger.error("Unable to read node index %s: %s", self.node, failure)
        raise CloseSpider("node_index_failed")

    def parse_page(
        self, response: scrapy.http.response.html.HtmlResponse, page: int
    ):
        yield from self.collect_page(response, page)

    def parse_page_err(self, failure):
        page = int(failure.request.cb_kwargs["page"])
        self.logger.error(
            "Unable to complete node %s snapshot because page %d failed: %s",
            self.node,
            page,
            failure,
        )
        raise CloseSpider("node_snapshot_incomplete")

    def collect_page(
        self, response: scrapy.http.response.html.HtmlResponse, page: int
    ):
        for topic_id, reply_count in self.page_topics(response):
            self.topic_snapshot[topic_id] = max(
                reply_count, self.topic_snapshot.get(topic_id, 0)
            )
        yield from self.finish_page(page)

    def finish_page(self, page: int):
        self.pending_pages.discard(page)
        if self.pending_pages or self.snapshot_complete:
            return
        self.snapshot_complete = True
        self.logger.info(
            "Node %s snapshot contains %d unique topics",
            self.node,
            len(self.topic_snapshot),
        )
        for topic_id in sorted(self.topic_snapshot, reverse=True):
            reply_count = self.topic_snapshot[topic_id]
            if self.topic_needs_refresh(topic_id, reply_count):
                yield scrapy.Request(
                    url=f"https://www.v2ex.com/t/{topic_id}",
                    callback=self.common_spider.parse_topic,
                    errback=self.common_spider.parse_topic_err,
                    cb_kwargs={"topic_id": topic_id},
                )

    def topic_needs_refresh(self, topic_id: int, reply_count: int) -> bool:
        return (
            not self.db.exist(TopicItem, topic_id)
            or self.db.topic_has_empty_node(topic_id)
            or (
                self.UPDATE_TOPIC_WHEN_REPLY_CHANGE
                and self.db.get_comment_count_by_topic(topic_id) < reply_count
            )
        )

    def closed(self, reason):
        self.db.close()
