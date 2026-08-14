# Define here the models for your spider middleware
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/spider-middleware.html

# useful for handling different item types with a single interface

import json
import logging
import random
import time

import scrapy
import scrapy.http.response.html
from scrapy import signals
from scrapy.exceptions import IgnoreRequest
from sqlalchemy.exc import SQLAlchemyError

from v2ex_scrapy import utils
from v2ex_scrapy.DB import DB, LogItem


class TutorialScrapySpiderMiddleware:
    # Not all methods need to be defined. If a method is not defined,
    # scrapy acts as if the spider middleware does not modify the
    # passed objects.

    @classmethod
    def from_crawler(cls, crawler):
        # This method is used by Scrapy to create your spiders.
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_spider_input(self, response, spider):
        # Called for each response that goes through the spider
        # middleware and into the spider.

        # Should return None or raise an exception.
        return None

    def process_spider_output(self, response, result, spider):
        # Called with the results returned from the Spider, after
        # it has processed the response.

        # Must return an iterable of Request, or item objects.
        for i in result:
            yield i

    def process_spider_exception(self, response, exception, spider):
        # Called when a spider or process_spider_input() method
        # (from other spider middleware) raises an exception.

        # Should return either None or an iterable of Request or item objects.
        pass

    def process_start_requests(self, start_requests, spider):
        # Called with the start requests of the spider, and works
        # similarly to the process_spider_output() method, except
        # that it doesn’t have a response associated.

        # Must return only requests (not items).
        for r in start_requests:
            yield r

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s" % spider.name)


class ProxyAndCookieDownloaderMiddleware:
    # Not all methods need to be defined. If a method is not defined,
    # scrapy acts as if the downloader middleware does not modify the
    # passed objects.
    def __init__(self):
        self.proxies: list[str] = []
        self.cookies: dict[str, str] = {}
        self.logger = logging.getLogger(__name__)

    @classmethod
    def from_crawler(cls, crawler):
        # This method is used by Scrapy to create your spiders.
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_request(self, request: scrapy.Request, spider):
        if "proxy" not in request.meta and len(self.proxies) > 0:
            request.meta["proxy"] = random.choice(self.proxies)
        if self.cookies != {} and request.cookies == {}:
            request.cookies = self.cookies
        # Called for each request that goes through the downloader
        # middleware.

        # Must either:
        # - return None: continue processing this request
        # - or return a Response object
        # - or return a Request object
        # - or raise IgnoreRequest: process_exception() methods of
        #   installed downloader middleware will be called
        return None

    def process_response(
        self,
        request: scrapy.Request,
        response: scrapy.http.response.html.HtmlResponse,
        spider: scrapy.Spider,
    ):
        # Called with the response returned from the downloader.
        if response.status == 403:
            self.logger.info(f"skip url:{response.url}, because 403")
            raise IgnoreRequest(f"403 url {response.url}")
        # Must either;
        # - return a Response object
        # - return a Request object
        # - or raise IgnoreRequest
        return response

    def process_exception(self, request, exception, spider):
        # Called when a download handler or a process_request()
        # (from other downloader middleware) raises an exception.

        # Must either:
        # - return None: continue processing this exception
        # - return a Response object: stops process_exception() chain
        # - return a Request object: stops process_exception() chain
        pass

    def spider_opened(self, spider: scrapy.Spider):
        self.proxies = spider.settings.get("PROXIES", [])  # type: ignore

        cookie_str = spider.settings.get("COOKIES", "")
        self.cookies = utils.cookie_str2cookie_dict(cookie_str)  # type: ignore

        spider.logger.info("Spider opened: %s" % spider.name)


class RandomUserAgentMiddleware:
    def __init__(self):
        self.user_agents: list[str] = []

    @classmethod
    def from_crawler(cls, crawler):
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_request(self, request: scrapy.Request, spider):
        if len(self.user_agents) > 0:
            request.headers[b"User-Agent"] = random.choice(self.user_agents)
        return None

    def spider_opened(self, spider: scrapy.Spider):
        with open("./user-agents.txt") as f:
            self.user_agents = f.read().splitlines()


class SaveHttpStatusToDBMiddleware:
    BATCH = 20

    def __init__(self):
        self.db = DB()
        self.pending = 0
        self.run_id: int | None = None
        self.response_count = 0
        self.error_count = 0

    @classmethod
    def from_crawler(cls, crawler):
        middleware = cls()
        crawler.signals.connect(middleware.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(middleware.spider_closed, signal=signals.spider_closed)
        return middleware

    @staticmethod
    def crawl_configuration(spider) -> dict:
        configuration = {
            key: getattr(spider, key)
            for key in (
                "start_id",
                "end_id",
                "force_update_topic",
                "update_empty_node",
                "crawl_members",
                "refresh_comments",
                "crawl_purpose",
            )
            if hasattr(spider, key)
        }
        if hasattr(spider, "topic_ids"):
            topic_ids = list(spider.topic_ids or [])
            if topic_ids:
                configuration.pop("start_id", None)
                configuration.pop("end_id", None)
                configuration.update(
                    {
                        "selected_topic_count": len(topic_ids),
                        "selected_topic_min": min(topic_ids),
                        "selected_topic_max": max(topic_ids),
                    }
                )
        return configuration

    def spider_opened(self, spider):
        configuration = self.crawl_configuration(spider)
        self.run_id = self.db.start_crawl_run(
            spider=spider.name,
            started_at=int(time.time()),
            configuration=json.dumps(configuration, ensure_ascii=False),
        )

    @staticmethod
    def topic_request_id(request) -> int | None:
        callback = getattr(request.callback, "__name__", "")
        topic_id = request.cb_kwargs.get("topic_id")
        if callback != "parse_topic" or topic_id is None:
            return None
        try:
            return int(topic_id)
        except (TypeError, ValueError):
            return None

    def process_response(
        self, request, response: scrapy.http.response.html.HtmlResponse, spider
    ):
        url = response.url
        status_code = response.status
        create_at = int(time.time())
        topic_id = self.topic_request_id(request)
        if topic_id is not None:
            self.db.record_topic_fetch(topic_id, status_code, create_at, url)
            if status_code >= 400 or status_code in {301, 302}:
                self.error_count += 1
        self.db.session.add(
            LogItem(url=url, status_code=status_code, create_at=create_at)
        )
        self.pending += 1
        self.response_count += 1
        # Persist topic state before the item pipeline begins writing. Keeping
        # this transaction open would hold SQLite's single writer lock.
        if topic_id is not None or self.pending >= self.BATCH:
            self.commit(spider)
        return response

    def process_exception(self, request, exception, spider):
        topic_id = self.topic_request_id(request)
        if topic_id is not None:
            self.db.record_topic_fetch(
                topic_id,
                -1,
                int(time.time()),
                request.url,
            )
            self.pending += 1
            self.error_count += 1
            self.commit(spider)
        return None

    def commit(self, spider):
        try:
            if self.run_id is not None:
                self.db.update_crawl_run_progress(
                    self.run_id,
                    self.response_count,
                    self.error_count,
                )
            self.db.session.commit()
        except SQLAlchemyError as exc:
            self.db.session.rollback()
            spider.logger.warning("Failed to persist HTTP status batch: %s", exc)
        finally:
            self.pending = 0

    def spider_closed(self, spider, reason):
        if self.pending > 0:
            self.commit(spider)
        if self.run_id is not None:
            self.db.finish_crawl_run(
                run_id=self.run_id,
                finished_at=int(time.time()),
                close_reason=str(reason),
                response_count=self.response_count,
                error_count=self.error_count,
            )
        self.db.close()
