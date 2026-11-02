import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from scrapy import Request
from scrapy.exceptions import IgnoreRequest
from scrapy.http import HtmlResponse
from scrapy.settings import Settings

from v2ex_scrapy.browser_request import BrowserRequestError, html_base_url, same_html_origin
from v2ex_scrapy.middlewares import ProxyAndCookieDownloaderMiddleware
from v2ex_scrapy.spiders.CommonSpider import CommonSpider
from v2ex_scrapy.spiders.V2exMemberSpider import V2exTopicSpider as MemberSpider
from v2ex_scrapy.spiders.V2exNodeTopicSpider import V2exNodeTopicSpider
from v2ex_scrapy.spiders.V2exSpider import V2exSpider


class CrawlOriginTest(unittest.TestCase):
    def test_only_two_official_https_html_origins_are_allowed(self):
        for host in ("www.v2ex.com", "v2ex.com"):
            self.assertEqual(html_base_url(host), f"https://{host}")
            self.assertTrue(same_html_origin(f"https://{host}:443/t/1", host))
        for host in ("edge.v2ex.com", "example.com", "v2ex.com:443", "v2ex.com/path"):
            with self.subTest(host=host), self.assertRaises(BrowserRequestError):
                html_base_url(host)

    def test_topic_and_member_start_requests_use_the_selected_host(self):
        for host in ("www.v2ex.com", "v2ex.com"):
            for kind, path in ((V2exSpider, "t"), (MemberSpider, "uid")):
                with self.subTest(host=host, spider=kind.name):
                    spider = kind.__new__(kind)
                    spider.settings = Settings({"V2EX_HOST": host})
                    spider.start_id = spider.end_id = 42
                    spider.explicit_topic_selection = False
                    spider.topic_ids = []
                    spider.should_crawl_topic = Mock(return_value=True)
                    spider.db = SimpleNamespace(exist=Mock(return_value=False))
                    requests = list(spider.start_requests())
                    self.assertEqual([request.url for request in requests], [f"https://{host}/{path}/42"])

    def test_node_listing_pagination_and_details_stay_on_the_selected_host(self):
        spider = V2exNodeTopicSpider.__new__(V2exNodeTopicSpider)
        spider.settings = Settings({"V2EX_HOST": "v2ex.com"})
        spider.node = "python"
        spider.topic_snapshot = {}
        spider.snapshot_complete = False
        spider.topic_needs_refresh = Mock(return_value=True)
        spider.common_spider = SimpleNamespace(parse_topic=Mock(), parse_topic_err=Mock())
        initial = next(spider.start_requests())
        self.assertEqual(initial.url, "https://v2ex.com/go/python")
        response = HtmlResponse(initial.url, request=initial, encoding="utf-8", body=b'''
            <a href="/go/python?p=2">2</a>
            <span class="item_title"><a href="/t/42#reply5">Title</a></span>
        ''')
        pages = list(spider.parse_index(response))
        self.assertEqual([request.url for request in pages], ["https://v2ex.com/go/python?p=2"])
        topics = list(spider.collect_page(response, 2))
        self.assertEqual([request.url for request in topics], ["https://v2ex.com/t/42"])

    def test_comment_pages_and_member_links_preserve_the_response_origin(self):
        common = CommonSpider.__new__(CommonSpider)
        common.parse_comment_callback = Mock()
        common.parse_member_callback = Mock()
        common.member_errback = Mock()
        common.CRAWL_MEMBERS = True
        common.UPDATE_MEMBER = False
        common.db = SimpleNamespace(member_needs_refresh=Mock(return_value=True))
        request = Request("https://v2ex.com/t/42")
        response = HtmlResponse(request.url, request=request)
        self.assertEqual(next(common.crawl_comment(42, 2, response)).url, "https://v2ex.com/t/42?p=2")
        self.assertEqual(next(common.crawl_member("alice", response)).url, "https://v2ex.com/member/alice")

    def test_cookies_are_attached_only_on_the_configured_origin(self):
        spider = SimpleNamespace(name="test", logger=Mock(), settings=Settings({
            "V2EX_HOST": "v2ex.com", "COOKIES": "session=private",
        }))
        middleware = ProxyAndCookieDownloaderMiddleware()
        middleware.spider_opened(spider)
        request = Request("https://v2ex.com/t/42")
        middleware.process_request(request, spider)
        self.assertEqual(request.cookies, {"session": "private"})
        for url in ("https://www.v2ex.com/t/42", "http://v2ex.com/t/42",
                    "https://edge.v2ex.com/t/42", "https://example.com/t/42",
                    "https://v2ex.com:8443/t/42"):
            other = Request(url)
            with self.subTest(url=url), self.assertRaises(IgnoreRequest):
                middleware.process_request(other, spider)
            self.assertEqual(other.cookies, {})


if __name__ == "__main__":
    unittest.main()
