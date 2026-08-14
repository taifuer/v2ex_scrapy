import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from v2ex_scrapy.DB import DB
from v2ex_scrapy.items import CrawlRunItem, TopicFetchState
from v2ex_scrapy.middlewares import SaveHttpStatusToDBMiddleware


class FetchTrackingTest(unittest.TestCase):
    def test_selected_topic_configuration_uses_actual_bounds(self):
        middleware = SaveHttpStatusToDBMiddleware.__new__(
            SaveHttpStatusToDBMiddleware
        )
        configuration = middleware.crawl_configuration(
            SimpleNamespace(
                start_id=1,
                end_id=1_000_000,
                force_update_topic=True,
                topic_ids=[1_100_000, 1_200_000],
            )
        )

        self.assertNotIn("start_id", configuration)
        self.assertNotIn("end_id", configuration)
        self.assertEqual(configuration["selected_topic_count"], 2)
        self.assertEqual(configuration["selected_topic_min"], 1_100_000)
        self.assertEqual(configuration["selected_topic_max"], 1_200_000)

    def test_records_topic_fetch_attempts_and_crawl_run(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "test.sqlite"
            db = DB(str(database))
            run_id = db.start_crawl_run(
                spider="v2ex",
                started_at=100,
                configuration=json.dumps({"start_id": 1}),
            )
            db.record_topic_fetch(10, 200, 101, "https://www.v2ex.com/t/10")
            db.record_topic_fetch(10, 403, 102, "https://www.v2ex.com/t/10")
            db.update_crawl_run_progress(run_id, 2, 1)
            db.session.commit()
            db.session.expire_all()
            active_run = db.session.get(CrawlRunItem, run_id)
            self.assertEqual(active_run.response_count, 2)
            self.assertEqual(active_run.error_count, 1)
            db.finish_crawl_run(run_id, 103, "finished", 2, 0)

            state = db.session.get(TopicFetchState, 10)
            self.assertIsNotNone(state)
            self.assertEqual(state.attempt_count, 2)
            self.assertEqual(state.last_status_code, 403)
            self.assertEqual(state.last_fetched_at, 102)

            run = db.session.get(CrawlRunItem, run_id)
            self.assertIsNotNone(run)
            self.assertEqual(run.close_reason, "finished")
            self.assertEqual(run.response_count, 2)
            self.assertEqual(run.error_count, 0)
            db.close()

    def test_new_run_only_interrupts_stale_unfinished_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "test.sqlite"
            db = DB(str(database))
            stale_id = db.start_crawl_run("v2ex", 100)
            recent_id = db.start_crawl_run(
                "v2ex", 100 + DB.CRAWL_RUN_STALE_SECONDS - 1
            )
            db.start_crawl_run("v2ex", 100 + DB.CRAWL_RUN_STALE_SECONDS + 1)

            stale = db.session.get(CrawlRunItem, stale_id)
            recent = db.session.get(CrawlRunItem, recent_id)
            self.assertEqual(stale.close_reason, "interrupted")
            self.assertIsNotNone(stale.finished_at)
            self.assertEqual(recent.close_reason, "running")
            self.assertIsNone(recent.finished_at)
            db.close()


if __name__ == "__main__":
    unittest.main()
