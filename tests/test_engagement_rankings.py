import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from analysis import build_analytics as builder
from analysis.builders.rankings import engagement_score


class EngagementRankingsTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.database = self.root / "source.sqlite"
        self.output = self.root / "dynamic-engagement.json"
        self.output.write_text(json.dumps({"rows": [["2026-10", 9]]}))
        with sqlite3.connect(self.database) as conn:
            conn.executescript("""
                CREATE TABLE topic (
                    id INTEGER PRIMARY KEY, author TEXT, title TEXT, node TEXT,
                    tag TEXT, create_at INTEGER, clicks INTEGER, reply_count INTEGER,
                    favorite_count INTEGER, thank_count INTEGER, votes INTEGER
                );
                CREATE TABLE comment (
                    id INTEGER PRIMARY KEY, topic_id INTEGER, commenter TEXT,
                    thank_count INTEGER, no INTEGER, content TEXT, create_at INTEGER
                );
            """)
            for topic_id, replies, favorites, thanks, votes, clicks in (
                (1, 0, 1000, 0, 0, 0),
                (2, 0, 0, 600, 0, 0),
                (3, 0, 0, 0, 1500, 0),
                (4, 0, 0, 0, 0, 1_000_000_000),
                (5, 1000, 900, 500, 1000, 100),
                (6, 1000, 900, 500, 1000, 100),
                (7, 10000, 10000, 10000, 10000, -1),
                (8, 10000, 10000, 10000, 10000, 10000),
                (9, -1, -1, -1, -1, 0),
            ):
                conn.execute("INSERT INTO topic VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                    topic_id, "alice", f"Post {topic_id}", "promotions" if topic_id == 6 else "python",
                    "[]", 0 if topic_id == 8 else 1790784000,
                    clicks, replies, favorites, thanks, votes,
                ))

    def update(self, limit):
        with (
            patch.object(builder, "SOURCE_DB", self.database),
            patch.object(builder, "PUBLIC_DIR", self.root),
            patch.object(builder, "write_manifest") as manifest,
        ):
            builder.update_engagement_rankings(post_limit=limit)
        manifest.assert_called_once_with("engagement")
        return json.loads(self.output.read_text())

    def test_composite_winner_is_not_limited_to_single_metric_winners(self):
        output = self.update(1)
        posts = output["top_posts"]
        self.assertEqual(set(posts), set(builder.INTERACTION_POST_METRICS))
        self.assertEqual(posts["score"][0]["id"], 6)
        self.assertEqual(posts["score"][0]["value"], engagement_score(posts["score"][0]))
        self.assertEqual(
            {metric: posts[metric][0]["id"] for metric in ("favorite_count", "thank_count", "votes", "clicks")},
            {"favorite_count": 1, "thank_count": 2, "votes": 3, "clicks": 4},
        )
        self.assertEqual(output["rows"], [["2026-10", 9]])

    def test_composite_ranking_keeps_ties_and_unknown_values_consistent(self):
        posts = self.update(20)["top_posts"]["score"]
        self.assertEqual(len(posts), 7)
        self.assertEqual([post["id"] for post in posts[:2]], [6, 5])
        self.assertFalse({7, 8} & {post["id"] for post in posts})
        self.assertEqual(posts[-1]["id"], 9)
        self.assertEqual(posts[-1]["value"], 0)
        self.assertEqual(posts[-1]["thank_count"], -1)
        for post in posts:
            self.assertEqual(post["value"], engagement_score(post))


if __name__ == "__main__":
    unittest.main()
