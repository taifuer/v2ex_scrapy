#!/usr/bin/env python3
"""Plan, launch, and verify a date-bounded incremental V2EX crawl."""

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
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import date, datetime, time as datetime_time, timedelta
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from parsel import Selector
from scrapy.http import HtmlResponse

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v2ex_scrapy.settings import DEFAULT_USER_AGENT
from v2ex_scrapy.v2ex_parser import parse_topic

LOCAL_TIMEZONE = ZoneInfo("Asia/Shanghai")
STATE_SCHEMA = 1
DEFAULT_STATE_ROOT = ROOT / ".crawl-jobs"
FINAL_HTTP_STATUSES = {200, 404}


@dataclass(frozen=True)
class TopicProbe:
    topic_id: int
    status_code: int
    created_at: int = 0
    title: str = ""

    @property
    def has_timestamp(self) -> bool:
        return self.status_code == 200 and self.created_at > 0


class V2EXProbeClient:
    def __init__(
        self,
        cookie: str,
        *,
        delay: float = 1.0,
        timeout: float = 30.0,
        opener=None,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.cookie = cookie
        self.delay = max(0.0, delay)
        self.timeout = max(1.0, timeout)
        self.opener = opener or urllib.request.build_opener()
        self.sleeper = sleeper
        self.last_request_at = 0.0
        self.cache: dict[int, TopicProbe] = {}

    def _request(self, url: str) -> tuple[int, bytes]:
        elapsed = time.monotonic() - self.last_request_at
        if self.last_request_at and elapsed < self.delay:
            self.sleeper(self.delay - elapsed)
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Cookie": self.cookie,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "From": "taifu@taifua.com",
            },
        )
        try:
            response = self.opener.open(request, timeout=self.timeout)
            body = response.read()
            return int(response.status), body
        except urllib.error.HTTPError as exc:
            return int(exc.code), exc.read()
        finally:
            self.last_request_at = time.monotonic()

    def recent_max_id(self) -> int:
        status, body = self._request("https://www.v2ex.com/recent")
        if status != 200:
            raise RuntimeError(f"V2EX recent page returned HTTP {status}")
        selector = Selector(body.decode("utf-8", errors="replace"))
        topic_ids = []
        for href in selector.css("a[href^='/t/']::attr(href)").getall():
            match = re.search(r"/t/(\d+)", href)
            if match:
                topic_ids.append(int(match.group(1)))
        if not topic_ids:
            raise RuntimeError("No topic IDs found on the V2EX recent page")
        return max(topic_ids)

    def fetch_topic(self, topic_id: int) -> TopicProbe:
        if topic_id in self.cache:
            return self.cache[topic_id]
        status, body = self._request(f"https://www.v2ex.com/t/{topic_id}")
        created_at = 0
        title = ""
        if status == 200:
            response = HtmlResponse(
                url=f"https://www.v2ex.com/t/{topic_id}",
                status=status,
                body=body,
                encoding="utf-8",
            )
            topic = next(iter(parse_topic(response, topic_id)), None)
            if topic is not None:
                created_at = int(topic.create_at)
                title = str(topic.title)
        probe = TopicProbe(topic_id, status, created_at, title)
        self.cache[topic_id] = probe
        return probe


def parse_through_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def cutoff_timestamp(through: date) -> int:
    next_day = datetime.combine(
        through + timedelta(days=1), datetime_time.min, LOCAL_TIMEZONE
    )
    return int(next_day.timestamp())


def nearest_valid_probe(
    fetch: Callable[[int], TopicProbe],
    center: int,
    lower: int,
    upper: int,
    *,
    max_distance: int = 64,
) -> TopicProbe | None:
    if lower > upper:
        return None
    for distance in range(0, max_distance + 1):
        candidates = [center] if distance == 0 else [center + distance, center - distance]
        for topic_id in candidates:
            if lower <= topic_id <= upper:
                probe = fetch(topic_id)
                if probe.has_timestamp:
                    return probe
    return None


