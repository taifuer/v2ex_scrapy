import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from analysis.publication import (
    PublicationPolicy, connect_public_source, load_publication_policy,
    require_publication_rebuild,
)
from scripts.audit_publication import audit_publication


class PublicationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "facts.sqlite"
        with sqlite3.connect(self.db) as conn:
            conn.executescript("""
                CREATE TABLE topic (id INTEGER PRIMARY KEY, author TEXT, title TEXT);
                CREATE TABLE comment (id INTEGER PRIMARY KEY, topic_id INTEGER, commenter TEXT);
                CREATE TABLE member (username TEXT);
                CREATE TABLE topic_supplement (topic_id INTEGER, content TEXT);
                INSERT INTO topic VALUES (1, 'PrivateUser', 'private'), (2, 'alice', 'visible'), (3, 'bob', 'restricted');
                INSERT INTO comment VALUES (11,1,'bob'), (12,2,'privateuser'), (13,2,'alice'), (14,2,'bob'), (15,3,'alice');
                INSERT INTO member VALUES ('PRIVATEUSER'), ('alice');
                INSERT INTO topic_supplement VALUES (1,'private note'), (2,'public note');
            """)

    def test_views_filter_all_facts_without_modifying_source(self):
        before = self.db.read_bytes()
        policy = PublicationPolicy(users=("privateuser",), comment_ids=(13,), restricted_topic_ids=(3,))
        source = connect_public_source(self.db, policy)
        self.addCleanup(source.close)
        self.assertEqual(source.execute("SELECT id FROM topic").fetchall(), [(2,)])
        self.assertEqual(source.execute("SELECT id FROM comment").fetchall(), [(14,)])
        self.assertEqual(source.execute("SELECT username FROM member").fetchall(), [("alice",)])
        self.assertEqual(source.execute("SELECT topic_id FROM topic_supplement").fetchall(), [(2,)])
        self.assertEqual(source.execute("SELECT COUNT(*) FROM main.topic").fetchone()[0], 3)
        self.assertEqual(before, self.db.read_bytes())

    def test_invalid_policy_fails_closed(self):
        path = self.root / "policy.json"
        for payload in [{"user": []}, {"users": ["x');DROP TABLE topic;"]}, {"topic_ids": [True]}, {"comment_ids": [-1]}, []]:
            path.write_text(json.dumps(payload))
            with self.assertRaises(ValueError):
                load_publication_policy(path)
        with self.assertRaises(ValueError):
            load_publication_policy(self.root / "missing.json")

    def test_policy_changes_block_partial_builds_and_audit_old_references(self):
        policy_file = self.root / "policy.json"
        policy_file.write_text(json.dumps({"users": ["PrivateUser"], "comment_ids": [13]}))
        with patch.dict(os.environ, {"V2EX_PUBLICATION_POLICY": str(policy_file)}):
            manifest = self.root / "dynamic-manifest.json"
            manifest.write_text('{}')
            with self.assertRaisesRegex(ValueError, "full analytics build"):
                require_publication_rebuild(self.root)
            manifest.write_text(json.dumps({"publication_policy": load_publication_policy().fingerprint}))
            (self.root / "dynamic-test.json").write_text(json.dumps({
                "posts": [{"id": 1, "title": "old post"}],
                "comments": [{"id": 13, "topic_id": 2}],
                "members": {"privateuser": {}},
                "rank_rows": [["year", "2025", "topics", 1, "PrivateUser", 5]],
                "text": "See @PrivateUser",
                "url": "https://www.v2ex.com/t/1#r_13",
            }))
            self.assertEqual(len(audit_publication(self.root, self.db)["violations"]), 6)

    def test_member_names_do_not_remove_same_named_topics_or_keywords(self):
        policy_file = self.root / "policy.json"
        policy_file.write_text(json.dumps({"users": ["AI"]}))
        with patch.dict(os.environ, {"V2EX_PUBLICATION_POLICY": str(policy_file)}):
            (self.root / "dynamic-manifest.json").write_text(json.dumps({"publication_policy": load_publication_policy().fingerprint}))
            (self.root / "dynamic-test.json").write_text(json.dumps({"tags": {"AI": {}}, "terms": {"AI": {}}, "title": "AI", "rows": [["2025", "AI", 10]]}))
            self.assertEqual(audit_publication(self.root, self.db)["violations"], [])

    def test_empty_policy_preserves_indexed_tables(self):
        source = connect_public_source(self.db, PublicationPolicy())
        self.addCleanup(source.close)
        self.assertEqual(source.execute("SELECT COUNT(*) FROM topic").fetchone()[0], 3)
        self.assertEqual(source.execute("SELECT COUNT(*) FROM sqlite_temp_master").fetchone()[0], 0)

    def test_deployment_rejects_missing_manifest_or_synthetic_data(self):
        with self.assertRaisesRegex(ValueError, "requires an analytics manifest"):
            audit_publication(self.root, self.db, for_deploy=True)
        (self.root / "dynamic-manifest.json").write_text(json.dumps({"dataset_kind": "synthetic"}))
        with self.assertRaisesRegex(ValueError, "must not be deployed"):
            audit_publication(self.root, self.db, for_deploy=True)
