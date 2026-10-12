#!/usr/bin/env python3
"""Read-only coverage and sensitivity audit; never changes public aggregates."""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from analysis.build_analytics import EXCLUDED_THANK_USERS, MIN_VALID_CREATE_AT


def interaction_impact(conn, excluded_users=EXCLUDED_THANK_USERS) -> dict:
    users = sorted(excluded_users)
    placeholders = ",".join("?" for _ in users) or "NULL"
    result = {"excluded_users": users, "unknown_values": "Unknown values are not estimates of zero; sums below include only known nonnegative values."}
    for key, table, author, metric, predicate in (
        ("topic_thanks", "topic", "author", "thank_count", "clicks >= 0"),
        ("topic_favorites", "topic", "author", "favorite_count", "clicks >= 0"),
        ("comment_thanks", "comment", "commenter", "thank_count", "1"),
    ):
        rows = []
        for period, count, known, total, excluded in conn.execute(f"""
            SELECT strftime('%Y-%m', create_at, 'unixepoch', '+8 hours'), COUNT(*),
                   SUM({metric} >= 0), SUM(MAX(0, {metric})),
                   SUM(CASE WHEN LOWER({author}) IN ({placeholders}) THEN MAX(0, {metric}) ELSE 0 END)
            FROM {table} WHERE create_at >= ? AND {predicate} GROUP BY 1 ORDER BY 1
        """, (*users, MIN_VALID_CREATE_AT)):
            rows.append({"period": period, "records": count, "known": known, "unknown": count-known,
                         "raw_sum": total, "without_confirmed_users": total-excluded,
                         "excluded_share_percent": round(100 * excluded / total, 4) if total else 0})
        count = sum(row["records"] for row in rows)
        known = sum(row["known"] for row in rows)
        raw = sum(row["raw_sum"] for row in rows)
        clean = sum(row["without_confirmed_users"] for row in rows)
        result[key] = {"records": count, "known": known, "unknown": count-known,
                       "known_percent": round(100 * known / count, 4) if count else None,
                       "raw_sum": raw, "without_confirmed_users": clean,
                       "excluded_share_percent": round(100 * (raw-clean) / raw, 4) if raw else 0,
                       "months": rows}
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "v2ex.sqlite")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with sqlite3.connect(f"{args.database.resolve().as_uri()}?mode=ro", uri=True) as conn:
        report = interaction_impact(conn)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: {k: v for k, v in value.items() if k != "months"} if isinstance(value, dict) else value
                      for key, value in report.items()}, ensure_ascii=False, indent=2))