def locate_date_boundary(
    fetch: Callable[[int], TopicProbe],
    known_before: TopicProbe,
    latest_id: int,
    cutoff: int,
    *,
    final_scan_size: int = 64,
) -> int:
    """Return the greatest candidate ID before an exclusive timestamp."""
    if not known_before.has_timestamp or known_before.created_at >= cutoff:
        raise ValueError("known_before must be a valid topic before the cutoff")
    if latest_id <= known_before.topic_id:
        raise ValueError("latest topic ID must be greater than the known lower bound")

    high = nearest_valid_probe(
        fetch,
        latest_id,
        known_before.topic_id + 1,
        latest_id,
    )
    if high is None:
        raise RuntimeError("Could not find an accessible topic near the latest ID")
    if high.created_at < cutoff:
        raise RuntimeError("Latest accessible topic is still before the requested cutoff")

    low = known_before
    while high.topic_id - low.topic_id > final_scan_size:
        midpoint = (low.topic_id + high.topic_id) // 2
        probe = nearest_valid_probe(
            fetch,
            midpoint,
            low.topic_id + 1,
            high.topic_id - 1,
        )
        if probe is None:
            raise RuntimeError(
                f"Could not locate an accessible topic between {low.topic_id} and {high.topic_id}"
            )
        if probe.created_at < cutoff:
            low = probe
        else:
            high = probe

    first_after = high
    for topic_id in range(low.topic_id + 1, high.topic_id + 1):
        probe = fetch(topic_id)
        if probe.has_timestamp and probe.created_at >= cutoff:
            first_after = probe
            break
    return first_after.topic_id - 1


def validate_explicit_boundary(
    fetch: Callable[[int], TopicProbe],
    end_id: int,
    cutoff: int,
    *,
    scan_distance: int = 64,
) -> tuple[TopicProbe, TopicProbe]:
    before = nearest_valid_probe(
        fetch, end_id, max(1, end_id - scan_distance), end_id, max_distance=scan_distance
    )
    after = nearest_valid_probe(
        fetch,
        end_id + 1,
        end_id + 1,
        end_id + 1 + scan_distance,
        max_distance=scan_distance,
    )
    if before is None or before.created_at >= cutoff:
        raise RuntimeError("Explicit end ID is not preceded by a topic before the cutoff")
    if after is None or after.created_at < cutoff:
        raise RuntimeError("Explicit end ID is not followed by a topic at or after the cutoff")
    return before, after


def database_snapshot(database: Path) -> dict[str, int]:
    with sqlite3.connect(database, timeout=60) as conn:
        return {
            "topics": int(conn.execute("SELECT COUNT(*) FROM topic").fetchone()[0]),
            "comments": int(conn.execute("SELECT COUNT(*) FROM comment").fetchone()[0]),
            "members": int(conn.execute("SELECT COUNT(*) FROM member").fetchone()[0]),
            "max_topic_id": int(
                conn.execute("SELECT COALESCE(MAX(id), 0) FROM topic").fetchone()[0]
            ),
        }


