import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.sample_title_keyword_gold import (
    append_approved,
    period_band,
    sample_real_titles,
    title_style,
)


class TitleGoldSamplingTest(unittest.TestCase):
    def test_title_style_distinguishes_common_risk_shapes(self):
        self.assertEqual(title_style("短标题"), "short")
        self.assertEqual(title_style("这是一个包含 React 和 Vue 的中文标题"), "mixed")
        self.assertEqual(title_style("An English title about Python tooling"), "latin")
        self.assertEqual(title_style("这是一个长度适中的纯中文标题内容"), "chinese")
        self.assertEqual(title_style("很长的标题" * 12), "long")
        self.assertEqual(period_band("2016-03"), "2015-2019")

    def test_sampling_is_deterministic_and_excludes_existing_titles(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "source.sqlite"
            with sqlite3.connect(database) as conn:
                conn.execute(
                    """
                    CREATE TABLE topic (
                        id INTEGER PRIMARY KEY, title TEXT, node TEXT,
                        create_at INTEGER, clicks INTEGER
                    )
                    """
                )
                rows = []
                for topic_id in range(1, 61):
                    year = 2010 + topic_id % 16
                    title = f"第 {topic_id} 个 React 中文测试标题"
                    rows.append(
                        (
                            topic_id,
                            title,
                            "programmer",
                            1262304000 + (year - 2010) * 31_536_000,
                            10,
                        )
                    )
                conn.executemany("INSERT INTO topic VALUES (?, ?, ?, ?, ?)", rows)

            first = sample_real_titles(database, {rows[0][1]}, 20, 42, batch_size=7)
            second = sample_real_titles(database, {rows[0][1]}, 20, 42, batch_size=7)

            self.assertEqual(first, second)
            self.assertEqual(len(first), 20)
            self.assertNotIn(rows[0][1], {row["title"] for row in first})

    def test_apply_only_appends_explicitly_approved_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gold = root / "gold.jsonl"
            review = root / "review.jsonl"
            gold.write_text(
                json.dumps(
                    {
                        "id": "existing",
                        "category": "test",
                        "title": "existing title",
                        "expected": [],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            review.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "review_status": "pending",
                                "topic_id": 10,
                                "stratum": "2024-latest/mixed",
                                "title": "pending title",
                                "expected": ["AI"],
                            }
                        ),
                        json.dumps(
                            {
                                "review_status": "approved",
                                "topic_id": 11,
                                "period": "2026-07",
                                "node": "ai",
                                "stratum": "2024-latest/mixed",
                                "title": "approved AI title",
                                "expected": ["AI", "AI"],
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            appended = append_approved(review, gold)

            self.assertEqual(appended, 1)
            rows = [json.loads(line) for line in gold.read_text().splitlines()]
            self.assertEqual(rows[-1]["id"], "real-11")
            self.assertEqual(rows[-1]["expected"], ["AI"])


if __name__ == "__main__":
    unittest.main()
