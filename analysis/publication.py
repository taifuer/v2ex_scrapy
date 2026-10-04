"""Local publication exclusions; raw facts and tokenizer caches are retained."""

import hashlib
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path


DEFAULT_POLICY = Path(__file__).resolve().parent / "publication_exclusions.local.json"


@dataclass(frozen=True)
class PublicationPolicy:
    users: tuple[str, ...] = ()
    topic_ids: tuple[int, ...] = ()
    comment_ids: tuple[int, ...] = ()
    restricted_topic_ids: tuple[int, ...] = ()

    @property
    def active(self) -> bool:
        return any((self.users, self.topic_ids, self.comment_ids, self.restricted_topic_ids))

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(self.__dict__, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


def load_publication_policy(path: Path | None = None) -> PublicationPolicy:
    explicit = path is not None or bool(os.environ.get("V2EX_PUBLICATION_POLICY"))
    path = path or Path(os.environ.get("V2EX_PUBLICATION_POLICY") or DEFAULT_POLICY)
    if not path.is_file():
        if explicit:
            raise ValueError(f"Publication policy not found: {path}")
        return PublicationPolicy()
    payload = json.loads(path.read_text(encoding="utf-8"))
    fields = set(PublicationPolicy.__dataclass_fields__)
    if not isinstance(payload, dict) or set(payload) - fields:
        raise ValueError("Invalid publication policy fields")
    values = {}
    for key in fields:
        entries = payload.get(key, [])
        if not isinstance(entries, list):
            raise ValueError(f"Publication policy {key} must be a list")
        if key == "users":
            if any(not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", v) for v in entries):
                raise ValueError("Invalid publication username")
            entries = [v.casefold() for v in entries]
        elif any(type(v) is not int or v <= 0 for v in entries):
            raise ValueError(f"Publication policy {key} requires positive integer IDs")
        values[key] = tuple(sorted(set(entries)))
    return PublicationPolicy(**values)


def connect_public_source(path: Path, policy: PublicationPolicy | None = None) -> sqlite3.Connection:
    policy = policy if policy is not None else load_publication_policy()
    source = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)
    if not policy.active:
        return source
    try:
        source.execute("PRAGMA temp_store = FILE")
        # TEMP views shadow the fact tables for every aggregation on this connection.
        # Materialize excluded post IDs once, retaining indexed lookups in large scans.
        source.executescript("""
            CREATE TEMP TABLE publication_users (name TEXT PRIMARY KEY COLLATE NOCASE);
            CREATE TEMP TABLE publication_topics (id INTEGER PRIMARY KEY);
            CREATE TEMP TABLE publication_comments (id INTEGER PRIMARY KEY);
        """)
        source.executemany("INSERT INTO publication_users VALUES (?)", ((v,) for v in policy.users))
        source.executemany("INSERT INTO publication_topics VALUES (?)", ((v,) for v in sorted(set(policy.topic_ids + policy.restricted_topic_ids))))
        source.executemany("INSERT INTO publication_comments VALUES (?)", ((v,) for v in policy.comment_ids))
        source.execute("""INSERT OR IGNORE INTO publication_topics
            SELECT id FROM main.topic WHERE author COLLATE NOCASE IN (SELECT name FROM publication_users)""")
        tables = {r[0] for r in source.execute("SELECT name FROM main.sqlite_master WHERE type = 'table'")}
        source.execute("""CREATE TEMP VIEW topic AS SELECT * FROM main.topic
            WHERE id NOT IN (SELECT id FROM publication_topics)""")
        if "comment" in tables:
            source.execute("""CREATE TEMP VIEW comment AS SELECT * FROM main.comment
                WHERE id NOT IN (SELECT id FROM publication_comments)
                AND topic_id NOT IN (SELECT id FROM publication_topics)
                AND commenter COLLATE NOCASE NOT IN (SELECT name FROM publication_users)""")
        if "member" in tables:
            source.execute("""CREATE TEMP VIEW member AS SELECT * FROM main.member
                WHERE username COLLATE NOCASE NOT IN (SELECT name FROM publication_users)""")
        if "topic_supplement" in tables:
            source.execute("""CREATE TEMP VIEW topic_supplement AS SELECT * FROM main.topic_supplement
                WHERE topic_id NOT IN (SELECT id FROM publication_topics)""")
        source.commit()
    except Exception:
        source.close()
        raise
    return source


def require_publication_rebuild(public_dir: Path) -> None:
    manifest_path = public_dir / "dynamic-manifest.json"
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    previous = manifest.get("publication_policy", PublicationPolicy().fingerprint)
    if previous != load_publication_policy().fingerprint:
        raise ValueError("Publication exclusions changed: run a full analytics build before partial updates or deployment")
