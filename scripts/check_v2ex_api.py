#!/usr/bin/env python3
"""Inspect authenticated API field coverage without writing the source database."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v2ex_scrapy.api import API_HOSTS, APIError, V2EXAPIClient, read_api_token


def field_types(value) -> dict:
    if not isinstance(value, dict):
        return {"result_type": type(value).__name__}
    return {
        key: field_types(item) if isinstance(item, dict) else type(item).__name__
        for key, item in value.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--token-file", type=Path,
        default=Path(os.environ["V2EX_API_TOKEN_FILE"])
        if os.environ.get("V2EX_API_TOKEN_FILE") else None,
    )
    parser.add_argument("--host", choices=API_HOSTS, default=API_HOSTS[0])
    parser.add_argument(
        "--request-file", type=Path,
        default=Path(os.environ["V2EX_BROWSER_REQUEST_FILE"])
        if os.environ.get("V2EX_BROWSER_REQUEST_FILE") else None,
    )
    parser.add_argument("--topic-id", type=int)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--proxy")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    if args.token_file is None:
        parser.error("set V2EX_API_TOKEN_FILE or pass --token-file")
    if args.page < 1 or (args.topic_id is not None and args.topic_id < 1):
        parser.error("topic ID and page must be positive")
    client = V2EXAPIClient(
        read_api_token(args.token_file), host=args.host,
        timeout=args.timeout, proxy=args.proxy, request_file=args.request_file,
    )
    member = client.get("member")
    if not isinstance(member, dict) or not member.get("username"):
        raise APIError("API member response did not confirm authentication.")
    print(json.dumps({"authenticated": True, "rate_limit": client.rate_limit}), flush=True)
    if args.topic_id is not None:
        topic = client.get("topic", topic_id=args.topic_id)
        if not isinstance(topic, dict) or topic.get("id") != args.topic_id:
            raise APIError("API topic response did not match the requested topic.")
        print(json.dumps({"topic_id": args.topic_id, "topic_fields": field_types(topic), "rate_limit": client.rate_limit}), flush=True)
        replies = client.get("replies", topic_id=args.topic_id, page=args.page)
        if not isinstance(replies, list):
            raise APIError("API replies response is not a list; inspect the response contract.")
        print(json.dumps({"replies_page": args.page, "replies_count": len(replies), "reply_fields": field_types(replies[0]) if replies else {}, "rate_limit": client.rate_limit}), flush=True)
    if args.latest:
        topics = client.get("latest", page=args.page)
        if not isinstance(topics, list):
            raise APIError("API latest-topics response is not a list; inspect the response contract.")
        print(json.dumps({"latest_page": args.page, "count": len(topics), "max_topic_id": max((item.get("id", 0) for item in topics if isinstance(item, dict)), default=0), "rate_limit": client.rate_limit}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except APIError as exc:
        raise SystemExit(str(exc)) from None
