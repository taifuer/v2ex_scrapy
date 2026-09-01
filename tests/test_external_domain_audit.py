import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.audit_external_domain_trends import (
    build_domain_report,
    canonical_domain,
    domain_category,
    extract_external_urls,
)


class ExternalDomainAuditTest(unittest.TestCase):
    def test_domain_normalization_and_internal_filtering(self):
        self.assertEqual(canonical_domain("https://gist.github.com/a/1"), "github.com")
        self.assertEqual(canonical_domain("https://mobile.twitter.com/a"), "x.com")
        self.assertEqual(
            canonical_domain("https://itunes.apple.com/cn/app/id1"),
            "apps.apple.com",
        )
        self.assertEqual(canonical_domain("https://www.zhihu.com/question/1"), "zhihu.com")
        self.assertIsNone(canonical_domain("https://www.v2ex.com/t/1"))
        self.assertIsNone(canonical_domain("http://127.0.0.1:8000/a"))
        self.assertIsNone(canonical_domain("https://CLAUDE.md"))
        self.assertIsNone(canonical_domain("https://-inc.com/job"))
        self.assertEqual(domain_category("github.com"), "code")
        self.assertEqual(domain_category("i.imgur.com"), "images")

    def test_url_extraction_deduplicates_href_and_visible_url(self):
        text = '<a href="https://github.com/a/b">https://github.com/a/b</a>'
        self.assertEqual(extract_external_urls(text), {"https://github.com/a/b"})

    def test_report_counts_topics_not_duplicate_links(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "source.sqlite"
            with sqlite3.connect(database) as conn:
                conn.execute(
                    """
                    CREATE TABLE topic (
                        id INTEGER PRIMARY KEY, author TEXT, title TEXT,
                        node TEXT, content TEXT, create_at INTEGER, clicks INTEGER
                    )
                    """
                )
                conn.executemany(
                    "INSERT INTO topic VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            1,
                            "alice",
                            "GitHub project",
                            "python",
                            "https://github.com/a/1 https://github.com/a/2",
                            1704067200,
                            10,
                        ),
                        (
                            2,
                            "bob",
                            "Another project",
                            "share",
                            '<a href="https://gist.github.com/b/2">code</a>',
                            1735689600,
                            10,
                        ),
                        (
                            3,
                            "seller",
                            "Promotion",
                            "promotions",
                            "https://github.com/spam/1",
                            1735689600,
                            10,
                        ),
                    ],
                )

            report = build_domain_report(
                database,
                "2025-12",
                minimum_topics=1,
                minimum_authors=1,
                minimum_nodes=1,
                top_limit=10,
                batch_size=1,
            )

            github = next(row for row in report["domains"] if row["domain"] == "github.com")
            self.assertEqual(github["topics"], 2)
            self.assertEqual(github["links"], 3)
            self.assertEqual(report["metadata"]["excluded_topics"], 1)
            self.assertEqual(report["top_information_domains"][0]["domain"], "github.com")
            json.dumps(report)


if __name__ == "__main__":
    unittest.main()
