import tempfile
import unittest
from pathlib import Path

from v2ex_scrapy.DB import DB
from v2ex_scrapy.items import CommentItem
from v2ex_scrapy.pipelines import TutorialScrapyPipeline


class PipelineTest(unittest.TestCase):
    def test_comment_refresh_updates_existing_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            pipeline = TutorialScrapyPipeline()
            pipeline.db.close()
            pipeline.db = DB(str(Path(directory) / "test.sqlite"))
            original = CommentItem(
                id_=1,
                topic_id=10,
                commenter="alice",
                content="old",
                thank_count=1,
                create_at=100,
                no=1,
            )
            refreshed = CommentItem(
                id_=1,
                topic_id=10,
                commenter="alice",
                content="new",
                thank_count=3,
                create_at=100,
                no=1,
            )

            pipeline.process_comments([original])
            pipeline.process_comments([refreshed])
            saved = pipeline.db.session.get(CommentItem, 1)

            self.assertEqual(saved.content, "new")
            self.assertEqual(saved.thank_count, 3)
            pipeline.db.close()


if __name__ == "__main__":
    unittest.main()
