import sqlite3
import unittest

from scripts.audit_interaction_impact import interaction_impact


class InteractionImpactTest(unittest.TestCase):
    def test_unknown_values_and_flagged_users_remain_separate(self):
        with sqlite3.connect(":memory:") as conn:
            conn.executescript("""
                CREATE TABLE topic (author TEXT, create_at INTEGER, clicks INTEGER, thank_count INTEGER, favorite_count INTEGER);
                CREATE TABLE comment (commenter TEXT, create_at INTEGER, thank_count INTEGER);
                INSERT INTO topic VALUES ('alice', 1700000000, 10, -1, 0), ('usdc', 1700000000, 10, 4, 3);
                INSERT INTO comment VALUES ('USDC', 1700000000, 100), ('alice', 1700000000, 20);
            """)
            report = interaction_impact(conn)
        self.assertEqual(report["topic_thanks"]["known"], 1)
        self.assertEqual(report["topic_thanks"]["unknown"], 1)
        self.assertEqual(report["topic_favorites"]["known"], 2)
        self.assertEqual(report["comment_thanks"]["raw_sum"], 120)
        self.assertEqual(report["comment_thanks"]["without_confirmed_users"], 20)
