#!/usr/bin/env python3
"""Bounded anonymous checks; never read cookies or infer privacy from HTTP errors."""

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path

from parsel import Selector

ORIGIN = "https://www.v2ex.com"
USER_AGENT = "V2EXDashboardAudit/1.0 (+https://github.com/taifuer/v2ex_scrapy)"


def classify(status: int, url: str, body: str) -> str:
    if status in {403, 429, 503}:
        return "blocked_or_rate_limited"
    if urllib.parse.urlsplit(url).path == "/signin":
        return "login_required"
    if status != 200:
        return "unknown"
    page = Selector(text=body)
    if page.css(".header h1") and page.css(".header a[href^='/go/']") and page.css(".topic_content"):
        return "anonymous_readable"
    if page.css("form[action='/signin']"):
        return "login_required"
    return "unknown"


class LocalRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if parsed.scheme != "https" or parsed.netloc != "www.v2ex.com":
            raise ValueError("Anonymous audit refused an external redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic-id", type=int, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    ids = list(dict.fromkeys(args.topic_id))
    if len(ids) > 20 or any(value <= 0 for value in ids):
        parser.error("Use 1 to 20 positive topic IDs per audit")
    if args.output.exists():
        parser.error("Refusing to overwrite an existing audit report")
    opener = urllib.request.build_opener(LocalRedirects())
    headers = {"User-Agent": USER_AGENT, "From": "taifu@taifua.com"}
    robots = urllib.robotparser.RobotFileParser()
    request = urllib.request.Request(ORIGIN + "/robots.txt", headers=headers)
    with opener.open(request, timeout=20) as response:
        text = response.read(500_000).decode("utf-8", "replace")
        if "<html" in text.lower() or "user-agent:" not in text.lower():
            raise ValueError("Could not verify robots rules; audit stopped")
        robots.parse(text.splitlines())
    delay = max(1, robots.crawl_delay(USER_AGENT) or 0)
    rate = robots.request_rate(USER_AGENT)
    if rate:
        delay = max(delay, rate.seconds / rate.requests)
    rows = []
    for topic_id in ids:
        url = f"{ORIGIN}/t/{topic_id}"
        if not robots.can_fetch(USER_AGENT, url):
            rows.append({"topic_id": topic_id, "state": "robots_disallowed"})
            continue
        time.sleep(delay)
        try:
            with opener.open(urllib.request.Request(url, headers=headers), timeout=20) as response:
                state = classify(response.status, response.url, response.read(2_000_000).decode("utf-8", "replace"))
        except urllib.error.HTTPError as error:
            state = classify(error.code, error.url, "")
        except (urllib.error.URLError, TimeoutError, ValueError):
            state = "unknown"
        rows.append({"topic_id": topic_id, "state": state})
        if state == "blocked_or_rate_limited":
            break
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "requested_ids": ids, "results": rows,
        "scope": "Anonymous access at check time only; unknown is not proof of restriction or permission to republish.",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Checked {len(rows)} / {len(ids)} topics; no cookies used, no policy or source data changed")


if __name__ == "__main__":
    main()
