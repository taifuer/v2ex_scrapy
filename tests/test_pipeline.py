import tempfile
import unittest
from pathlib import Path

from v2ex_scrapy.DB import DB
from v2ex_scrapy.items import CommentItem, TopicItem, TopicSupplementItem
from v2ex_scrapy.pipelines import TutorialScrapyPipeline


class PipelineTest(unittest.TestCase):
    def test_supplement_refetch_replaces_unknown_time_without_losing_distinct_updates(self):
        with tempfile.TemporaryDirectory() as directory:
            pipeline = TutorialScrapyPipeline()
            pipeline.db.close()
            pipeline.db = DB(str(Path(directory) / "test.sqlite"))
            def supplement(content, timestamp):
                return TopicSupplementItem(topic_id=10, content=content, create_at=timestamp)
            pipeline.process_it([supplement("same", 0), supplement("different", 0)])
            pipeline.process_it([supplement("same", 100), supplement("same", 100)])
            pipeline.process_it([supplement("same", 0), supplement("same", 200)])
            saved = pipeline.db.session.query(TopicSupplementItem).all()
            self.assertEqual(
                {(item.content, item.create_at) for item in saved},
                {("same", 100), ("same", 200), ("different", 0)},
            )
            pipeline.db.close()

    def test_topic_refresh_preserves_known_interactions_when_page_hides_them(self):
        with tempfile.TemporaryDirectory() as directory:
            pipeline = TutorialScrapyPipeline()
            pipeline.db.close()
            pipeline.db = DB(str(Path(directory) / "test.sqlite"))
            original = TopicItem(
                id_=10,
                author="alice",
                title="Original",
                content="content",
                node="python",
                tag=["Python"],
                clicks=100,
                votes=2,
                create_at=100,
                thank_count=4,
                favorite_count=8,
                reply_count=3,
            )
            refreshed = TopicItem(
                id_=10,
                author="alice",
                title="Refreshed",
                content="content",
                node="python",
                tag=["Python"],
                clicks=120,
                votes=3,
                create_at=100,
                thank_count=-1,
                favorite_count=-1,
                reply_count=5,
            )

            pipeline.process_topics([original])
            pipeline.process_topics([refreshed])
            saved = pipeline.db.session.get(TopicItem, 10)

            self.assertEqual(saved.clicks, 120)
            self.assertEqual(saved.reply_count, 5)
            self.assertEqual(saved.thank_count, 4)
            self.assertEqual(saved.favorite_count, 8)
            pipeline.db.close()

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
