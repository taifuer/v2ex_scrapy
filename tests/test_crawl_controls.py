import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scrapy import Request
from scrapy.exceptions import CloseSpider, IgnoreRequest
from scrapy.http import HtmlResponse
from scrapy.settings import Settings

from v2ex_scrapy.middlewares import RateLimitDownloaderMiddleware
from v2ex_scrapy.spiders.V2exNodeTopicSpider import V2exNodeTopicSpider


class RateLimitDownloaderMiddlewareTest(unittest.TestCase):
    def middleware(self, **overrides):
        settings = Settings(
            {
                "V2EX_RATE_LIMIT_RETRIES": 2,
                "V2EX_RATE_LIMIT_BASE_DELAY": 5.0,
                "V2EX_RATE_LIMIT_MAX_DELAY": 300.0,
                "V2EX_RATE_LIMIT_ABORT_AFTER": 6,
                **overrides,
            }
        )
        crawler = SimpleNamespace(settings=settings, stats=Mock(), engine=Mock())
        return RateLimitDownloaderMiddleware(crawler), crawler

    def test_retry_after_supports_seconds_and_http_dates(self):
        self.assertEqual(
            RateLimitDownloaderMiddleware.retry_after_seconds(b"12"), 12.0
        )
        self.assertEqual(
            RateLimitDownloaderMiddleware.retry_after_seconds(
                "Thu, 01 Jan 1970 00:01:00 GMT", now=30
            ),
            30.0,
        )
        self.assertIsNone(
            RateLimitDownloaderMiddleware.retry_after_seconds("not-a-date")
        )

    def test_429_returns_delayed_replacement_request(self):
        middleware, _ = self.middleware()
        spider = SimpleNamespace(logger=Mock())
        request = Request("https://www.v2ex.com/t/1")
        response = HtmlResponse(
            request.url,
            status=429,
            headers={"Retry-After": "17"},
            request=request,
        )
        with patch(
            "twisted.internet.task.deferLater",
            side_effect=lambda reactor, delay, callback: callback(),
        ) as defer_later:
            retry = middleware.process_response(request, response, spider)

        self.assertIsInstance(retry, Request)
        self.assertTrue(retry.dont_filter)
        self.assertEqual(retry.meta[middleware.RETRY_META_KEY], 1)
        self.assertTrue(retry.meta["autothrottle_dont_adjust_delay"])
        self.assertEqual(defer_later.call_args.args[1], 17.0)

    def test_persistent_limit_stops_crawl(self):
        middleware, crawler = self.middleware(V2EX_RATE_LIMIT_ABORT_AFTER=1)
        spider = SimpleNamespace(logger=Mock())
        request = Request("https://www.v2ex.com/t/1")
        response = HtmlResponse(request.url, status=403, request=request)

        with self.assertRaises(IgnoreRequest):
            middleware.process_response(request, response, spider)
        crawler.engine.close_spider.assert_called_once_with(
            spider, reason="rate_limited"
        )


class V2exNodeTopicSpiderTest(unittest.TestCase):
    @staticmethod
    def response(body: str, page: int = 1) -> HtmlResponse:
        url = "https://www.v2ex.com/go/python"
        if page > 1:
            url += f"?p={page}"
        request = Request(url)
        return HtmlResponse(
            url,
            body=body.encode(),
            encoding="utf-8",
            request=request,
        )

    def test_extracts_page_count_and_topics_from_node_page(self):
        response = self.response(
            """
            <a href="/go/python?p=2">2</a><a href="?p=12">12</a>
            <span class="item_title"><a href="/t/101#reply9">One</a></span>
            <span class="item_title extra"><a href="/t/102">Two</a></span>
            """
        )
        self.assertEqual(V2exNodeTopicSpider.max_page(response), 12)
        self.assertEqual(
            V2exNodeTopicSpider.page_topics(response), [(101, 9), (102, 0)]
        )

    def test_schedules_topic_details_only_after_snapshot_finishes(self):
        spider = V2exNodeTopicSpider.__new__(V2exNodeTopicSpider)
        spider.node = "python"
        spider.pending_pages = {1, 2}
        spider.topic_snapshot = {}
        spider.snapshot_complete = False
        spider.topic_needs_refresh = Mock(return_value=True)
        spider.common_spider = SimpleNamespace(
            parse_topic=lambda response, topic_id: None,
            parse_topic_err=lambda failure: None,
        )

        page_one = self.response(
            '<span class="item_title"><a href="/t/101#reply2">One</a></span>'
        )
        page_two = self.response(
            """
            <span class="item_title"><a href="/t/101#reply3">One</a></span>
            <span class="item_title"><a href="/t/102#reply1">Two</a></span>
            """,
            page=2,
        )

        self.assertEqual(list(spider.collect_page(page_one, 1)), [])
        requests = list(spider.collect_page(page_two, 2))
        self.assertEqual(
            [request.cb_kwargs["topic_id"] for request in requests], [102, 101]
        )
        self.assertEqual(spider.topic_snapshot[101], 3)
        self.assertTrue(spider.snapshot_complete)

    def test_failed_listing_page_aborts_incomplete_snapshot(self):
        spider = V2exNodeTopicSpider.__new__(V2exNodeTopicSpider)
        spider.node = "python"
        failure = SimpleNamespace(
            request=SimpleNamespace(cb_kwargs={"page": 2})
        )

        with self.assertRaises(CloseSpider) as raised:
            spider.parse_page_err(failure)
        self.assertEqual(raised.exception.reason, "node_snapshot_incomplete")


if __name__ == "__main__":
    unittest.main()
