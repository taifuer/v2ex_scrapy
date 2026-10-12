import sqlite3
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scrapy import Request
from scrapy.http import HtmlResponse

from v2ex_scrapy.DB import DB
from v2ex_scrapy.fetch_completion import ATTEMPT_META, PAGE_META, begin_attempt, plan_pages, finish_page, completion_states
from v2ex_scrapy.items import CommentItem, MemberItem, TopicItem, TopicSupplementItem, TopicCrawlState, PagePersisted
from v2ex_scrapy.middlewares import SaveHttpStatusToDBMiddleware
from v2ex_scrapy.pipelines import TutorialScrapyPipeline
from analysis.builders.lifecycle_coverage import prepare_lifecycle_source
from v2ex_scrapy.spiders.CommonSpider import CommonSpider
from v2ex_scrapy.data_quality import incomplete_collection_topics, anomaly_regressions


class FetchCompletionTest(unittest.TestCase):
    def setUp(self):
        self.db = DB(":memory:")
        self.addCleanup(self.db.close)

    def plan(self, pages=None, total=3):
        attempt = begin_attempt(self.db.session, 42, 100)
        plan_pages(self.db.session, 42, attempt, pages or [1, 2, 3], total)
        self.db.session.commit()
        return attempt

    def state(self):
        return self.db.session.get(TopicCrawlState, 42, populate_existing=True)

    def test_failed_page_and_retry_require_every_page_to_commit(self):
        attempt = self.plan()
        for page in (1, 2):
            finish_page(self.db.session, 42, page, attempt, success=True, now=110)
        finish_page(self.db.session, 42, 3, attempt, success=False)
        self.assertEqual(self.state().completed_at, 0)
        finish_page(self.db.session, 42, 3, attempt, success=True, now=120)
        self.db.session.commit()
        self.assertEqual(self.state().completed_at, 120)
        self.assertEqual(self.state().verified_at, 120)

    def test_incremental_completion_does_not_claim_full_refresh(self):
        attempt = self.plan([1, 3])
        for page in (1, 3):
            finish_page(self.db.session, 42, page, attempt, success=True)
        self.assertGreater(self.state().completed_at, 0)
        self.assertEqual(self.state().verified_at, 0)

    def test_stale_response_cannot_complete_new_attempt(self):
        old = self.plan([1], 1)
        current = self.plan([1], 1)
        finish_page(self.db.session, 42, 1, old, success=True)
        self.assertEqual(self.state().completed_at, 0)
        finish_page(self.db.session, 42, 1, current, success=True)
        self.assertGreater(self.state().completed_at, 0)

    def test_http_failure_counts_and_persists_comment_page_failure(self):
        attempt = self.plan()
        middleware = SaveHttpStatusToDBMiddleware.__new__(SaveHttpStatusToDBMiddleware)
        middleware.db = self.db
        middleware.run_id = None
        middleware.pending = middleware.response_count = middleware.error_count = 0
        def parse_comment(response): pass
        request = Request("https://www.v2ex.com/t/42?p=3", callback=parse_comment,
                          cb_kwargs={"topic_id": 42}, meta={ATTEMPT_META: attempt, PAGE_META: 3})
        middleware.process_response(request, HtmlResponse(request.url, status=500, request=request), SimpleNamespace(logger=Mock()))
        self.assertEqual(middleware.error_count, 1)
        self.assertEqual(self.state().completed_at, 0)

    def test_pipeline_marker_waits_for_successful_commits(self):
        attempt = self.plan([1], 1)
        pipeline = TutorialScrapyPipeline.__new__(TutorialScrapyPipeline)
        pipeline.db = self.db
        pipeline.data = {kind: [] for kind in (TopicItem, CommentItem, MemberItem, TopicSupplementItem)}
        marker = PagePersisted(42, 1, attempt)
        with patch.object(pipeline, "save_all", side_effect=RuntimeError("disk full")):
            with self.assertRaises(RuntimeError):
                pipeline.process_item(marker, None)
        self.assertEqual(self.state().completed_at, 0)
        pipeline.process_item(marker, None)
        self.assertGreater(self.state().completed_at, 0)

    def test_page_completion_commits_buffered_comments_before_the_marker(self):
        attempt = self.plan([1], 1)
        pipeline = TutorialScrapyPipeline.__new__(TutorialScrapyPipeline)
        pipeline.db = self.db
        pipeline.data = {kind: [] for kind in (TopicItem, CommentItem, MemberItem, TopicSupplementItem)}
        comment = CommentItem(id_=1, topic_id=42, commenter="alice", content="A reply", thank_count=1, create_at=100, no=1)
        pipeline.process_item(comment, None)
        self.assertEqual(self.db.get_comment_count_by_topic(42), 0)
        pipeline.process_item(PagePersisted(42, 1, attempt), None)
        self.assertEqual(self.db.get_comment_count_by_topic(42), 1)
        self.assertEqual(pipeline.data[CommentItem], [])
        self.assertGreater(self.state().completed_at, 0)

    def test_legacy_database_is_not_reported_as_verified(self):
        with sqlite3.connect(":memory:") as conn:
            self.assertEqual(completion_states(conn, 1, 100), {})

    def test_known_incomplete_pages_block_publication_but_404_is_separate(self):
        with sqlite3.connect(":memory:") as conn:
            conn.executescript("""
                CREATE TABLE topic_crawl_state (topic_id INTEGER PRIMARY KEY, completed_at INTEGER);
                CREATE TABLE topic_fetch_state (topic_id INTEGER PRIMARY KEY, last_status_code INTEGER);
                INSERT INTO topic_crawl_state VALUES (1, 0), (2, 0), (3, 123);
                INSERT INTO topic_fetch_state VALUES (1, 200), (2, 404), (3, 200);
            """)
            incomplete = incomplete_collection_topics(conn)
            self.assertEqual(incomplete, {"1": 1})
            self.assertEqual(len(anomaly_regressions({"collection.incomplete_topics": incomplete}, {})), 1)

    def test_login_html_cannot_complete_a_topic_or_comment_page(self):
        spider = CommonSpider.__new__(CommonSpider)
        spider.db = self.db
        spider.logger = Mock()
        request = Request("https://www.v2ex.com/t/42")
        response = HtmlResponse(request.url, body=b"<html>Please login</html>", encoding="utf-8", request=request)
        with self.assertRaisesRegex(ValueError, "accessible topic"):
            list(spider.parse_topic(response, 42))
        with self.assertRaisesRegex(ValueError, "parsed no comments"):
            list(spider.parse_comment(response, 42))

    def test_lifecycle_excludes_tracked_windows_not_yet_verified(self):
        with sqlite3.connect(":memory:") as conn:
            conn.executescript("""
                CREATE TABLE topic (id INTEGER PRIMARY KEY, create_at INTEGER, clicks INTEGER);
                CREATE TABLE topic_crawl_state (topic_id INTEGER PRIMARY KEY, verified_at INTEGER);
                INSERT INTO topic VALUES (1, 100, 10), (2, 100, 10), (3, 100, 10);
                INSERT INTO topic_crawl_state VALUES (2, 101), (3, 1000000);
            """)
            coverage = prepare_lifecycle_source(conn, 4000000, 1)
            self.assertEqual(coverage["7"], {"elapsed_topics": 3, "verified_topics": 1,
                             "legacy_unverified_topics": 1, "excluded_tracked_topics": 1})
            self.assertEqual(conn.execute("SELECT id FROM lifecycle_topics_7d ORDER BY id").fetchall(), [(1,), (3,)])
            self.assertEqual(conn.execute("SELECT id FROM lifecycle_topics_30d").fetchall(), [(1,)])