def known_topic_before(database: Path, cutoff: int) -> TopicProbe:
    with sqlite3.connect(database, timeout=60) as conn:
        row = conn.execute(
            """
            SELECT id, create_at, title
            FROM topic
            WHERE create_at > 0 AND create_at < ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (cutoff,),
        ).fetchone()
    if row is None:
        raise RuntimeError("Database has no valid topic before the requested cutoff")
    return TopicProbe(int(row[0]), 200, int(row[1]), str(row[2]))


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def load_plan(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"Crawl plan not found: {path}")
    plan = json.loads(path.read_text(encoding="utf-8"))
    if plan.get("schema") != STATE_SCHEMA:
        raise SystemExit(f"Unsupported crawl plan schema: {plan.get('schema')}")
    return plan


def proxy_environment(explicit_proxy: str | None = None) -> dict[str, str]:
    proxies = urllib.request.getproxies()
    http_proxy = explicit_proxy or proxies.get("http")
    https_proxy = explicit_proxy or proxies.get("https") or http_proxy
    values = {}
    for name, value in (
        ("HTTP_PROXY", http_proxy),
        ("HTTPS_PROXY", https_proxy),
        ("http_proxy", http_proxy),
        ("https_proxy", https_proxy),
    ):
        if value:
            values[name] = str(value)
    return values


def scrapy_command(plan: dict, args) -> list[str]:
    command = [
        str(ROOT / ".venv" / "bin" / "scrapy"),
        "crawl",
        "v2ex",
        "-a",
        f"start_id={plan['start_id']}",
        "-a",
        f"end_id={plan['end_id']}",
        "-a",
        f"crawl_purpose={plan['crawl_purpose']}",
        "-a",
        f"crawl_members={'false' if args.no_members else 'true'}",
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
    return command


def systemd_command(
    plan: dict,
    args,
    command: list[str],
    environment: dict[str, str],
) -> list[str]:
    result = [
        "systemd-run",
        f"--unit={plan['unit']}",
        "--collect",
        f"--description=V2EX incremental crawl through {plan['through']}",
        f"--property=WorkingDirectory={ROOT}",
        f"--setenv=V2EX_COOKIES_FILE={args.cookie_file.resolve()}",
        f"--setenv=V2EX_JOBDIR={plan['job_dir']}",
    ]
    result.extend(f"--setenv={name}={value}" for name, value in environment.items())
    return [*result, *command]


def matching_crawl_runs(database: Path, purpose: str, started_at: int) -> list[dict]:
    with sqlite3.connect(database, timeout=60) as conn:
        rows = conn.execute(
            """
            SELECT id, started_at, finished_at, close_reason,
                   response_count, error_count, configuration
            FROM crawl_run
            WHERE started_at >= ?
            ORDER BY id
            """,
            (started_at,),
        ).fetchall()
    runs = []
    for row in rows:
        try:
            configuration = json.loads(row[6])
        except (json.JSONDecodeError, TypeError):
            continue
        if configuration.get("crawl_purpose") != purpose:
            continue
        runs.append(
            {
                "id": int(row[0]),
                "started_at": int(row[1]),
                "finished_at": int(row[2]) if row[2] is not None else None,
                "close_reason": str(row[3]),
                "response_count": int(row[4]),
                "error_count": int(row[5]),
            }
        )
    return runs


def unit_status(unit: str | None) -> str:
    if not unit:
        return "not-launched"
    result = subprocess.run(
        ["systemctl", "show", unit, "-p", "ActiveState", "--value"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() or "inactive"


def crawl_report(database: Path, plan: dict) -> dict:
    start_id = int(plan["start_id"])
    end_id = int(plan["end_id"])
    cutoff = int(plan["cutoff_timestamp"])
    with sqlite3.connect(database, timeout=60) as conn:
        topic_rows = conn.execute(
            """
            SELECT id, create_at, title, author, node, clicks,
                   reply_count, favorite_count, thank_count, votes
            FROM topic
            WHERE id BETWEEN ? AND ?
            ORDER BY id
            """,
            (start_id, end_id),
        ).fetchall()
        fetch_rows = conn.execute(
            """
            SELECT topic_id, last_status_code, last_fetched_at
            FROM topic_fetch_state
            WHERE topic_id BETWEEN ? AND ?
            """,
            (start_id, end_id),
        ).fetchall()
        comments = int(
            conn.execute(
                "SELECT COUNT(*) FROM comment WHERE topic_id BETWEEN ? AND ?",
                (start_id, end_id),
            ).fetchone()[0]
        )
        current = {
            "topics": int(conn.execute("SELECT COUNT(*) FROM topic").fetchone()[0]),
            "comments": int(conn.execute("SELECT COUNT(*) FROM comment").fetchone()[0]),
            "members": int(conn.execute("SELECT COUNT(*) FROM member").fetchone()[0]),
        }

    topics = {int(row[0]): row for row in topic_rows}
    fetches = {int(row[0]): (int(row[1]), int(row[2])) for row in fetch_rows}
    all_ids = set(range(start_id, end_id + 1))
    missing_ids = sorted(all_ids - topics.keys())
    retry_ids = set()
    status_counts: dict[str, int] = {}
    for topic_id in all_ids:
        status = fetches.get(topic_id, (None, None))[0]
        if (
            status is None
            or status not in FINAL_HTTP_STATUSES
            or (status == 200 and topic_id not in topics)
        ):
            retry_ids.add(topic_id)
    for status, _ in fetches.values():
        status_counts[str(status)] = status_counts.get(str(status), 0) + 1

    valid_rows = [row for row in topic_rows if int(row[1]) > 0 and str(row[2])]
    placeholders = [row for row in topic_rows if int(row[1]) <= 0 or not str(row[2])]
    unknown_interaction_ids = []
    for row in topic_rows:
        topic_id, created_at, title, author, node, *interactions = row
        status = fetches.get(int(topic_id), (None, None))[0]
        has_unknown_interaction = any(int(value) < 0 for value in interactions)
        if has_unknown_interaction:
            unknown_interaction_ids.append(int(topic_id))
        if status == 200 and (
            int(created_at) <= 0
            or not str(title)
            or not str(author)
            or not str(node)
            or has_unknown_interaction
        ):
            retry_ids.add(int(topic_id))

    out_of_range = [int(row[0]) for row in valid_rows if int(row[1]) >= cutoff]
    baseline = plan["baseline"]
    runs = matching_crawl_runs(
        database, str(plan["crawl_purpose"]), int(plan["created_at"])
    )
    return {
        "through": plan["through"],
        "range": {"start_id": start_id, "end_id": end_id, "candidate_ids": len(all_ids)},
        "unit": {"name": plan.get("unit"), "state": unit_status(plan.get("unit"))},
        "topics": {
            "rows": len(topic_rows),
            "valid": len(valid_rows),
            "placeholders": len(placeholders),
            "unknown_interactions": len(unknown_interaction_ids),
            "missing": len(missing_ids),
            "out_of_range": len(out_of_range),
            "min_created_at": min((int(row[1]) for row in valid_rows), default=0),
            "max_created_at": max((int(row[1]) for row in valid_rows), default=0),
        },
        "comments_in_range": comments,
        "deltas": {
            "topic_rows": current["topics"] - int(baseline["topics"]),
            "comments": current["comments"] - int(baseline["comments"]),
            "members": current["members"] - int(baseline["members"]),
        },
        "fetch": {
            "tracked": len(fetches),
            "status_counts": status_counts,
            "retry_ids": sorted(retry_ids),
        },
        "out_of_range_ids": out_of_range,
        "unknown_interaction_ids": sorted(unknown_interaction_ids),
        "runs": runs,
    }


def crawl_status(database: Path, plan: dict) -> dict:
    start_id = int(plan["start_id"])
    end_id = int(plan["end_id"])
    with sqlite3.connect(database, timeout=60) as conn:
        topic_row = conn.execute(
            """
            SELECT COUNT(*),
                   SUM(create_at > 0 AND title != ''),
                   SUM(create_at <= 0 OR title = ''),
                   MAX(id)
            FROM topic
            WHERE id BETWEEN ? AND ?
            """,
            (start_id, end_id),
        ).fetchone()
        status_rows = conn.execute(
            """
            SELECT last_status_code, COUNT(*)
            FROM topic_fetch_state
            WHERE topic_id BETWEEN ? AND ?
            GROUP BY last_status_code
            ORDER BY last_status_code
            """,
            (start_id, end_id),
        ).fetchall()
    status_counts = {str(status): int(count) for status, count in status_rows}
    return {
        "unit_state": unit_status(plan.get("unit")),
        "candidate_ids": max(0, end_id - start_id + 1),
        "tracked": sum(status_counts.values()),
        "status_counts": status_counts,
        "topic_rows": int(topic_row[0] or 0),
        "valid_topics": int(topic_row[1] or 0),
        "placeholders": int(topic_row[2] or 0),
        "max_topic_id": int(topic_row[3] or 0),
        "runs": matching_crawl_runs(
            database, str(plan["crawl_purpose"]), int(plan["created_at"])
        ),
    }


def ids_to_ranges(topic_ids: list[int]) -> str:
    if not topic_ids:
        return ""
    ranges = []
    start = previous = topic_ids[0]
    for topic_id in topic_ids[1:]:
        if topic_id == previous + 1:
            previous = topic_id
            continue
        ranges.append((start, previous))
        start = previous = topic_id
    ranges.append((start, previous))
    return ",".join(
        str(start) if start == end else f"{start}-{end}" for start, end in ranges
    )


def print_status(database: Path, plan: dict) -> None:
    status = crawl_status(database, plan)
    candidate_ids = int(status["candidate_ids"])
    progress = 100.0 * int(status["tracked"]) / max(1, candidate_ids)
    remaining = max(0, candidate_ids - int(status["tracked"]))
    print(
        f"Crawl through {plan['through']}: {status['unit_state']}; "
        f"{status['tracked']:,}/{candidate_ids:,} IDs tracked ({progress:.1f}%), "
        f"{remaining:,} remaining, {status['valid_topics']:,} valid topics, "
        f"{status['placeholders']:,} placeholders."
    )
    print(f"HTTP statuses: {status['status_counts'] or '{}'}")
    if status["runs"]:
        latest = status["runs"][-1]
        print(
            f"Latest run #{latest['id']}: {latest['close_reason']}, "
            f"{latest['response_count']:,} responses, {latest['error_count']:,} errors."
        )


def write_report(state_dir: Path, report: dict) -> None:
    atomic_write_json(state_dir / "report.json", report)
    retry_ids = report["fetch"]["retry_ids"]
    retry_path = state_dir / "retry-topic-ids.txt"
    retry_path.write_text(
        ids_to_ranges(retry_ids) + ("\n" if retry_ids else ""), encoding="utf-8"
    )


def print_report(state_dir: Path, report: dict) -> None:
    topics = report["topics"]
    fetch = report["fetch"]
    candidate_ids = int(report["range"]["candidate_ids"])
    print(
        f"Crawl report through {report['through']}: "
        f"{fetch['tracked']:,}/{candidate_ids:,} IDs tracked, "
        f"{topics['valid']:,} valid topics, {topics['placeholders']:,} placeholders, "
        f"{topics['unknown_interactions']:,} with unknown interactions."
    )
    print(
        f"HTTP statuses: {fetch['status_counts'] or '{}'}; "
        f"retry {len(fetch['retry_ids']):,}; out of range {topics['out_of_range']:,}."
    )
    deltas = report["deltas"]
    print(
        "Database deltas: "
        f"{deltas['topic_rows']:+,} topic rows, {deltas['comments']:+,} comments, "
        f"{deltas['members']:+,} members."
    )
    print(f"Report written to {state_dir / 'report.json'}")
    if fetch["retry_ids"]:
        print(f"Retry IDs written to {state_dir / 'retry-topic-ids.txt'}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run and verify a date-bounded incremental V2EX crawl."
    )
    parser.add_argument(
        "action", nargs="?", choices=("start", "status", "report"), default="start"
    )
    parser.add_argument("--through", required=True, type=parse_through_date)
    parser.add_argument("--end-id", type=int, help="Use and verify an explicit upper ID.")
    parser.add_argument("--latest-id", type=int, help="Skip recent-page ID discovery.")
    parser.add_argument("--start-id", type=int)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--probe-delay", type=float, default=1.0)
    parser.add_argument("--probe-timeout", type=float, default=30.0)
    parser.add_argument("--auto-throttle", action="store_true")
    parser.add_argument("--no-members", action="store_true")
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
    args.concurrency = max(1, args.concurrency)
    args.delay = max(0.0, args.delay)
    database = ROOT / "v2ex.sqlite"
    state_dir = args.state_root.resolve() / f"through-{args.through.isoformat()}"
    plan_path = state_dir / "plan.json"

    if args.action in {"status", "report"}:
        plan = load_plan(plan_path)
        if args.action == "status":
            print_status(database, plan)
            return
        report = crawl_report(database, plan)
        write_report(state_dir, report)
        print_report(state_dir, report)
        return

    if plan_path.exists() and not args.refresh_plan:
        plan = load_plan(plan_path)
        print(f"Reusing crawl plan: {plan_path}")
    else:
        if plan_path.exists():
            previous = load_plan(plan_path)
            if unit_status(previous.get("unit")) in {"active", "activating"}:
                raise SystemExit(
                    f"Crawl unit is still active: {previous.get('unit')}.service"
                )
        if args.cookie_file is None or not args.cookie_file.is_file():
            raise SystemExit("Set V2EX_COOKIES_FILE or pass --cookie-file.")
        cookie = args.cookie_file.read_text(encoding="utf-8").strip()
        if not cookie:
            raise SystemExit(f"Cookie file is empty: {args.cookie_file}")
        if args.proxy:
            handler = urllib.request.ProxyHandler(
                {"http": args.proxy, "https": args.proxy}
            )
            opener = urllib.request.build_opener(handler)
        else:
            opener = urllib.request.build_opener()
        client = V2EXProbeClient(
            cookie,
            delay=args.probe_delay,
            timeout=args.probe_timeout,
            opener=opener,
        )
        cutoff = cutoff_timestamp(args.through)
        baseline = database_snapshot(database)
        start_id = args.start_id or baseline["max_topic_id"] + 1
        if args.end_id is not None:
            before, after = validate_explicit_boundary(
                client.fetch_topic, args.end_id, cutoff
            )
            end_id = args.end_id
        else:
            lower = known_topic_before(database, cutoff)
            latest_id = args.latest_id or client.recent_max_id()
            end_id = locate_date_boundary(
                client.fetch_topic, lower, latest_id, cutoff
            )
            before = nearest_valid_probe(
                client.fetch_topic, end_id, max(1, end_id - 64), end_id
            )
            after = nearest_valid_probe(
                client.fetch_topic, end_id + 1, end_id + 1, end_id + 65
            )
            if before is None or after is None:
                raise RuntimeError("Could not validate the discovered date boundary")
        created_at = int(time.time())
        purpose = f"incremental-through-{args.through.isoformat()}"
        state_dir.mkdir(parents=True, exist_ok=True)
        plan = {
            "schema": STATE_SCHEMA,
            "through": args.through.isoformat(),
            "cutoff_timestamp": cutoff,
            "start_id": int(start_id),
            "end_id": int(end_id),
            "candidate_ids": max(0, int(end_id) - int(start_id) + 1),
            "boundary_before": asdict(before),
            "boundary_after": asdict(after),
            "baseline": baseline,
            "created_at": created_at,
            "crawl_purpose": purpose,
            "job_dir": str(state_dir / "scrapy"),
            "unit": f"v2ex-crawl-through-{args.through.strftime('%Y%m%d')}-{created_at}",
        }
        atomic_write_json(plan_path, plan)
        print(
            f"Planned IDs {start_id}..{end_id} through {args.through.isoformat()}; "
            f"next accessible topic is #{after.topic_id}."
        )

    if int(plan["start_id"]) > int(plan["end_id"]):
        print("No new IDs fall within the requested date boundary.")
        return
    if args.dry_run:
        print(f"Plan written to {plan_path}")
        return
    if args.cookie_file is None or not args.cookie_file.is_file():
        raise SystemExit("Set V2EX_COOKIES_FILE or pass --cookie-file.")

    if unit_status(plan.get("unit")) in {"active", "activating"}:
        print_status(database, plan)
        print(f"Crawl unit is already active: {plan['unit']}.service")
        return

    command = scrapy_command(plan, args)
    environment = os.environ.copy()
    environment.update(proxy_environment(args.proxy))
    environment["V2EX_COOKIES_FILE"] = str(args.cookie_file.resolve())
    environment["V2EX_JOBDIR"] = str(plan["job_dir"])
    if args.foreground:
        print(f"Starting foreground crawl: {shlex.join(command)}")
        subprocess.run(command, cwd=ROOT, env=environment, check=True)
        report = crawl_report(database, plan)
        write_report(state_dir, report)
        print_status(database, plan)
        return

    launch = systemd_command(
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
                "--through",
                plan["through"],
            ]
        )
    )


if __name__ == "__main__":
    main()
