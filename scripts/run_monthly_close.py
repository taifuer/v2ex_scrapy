#!/usr/bin/env python3
"""Refresh a completed month after a short maturation window."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sqlite3
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_incremental_crawl import (  # noqa: E402
    FINAL_HTTP_STATUSES,
    LOCAL_TIMEZONE,
    atomic_write_json,
    database_snapshot,
    ids_to_ranges,
    matching_crawl_runs,
    proxy_environment,
    unit_status,
)


STATE_SCHEMA = 1
DEFAULT_STATE_ROOT = ROOT / ".crawl-jobs"


@dataclass(frozen=True)
class MonthWindow:
    label: str
    start_timestamp: int
    end_timestamp: int


@dataclass(frozen=True)
class MonthSource:
    topic_ids: list[int]
    range_start_id: int
    range_end_id: int
    candidate_ids: int
    covered_ids: int
    source_max_created_at: int

    @property
    def unverified_ids(self) -> int:
        return max(0, self.candidate_ids - self.covered_ids)


def parse_month(value: str) -> MonthWindow:
    match = re.fullmatch(r"(\d{4})-(\d{2})", value)
    if match is None:
        raise argparse.ArgumentTypeError("expected YYYY-MM")
    year, month = (int(part) for part in match.groups())
    try:
        start = datetime(year, month, 1, tzinfo=LOCAL_TIMEZONE)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a valid YYYY-MM") from exc
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=LOCAL_TIMEZONE)
    else:
        end = datetime(year, month + 1, 1, tzinfo=LOCAL_TIMEZONE)
    return MonthWindow(value, int(start.timestamp()), int(end.timestamp()))


def ready_at(window: MonthWindow, grace_days: int) -> int:
    return window.end_timestamp + max(0, grace_days) * 24 * 60 * 60


def validate_maturity(
    window: MonthWindow,
    grace_days: int,
    now_timestamp: int,
    *,
    allow_early: bool,
) -> None:
    threshold = ready_at(window, grace_days)
    if allow_early or now_timestamp >= threshold:
        return
    ready = datetime.fromtimestamp(threshold, LOCAL_TIMEZONE).strftime(
        "%Y-%m-%d %H:%M:%S %Z"
    )
    raise RuntimeError(
        f"Month {window.label} is still maturing; close it after {ready}, "
        "or pass --allow-early for an intentional test."
    )


def load_month_source(database: Path, window: MonthWindow) -> MonthSource:
    with sqlite3.connect(database, timeout=60) as conn:
        bounds = conn.execute(
            """
            SELECT MIN(id), MAX(id)
            FROM topic
            WHERE create_at >= ? AND create_at < ?
            """,
            (window.start_timestamp, window.end_timestamp),
        ).fetchone()
        if bounds is None or bounds[0] is None or bounds[1] is None:
            raise RuntimeError(f"No dated topics found for {window.label}")
        range_start_id, range_end_id = (int(value) for value in bounds)
        topic_ids = [
            int(row[0])
            for row in conn.execute(
                """
                SELECT topic_id
                FROM (
                    SELECT id AS topic_id
                    FROM topic
                    WHERE id BETWEEN ? AND ?
                    UNION
                    SELECT topic_id
                    FROM topic_fetch_state
                    WHERE topic_id BETWEEN ? AND ?
                      AND last_status_code = 200
                )
                ORDER BY topic_id
                """,
                (
                    range_start_id,
                    range_end_id,
                    range_start_id,
                    range_end_id,
                ),
            )
        ]
        covered_ids = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT id AS topic_id
                    FROM topic
                    WHERE id BETWEEN ? AND ?
                    UNION
                    SELECT topic_id
                    FROM topic_fetch_state
                    WHERE topic_id BETWEEN ? AND ?
                      AND last_status_code IN (200, 404)
                )
                """,
                (
                    range_start_id,
                    range_end_id,
                    range_start_id,
                    range_end_id,
                ),
            ).fetchone()[0]
        )
        source_max_created_at = int(
            conn.execute(
                """
                SELECT COALESCE(MAX(create_at), 0)
                FROM topic
                WHERE create_at > 0
                """
            ).fetchone()[0]
        )
    return MonthSource(
        topic_ids=topic_ids,
        range_start_id=range_start_id,
        range_end_id=range_end_id,
        candidate_ids=range_end_id - range_start_id + 1,
        covered_ids=covered_ids,
        source_max_created_at=source_max_created_at,
    )


