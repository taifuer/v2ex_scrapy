# Define here the models for your spider middleware
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/spider-middleware.html

# useful for handling different item types with a single interface

import json
import logging
import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

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


class RateLimitDownloaderMiddleware:
    """Back off on access limits and stop a crawl that remains blocked."""

    LIMITED_STATUSES = {403, 429}
    RETRY_META_KEY = "v2ex_rate_limit_retry_times"

    def __init__(self, crawler):
        self.crawler = crawler
        settings = crawler.settings
        self.max_retries = max(0, settings.getint("V2EX_RATE_LIMIT_RETRIES", 2))
        self.base_delay = max(
            0.0, settings.getfloat("V2EX_RATE_LIMIT_BASE_DELAY", 5.0)
        )
        self.max_delay = max(
            self.base_delay,
            settings.getfloat("V2EX_RATE_LIMIT_MAX_DELAY", 300.0),
        )
        self.abort_after = max(
            1, settings.getint("V2EX_RATE_LIMIT_ABORT_AFTER", 6)
        )
        self.consecutive_limited = 0

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    @staticmethod
    def retry_after_seconds(
        value: bytes | str | None, now: float | None = None
    ) -> float | None:
        if not value:
            return None
        text = (
            value.decode("ascii", errors="ignore")
            if isinstance(value, bytes)
            else value
        ).strip()
        if text.isdigit():
            return float(text)
        try:
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError, OverflowError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        current = datetime.fromtimestamp(
            now if now is not None else time.time(), timezone.utc
        )
        return max(0.0, (parsed - current).total_seconds())

    def retry_delay(self, response, retry_times: int) -> float:
        retry_after = self.retry_after_seconds(response.headers.get("Retry-After"))
        delay = (
            retry_after
            if retry_after is not None
            else self.base_delay * (2**retry_times)
        )
        return min(self.max_delay, max(0.0, delay))

    def stop_crawl(self, spider, reason: str) -> None:
        self.crawler.stats.inc_value("v2ex/rate_limit/aborted", spider=spider)
        engine = getattr(self.crawler, "engine", None)
        if engine is not None:
            engine.close_spider(spider, reason=reason)

    def process_response(self, request, response, spider):
        if response.status not in self.LIMITED_STATUSES:
            self.consecutive_limited = 0
            return response

        self.consecutive_limited += 1
        self.crawler.stats.inc_value(
            f"v2ex/rate_limit/status/{response.status}", spider=spider
        )
        if self.consecutive_limited >= self.abort_after:
            spider.logger.error(
                "Stopping crawl after %d consecutive limited responses; latest=%s %s",
                self.consecutive_limited,
                response.status,
                response.url,
            )
            self.stop_crawl(spider, "rate_limited")
            raise IgnoreRequest(
                f"persistent rate limit: {response.status} {response.url}"
            )

        retry_times = int(request.meta.get(self.RETRY_META_KEY, 0))
        if retry_times >= self.max_retries:
            spider.logger.warning(
                "Skipping %s after %d rate-limit retries (%s)",
                response.url,
                retry_times,
                response.status,
            )
            raise IgnoreRequest(f"rate limit retries exhausted: {response.url}")

        delay = self.retry_delay(response, retry_times)
        retry_request = request.copy()
        retry_request.dont_filter = True
        retry_request.meta[self.RETRY_META_KEY] = retry_times + 1
        retry_request.meta["autothrottle_dont_adjust_delay"] = True
        self.crawler.stats.inc_value("v2ex/rate_limit/retry", spider=spider)
        self.crawler.stats.inc_value(
            "v2ex/rate_limit/backoff_seconds", delay, spider=spider
        )
        spider.logger.warning(
            "Retrying %s in %.1fs after HTTP %s (%d/%d)",
            response.url,
            delay,
            response.status,
            retry_times + 1,
            self.max_retries,
        )

        # Import the installed reactor only after Scrapy has configured it.
        from twisted.internet import reactor
        from twisted.internet.task import deferLater

        return deferLater(reactor, delay, lambda: retry_request)


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
