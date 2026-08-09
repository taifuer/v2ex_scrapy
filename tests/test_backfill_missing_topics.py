import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.backfill_missing_topics import (
    find_interaction_issue_ids,
    ids_to_ranges,
)


class BackfillMissingTopicsTest(unittest.TestCase):
    def test_ids_to_ranges_collapses_consecutive_ids(self):
        self.assertEqual(
            ids_to_ranges([1, 2, 3, 6, 8, 9]),
            [(1, 3), (6, 6), (8, 9)],
        )

    def test_interaction_mode_selects_only_valid_unknown_topics(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "test.sqlite"
            with sqlite3.connect(database) as conn:
                conn.execute(
                    """
                    CREATE TABLE topic (
                        id INTEGER PRIMARY KEY,
                        clicks INTEGER NOT NULL,
                        favorite_count INTEGER NOT NULL,
                        thank_count INTEGER NOT NULL
                    )
                    """
                )
                conn.executemany(
                    "INSERT INTO topic VALUES (?, ?, ?, ?)",
                    [
                        (1, 10, -1, -1),
                        (2, 20, 3, -1),
                        (3, 30, 3, 2),
                        (4, -1, -1, -1),
                        (5, 40, -1, 0),
                    ],
                )

            self.assertEqual(
                find_interaction_issue_ids(database, end_id=5),
                [(1, 2), (5, 5)],
            )


if __name__ == "__main__":
    unittest.main()