def validate_source_coverage(
    source: MonthSource,
    window: MonthWindow,
    *,
    allow_incomplete: bool,
) -> None:
    problems = []
    if source.source_max_created_at < window.end_timestamp:
        problems.append("the source database has not advanced beyond the month boundary")
    if source.unverified_ids:
        problems.append(
            f"{source.unverified_ids:,} IDs in the month range have neither a topic row "
            "nor a final 200/404 state"
        )
    if problems and not allow_incomplete:
        raise RuntimeError("; ".join(problems) + ". Run the incremental crawl first.")


def month_snapshot(database: Path, window: MonthWindow) -> dict[str, int]:
    with sqlite3.connect(database, timeout=60) as conn:
        topic = conn.execute(
            """
            SELECT COUNT(*),
                   COALESCE(SUM(CASE WHEN reply_count >= 0 THEN reply_count ELSE 0 END), 0),
                   COALESCE(SUM(CASE WHEN clicks >= 0 THEN clicks ELSE 0 END), 0),
                   COALESCE(SUM(CASE WHEN favorite_count >= 0 THEN favorite_count ELSE 0 END), 0),
                   COALESCE(SUM(CASE WHEN thank_count >= 0 THEN thank_count ELSE 0 END), 0),
                   COALESCE(SUM(CASE WHEN votes >= 0 THEN votes ELSE 0 END), 0)
            FROM topic
            WHERE clicks >= 0 AND create_at >= ? AND create_at < ?
            """,
            (window.start_timestamp, window.end_timestamp),
        ).fetchone()
        comments = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM comment
                WHERE topic_id IN (
                    SELECT id FROM topic
                    WHERE clicks >= 0 AND create_at >= ? AND create_at < ?
                )
                """,
                (window.start_timestamp, window.end_timestamp),
            ).fetchone()[0]
        )
    return {
        "topics": int(topic[0]),
        "reply_snapshot": int(topic[1]),
        "clicks": int(topic[2]),
        "favorites": int(topic[3]),
        "topic_thanks": int(topic[4]),
        "votes": int(topic[5]),
        "comments": comments,
    }


def close_scrapy_command(plan: dict, args) -> list[str]:
    return [
        str(ROOT / ".venv" / "bin" / "scrapy"),
        "crawl",
        "v2ex",
        "-a",
        f"topic_ids_file={plan['topic_ids_file']}",
        "-a",
        "force_update=true",
        "-a",
        "crawl_members=false",
        "-a",
        f"crawl_purpose={plan['crawl_purpose']}",
        "-s",
        f"LOG_LEVEL={args.log_level}",
        "-s",
        f"CONCURRENT_REQUESTS={args.concurrency}",
        "-s",
        f"CONCURRENT_REQUESTS_PER_DOMAIN={args.concurrency}",
        "-s",
        f"DOWNLOAD_DELAY={args.delay}",
        "-s",
        f"AUTOTHROTTLE_ENABLED={'true' if args.auto_throttle else 'false'}",
    ]


def close_systemd_command(
    plan: dict,
    args,
    command: list[str],
    environment: dict[str, str],
) -> list[str]:
    result = [
        "systemd-run",
        f"--unit={plan['unit']}",
        "--collect",
        f"--description=V2EX monthly close for {plan['month']}",
        f"--property=WorkingDirectory={ROOT}",
        f"--setenv=V2EX_COOKIES_FILE={args.cookie_file.resolve()}",
        f"--setenv=V2EX_JOBDIR={plan['job_dir']}",
    ]
    result.extend(f"--setenv={name}={value}" for name, value in environment.items())
    return [*result, *command]


def load_plan(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"Monthly close plan not found: {path}")
    plan = json.loads(path.read_text(encoding="utf-8"))
    if plan.get("schema") != STATE_SCHEMA:
        raise SystemExit(f"Unsupported monthly close schema: {plan.get('schema')}")
    return plan


def selected_topic_ids(plan: dict) -> list[int]:
    raw = Path(plan["topic_ids_file"]).read_text(encoding="utf-8").strip()
    if not raw:
        return []
    ids = []
    for part in raw.split(","):
        start, separator, end = part.partition("-")
        first = int(start)
        last = int(end) if separator else first
        ids.extend(range(first, last + 1))
    return ids


def close_status(database: Path, plan: dict) -> dict:
    selected = selected_topic_ids(plan)
    selected_set = set(selected)
    if not selected:
        fetches = {}
        valid_topics = set()
    else:
        with sqlite3.connect(database, timeout=60) as conn:
            rows = conn.execute(
                """
                SELECT topic_id, last_status_code, last_fetched_at
                FROM topic_fetch_state
                WHERE topic_id BETWEEN ? AND ?
                """,
                (selected[0], selected[-1]),
            ).fetchall()
            valid_topics = {
                int(row[0])
                for row in conn.execute(
                    """
                    SELECT id
                    FROM topic
                    WHERE id BETWEEN ? AND ?
                      AND create_at > 0
                      AND title != ''
                      AND author != ''
                      AND node != ''
                      AND clicks >= 0
                      AND reply_count >= 0
                      AND favorite_count >= 0
                      AND thank_count >= 0
                      AND votes >= 0
                    """,
                    (selected[0], selected[-1]),
                )
                if int(row[0]) in selected_set
            }
        fetches = {
            int(topic_id): (int(status), int(fetched_at))
            for topic_id, status, fetched_at in rows
            if int(topic_id) in selected_set
        }
    fresh = {
        topic_id: status
        for topic_id, (status, fetched_at) in fetches.items()
        if fetched_at >= int(plan["created_at"])
    }
    status_counts: dict[str, int] = {}
    for status in fresh.values():
        status_counts[str(status)] = status_counts.get(str(status), 0) + 1
    return {
        "selected": len(selected),
        "fresh": len(fresh),
        "refreshed": sum(
            1
            for topic_id, status in fresh.items()
            if status == 200 and topic_id in valid_topics
        ),
        "remaining": max(0, len(selected) - len(fresh)),
        "status_counts": status_counts,
        "retry_ids": sorted(
            topic_id
            for topic_id in selected
            if topic_id not in fresh
            or fresh[topic_id] not in FINAL_HTTP_STATUSES
            or (fresh[topic_id] == 200 and topic_id not in valid_topics)
        ),
        "inaccessible_ids": sorted(
            topic_id for topic_id, status in fresh.items() if status == 404
        ),
        "unit_state": unit_status(plan.get("unit")),
        "runs": matching_crawl_runs(
            database, str(plan["crawl_purpose"]), int(plan["created_at"])
        ),
    }


def close_report(database: Path, plan: dict) -> dict:
    window = MonthWindow(
        plan["month"], int(plan["start_timestamp"]), int(plan["end_timestamp"])
    )
    status = close_status(database, plan)
    current = month_snapshot(database, window)
    baseline = plan["baseline_month"]
    return {
        "month": plan["month"],
        "unit": {"name": plan.get("unit"), "state": status["unit_state"]},
        "selected_topics": status["selected"],
        "attempted_topics": status["fresh"],
        "refreshed_topics": status["refreshed"],
        "remaining_topics": status["remaining"],
        "status_counts": status["status_counts"],
        "retry_ids": status["retry_ids"],
        "inaccessible_ids": status["inaccessible_ids"],
        "before": baseline,
        "after": current,
        "deltas": {
            key: int(current[key]) - int(baseline[key]) for key in current
        },
        "runs": status["runs"],
    }


def write_report(state_dir: Path, report: dict) -> None:
    atomic_write_json(state_dir / "report.json", report)
    retry_ids = report["retry_ids"]
    (state_dir / "retry-topic-ids.txt").write_text(
        ids_to_ranges(retry_ids) + ("\n" if retry_ids else ""), encoding="utf-8"
    )


def print_status(plan: dict, status: dict) -> None:
    selected = int(status["selected"])
    progress = 100.0 * int(status["fresh"]) / max(1, selected)
    print(
        f"Monthly close {plan['month']}: {status['unit_state']}; "
        f"{status['fresh']:,}/{selected:,} topics attempted ({progress:.1f}%), "
        f"{status['refreshed']:,} refreshed, {status['remaining']:,} not attempted."
    )
    print(f"HTTP statuses: {status['status_counts'] or '{}'}")
    if status["runs"]:
        latest = status["runs"][-1]
        print(
            f"Latest run #{latest['id']}: {latest['close_reason']}, "
            f"{latest['response_count']:,} responses, {latest['error_count']:,} errors."
        )


def print_report(state_dir: Path, report: dict) -> None:
    print(
        f"Monthly close report {report['month']}: "
        f"{report['attempted_topics']:,}/{report['selected_topics']:,} attempted, "
        f"{report['refreshed_topics']:,} refreshed, "
        f"{len(report['retry_ids']):,} retry, "
        f"{len(report['inaccessible_ids']):,} inaccessible."
    )
    delta = report["deltas"]
    print(
        "Changes: "
        f"{delta['comments']:+,} comments, {delta['clicks']:+,} clicks, "
        f"{delta['favorites']:+,} favorites, "
        f"{delta['topic_thanks']:+,} topic thanks, {delta['votes']:+,} votes."
    )
    print(f"Report written to {state_dir / 'report.json'}")
    if report["retry_ids"]:
        print(f"Retry IDs written to {state_dir / 'retry-topic-ids.txt'}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Refresh a completed V2EX month after a maturation window."
    )
    parser.add_argument(
        "action", nargs="?", choices=("start", "status", "report"), default="start"
    )
    parser.add_argument("--month", required=True, type=parse_month)
    parser.add_argument("--grace-days", type=int, default=7)
    parser.add_argument("--allow-early", action="store_true")
    parser.add_argument("--allow-incomplete-source", action="store_true")
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--auto-throttle", action="store_true")
    parser.add_argument("--foreground", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--refresh-plan", action="store_true")
    parser.add_argument("--proxy")
    parser.add_argument(
        "--cookie-file",
        type=Path,
        default=Path(os.environ["V2EX_COOKIES_FILE"])
        if os.environ.get("V2EX_COOKIES_FILE")
        else None,
    )
    parser.add_argument("--state-root", type=Path, default=DEFAULT_STATE_ROOT)
    parser.add_argument(
        "--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default="INFO"
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    window = args.month
    args.concurrency = max(1, args.concurrency)
    args.delay = max(0.0, args.delay)
    args.grace_days = max(0, args.grace_days)
    database = ROOT / "v2ex.sqlite"
    state_dir = args.state_root.resolve() / f"month-close-{window.label}"
    plan_path = state_dir / "plan.json"

    if args.action in {"status", "report"}:
        plan = load_plan(plan_path)
        if args.action == "status":
            print_status(plan, close_status(database, plan))
            return
        report = close_report(database, plan)
        write_report(state_dir, report)
        print_report(state_dir, report)
        return

    if plan_path.exists() and not args.refresh_plan:
        plan = load_plan(plan_path)
        print(f"Reusing monthly close plan: {plan_path}")
    else:
        if plan_path.exists():
            previous = load_plan(plan_path)
            if unit_status(previous.get("unit")) in {"active", "activating"}:
                raise SystemExit(
                    f"Monthly close unit is still active: {previous.get('unit')}.service"
                )
        now_timestamp = int(time.time())
        try:
            validate_maturity(
                window,
                args.grace_days,
                now_timestamp,
                allow_early=args.allow_early,
            )
            source = load_month_source(database, window)
            validate_source_coverage(
                source, window, allow_incomplete=args.allow_incomplete_source
            )
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc
        state_dir.mkdir(parents=True, exist_ok=True)
        topic_ids_file = state_dir / "topic-ids.txt"
        topic_ids_file.write_text(
            ids_to_ranges(source.topic_ids) + "\n", encoding="utf-8"
        )
        created_at = int(time.time())
        plan = {
            "schema": STATE_SCHEMA,
            "month": window.label,
            "start_timestamp": window.start_timestamp,
            "end_timestamp": window.end_timestamp,
            "grace_days": args.grace_days,
            "created_at": created_at,
            "source": {
                key: value
                for key, value in asdict(source).items()
                if key != "topic_ids"
            },
            "selected_topics": len(source.topic_ids),
            "topic_ids_file": str(topic_ids_file),
            "baseline_database": database_snapshot(database),
            "baseline_month": month_snapshot(database, window),
            "crawl_purpose": f"month-close-{window.label}",
            "job_dir": str(state_dir / "scrapy"),
            "unit": f"v2ex-month-close-{window.label.replace('-', '')}-{created_at}",
        }
        atomic_write_json(plan_path, plan)
        print(
            f"Planned {len(source.topic_ids):,} topics for refresh in {window.label}; "
            f"ID range {source.range_start_id}..{source.range_end_id}."
        )

    if args.dry_run:
        print(f"Plan written to {plan_path}")
        return
    if args.cookie_file is None or not args.cookie_file.is_file():
        raise SystemExit("Set V2EX_COOKIES_FILE or pass --cookie-file.")
    if unit_status(plan.get("unit")) in {"active", "activating"}:
        print_status(plan, close_status(database, plan))
        print(f"Monthly close unit is already active: {plan['unit']}.service")
        return

    command = close_scrapy_command(plan, args)
    environment = os.environ.copy()
    environment.update(proxy_environment(args.proxy))
    environment["V2EX_COOKIES_FILE"] = str(args.cookie_file.resolve())
    environment["V2EX_JOBDIR"] = str(plan["job_dir"])
    if args.foreground:
        print(f"Starting foreground monthly close: {shlex.join(command)}")
        subprocess.run(command, cwd=ROOT, env=environment, check=True)
        report = close_report(database, plan)
        write_report(state_dir, report)
        print_report(state_dir, report)
        return

    launch = close_systemd_command(
        plan, args, command, proxy_environment(args.proxy)
    )
    subprocess.run(launch, cwd=ROOT, check=True)
    print(f"Started {plan['unit']}.service")
    print(
        "Status: "
        + shlex.join(
            [
                str(ROOT / ".venv" / "bin" / "python"),
                str(Path(__file__)),
                "status",
                "--month",
                plan["month"],
            ]
        )
    )


if __name__ == "__main__":
    main()
