import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.audit_title_keyword_candidates import collect_candidates


LOCAL_TIMEZONE = timezone(timedelta(hours=8))


def timestamp(period: str) -> int:
    return int(
        datetime.strptime(f"{period}-15", "%Y-%m-%d")
        .replace(tzinfo=LOCAL_TIMEZONE)
        .timestamp()
    )


class KeywordCandidateAuditTests(unittest.TestCase):
    def test_candidate_metrics_cover_change_concentration_and_overlap(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "source.sqlite"
            cache_path = Path(temp_dir) / "tokens.sqlite"
            source = sqlite3.connect(source_path)
            source.execute(
                """
                CREATE TABLE topic (
                    id INTEGER PRIMARY KEY,
                    author TEXT,
                    title TEXT,
                    node TEXT,
                    create_at INTEGER,
                    clicks INTEGER
                )
                """
            )
            source.executemany(
                "INSERT INTO topic VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (1, "alice", "current one", "n1", timestamp("2026-07"), 1),
                    (2, "bob", "current two", "n2", timestamp("2026-06"), 1),
                    (3, "carol", "previous", "n3", timestamp("2025-07"), 1),
                    (4, "dave", "denominator", "n4", timestamp("2026-05"), 1),
                ],
            )
            source.commit()
            source.close()

            cache = sqlite3.connect(cache_path)
            cache.execute(
                "CREATE TABLE title_tokens (topic_id INTEGER PRIMARY KEY, tokens TEXT)"
            )
            cache.executemany(
                "INSERT INTO title_tokens VALUES (?, ?)",
                [
                    (1, json.dumps(["候选", "AI"])),
                    (2, json.dumps(["候选", "AI"])),
                    (3, json.dumps(["候选", "Python"])),
                    (4, json.dumps(["AI"])),
                ],
            )
            cache.commit()
            cache.close()

            rows = collect_candidates(
                source_path,
                cache_path,
                {"AI", "Python"},
                {"候选"},
                "2026-07",
                min_count=3,
                min_authors=3,
                min_nodes=3,
                limit=10,
            )

        self.assertEqual(len(rows), 1)
        candidate = rows[0]
        self.assertEqual(candidate["term"], "候选")
        self.assertEqual(candidate["recent_12m"], 2)
        self.assertEqual(candidate["previous_12m"], 1)
        self.assertEqual(candidate["active_periods"], 3)
        self.assertEqual(candidate["peak_period"], "2026-07")
        self.assertEqual(candidate["peak_count"], 1)
        self.assertEqual(candidate["top_author_share"], 0.3333)
        self.assertEqual(candidate["top_node_share"], 0.3333)
        self.assertEqual(candidate["closest_indexed_term"], "AI")
        self.assertEqual(candidate["closest_indexed_overlap"], 0.6667)
        self.assertEqual(candidate["recent_share_per_10k"], 6666.667)
        self.assertEqual(candidate["previous_share_per_10k"], 10000.0)
        self.assertTrue(candidate["configured"])


if __name__ == "__main__":
    unittest.main()
