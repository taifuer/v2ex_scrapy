import sqlite3
import unittest

from v2ex_scrapy.change_tracking import ensure_change_tracking


class ChangeTrackingTest(unittest.TestCase):
    def setUp(self):
        self.source = sqlite3.connect(":memory:")
        self.source.executescript(
            """
            CREATE TABLE topic (
                id INTEGER PRIMARY KEY, author TEXT, title TEXT, content TEXT,
                node TEXT, tag TEXT, create_at INTEGER, clicks INTEGER,
                reply_count INTEGER, favorite_count INTEGER,
                thank_count INTEGER, votes INTEGER
            );
            CREATE TABLE comment (
                id INTEGER PRIMARY KEY, topic_id INTEGER, commenter TEXT,
                content TEXT, thank_count INTEGER, create_at INTEGER, no INTEGER
            );
            CREATE TABLE member (
                uid INTEGER, username TEXT, avatar_url TEXT, create_at INTEGER,
                social_link TEXT, PRIMARY KEY (uid, username)
            );
            CREATE TABLE log (
                id INTEGER PRIMARY KEY, url TEXT, status_code INTEGER, create_at INTEGER
            );
            """
        )

    def tearDown(self):
        self.source.close()

    def test_tracks_only_analysis_relevant_changes(self):
        initial = ensure_change_tracking(self.source)
        self.source.execute("INSERT INTO log VALUES (1, '/t/1', 200, 1704067200)")
        self.source.execute(
            "INSERT INTO topic VALUES (1, '', '', '', '', '[]', 0, -1, -1, -1, -1, -1)"
        )
        self.source.commit()
        after_ignored = ensure_change_tracking(self.source)

        self.assertEqual(initial, after_ignored)

        self.source.execute(
            """
            INSERT INTO topic VALUES
            (2, 'alice', 'AI 工具', 'body', 'qna', '[]', 1704067200, 10, 1, 2, 3, 4)
            """
        )
        self.source.commit()
        after_insert = ensure_change_tracking(self.source)
        self.assertEqual(after_insert["topic"]["count"], 1)
        self.assertEqual(
            after_insert["topic"]["revision"], initial["topic"]["revision"] + 1
        )

        self.source.execute("UPDATE topic SET content = 'new body' WHERE id = 2")
        self.source.execute("UPDATE topic SET title = title WHERE id = 2")
        self.source.commit()
        after_irrelevant_update = ensure_change_tracking(self.source)
        self.assertEqual(after_insert, after_irrelevant_update)

        self.source.execute("UPDATE topic SET title = 'Claude 工具' WHERE id = 2")
        self.source.commit()
        after_title = ensure_change_tracking(self.source)
        self.assertEqual(
            after_title["topic"]["revision"], after_insert["topic"]["revision"] + 1
        )

        self.source.execute("DELETE FROM topic WHERE id = 2")
        self.source.commit()
        after_delete = ensure_change_tracking(self.source)
        self.assertEqual(after_delete["topic"]["count"], 0)
        self.assertEqual(after_delete["topic"]["max_id"], 0)
        self.assertEqual(after_delete["topic"]["max_create_at"], 0)


if __name__ == "__main__":
    unittest.main()
