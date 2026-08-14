import unittest

from v2ex_scrapy.spiders.CommonSpider import (
    comment_start_page,
    should_crawl_comment_pages,
)


class CommonSpiderTest(unittest.TestCase):
    def test_incremental_comment_crawl_resumes_from_partial_page(self):
        self.assertEqual(comment_start_page(250, refresh_existing=False), 3)

    def test_forced_comment_crawl_revisits_all_paginated_pages(self):
        self.assertEqual(comment_start_page(900, refresh_existing=True), 2)
        self.assertTrue(
            should_crawl_comment_pages(
                900,
                900,
                update_comments=True,
                refresh_existing=True,
            )
        )

    def test_incremental_comment_crawl_skips_complete_topics(self):
        self.assertFalse(
            should_crawl_comment_pages(
                900,
                900,
                update_comments=True,
                refresh_existing=False,
            )
        )


if __name__ == "__main__":
    unittest.main()
