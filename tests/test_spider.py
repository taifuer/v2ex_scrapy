import unittest
from tempfile import NamedTemporaryFile

from v2ex_scrapy.spiders.V2exSpider import V2exSpider


class V2exSpiderTest(unittest.TestCase):
    def test_topic_callbacks_are_serializable_for_jobdir_resume(self):
        spider = V2exSpider(
            start_id="1224064",
            end_id="1224064",
            force_update="true",
        )
        request = next(spider.start_requests())
        serialized = request.to_dict(spider=spider)

        self.assertEqual(serialized["callback"], "parse_topic")
        self.assertEqual(serialized["errback"], "parse_topic_err")
        self.assertTrue(request.meta["dont_redirect"])
        self.assertEqual(request.meta["handle_httpstatus_list"], [301, 302])
        self.assertTrue(spider.refresh_comments)
        spider.db.close()
        spider.common_spider.db.close()

    def test_topic_refresh_can_skip_historical_comment_replay(self):
        spider = V2exSpider(
            topic_ids="1224064",
            force_update="true",
            refresh_comments="false",
        )

        self.assertFalse(spider.refresh_comments)
        self.assertFalse(spider.common_spider.REFRESH_EXISTING_COMMENTS)
        spider.db.close()
        spider.common_spider.db.close()

    def test_empty_explicit_topic_file_does_not_fall_back_to_default_range(self):
        with NamedTemporaryFile(mode="w", encoding="utf-8") as topic_ids_file:
            spider = V2exSpider(topic_ids_file=topic_ids_file.name)

            self.assertEqual(list(spider.start_requests()), [])

            spider.db.close()
            spider.common_spider.db.close()


if __name__ == "__main__":
    unittest.main()
