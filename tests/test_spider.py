import unittest

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
        spider.db.close()
        spider.common_spider.db.close()


if __name__ == "__main__":
    unittest.main()
