"""Read-only access to the official V2EX API, separate from HTML cookies."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from v2ex_scrapy.browser_request import BrowserRequestError, load_browser_request


API_HOSTS = ("www.v2ex.com", "edge.v2ex.com")
API_USER_AGENT = "V2EXDashboard/1.0 (+https://github.com/taifuer/v2ex_scrapy)"
MIN_REQUEST_DELAY = 7.0
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class APIError(RuntimeError):
    """A safe diagnostic that contains neither credentials nor response bodies."""


class NoAPIRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_api_token(path: Path) -> str:
    try:
        token = path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        raise APIError("Cannot read the API token file.") from None
    if not token or not token.isprintable() or any(char.isspace() for char in token):
        raise APIError("Store only the API token, without a Bearer prefix or line breaks.")
    return token


def nonnegative_int(value) -> int | None:
    try:
        number = int(value)
    except (ValueError, TypeError):
        return None
    return number if number >= 0 else None


class V2EXAPIClient:
    def __init__(
        self,
        token: str,
        *,
        host: str = "www.v2ex.com",
        timeout: float = 30.0,
        proxy: str | None = None,
        request_file: Path | None = None,
        opener=None,
        sleeper=time.sleep,
        clock=time.monotonic,
    ):
        if host not in API_HOSTS:
            raise ValueError("Only documented V2EX API hosts are allowed.")
        if (
            not token or not token.isascii() or not token.isprintable()
            or any(char.isspace() for char in token)
        ):
            raise APIError("Invalid API token format.")
        handlers = [NoAPIRedirect()]
        if proxy:
            handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        self.opener = opener or urllib.request.build_opener(*handlers)
        self.token = token
        self.host = host
        self.headers = {
            "User-Agent": API_USER_AGENT,
            "Accept": "application/json",
            "From": "taifu@taifua.com",
        }
        if request_file is not None:
            try:
                profile = load_browser_request(request_file)
            except BrowserRequestError as exc:
                raise APIError(str(exc)) from None
            if profile.host != host:
                raise APIError("Browser request export must match the API host.")
            self.headers = profile.request_headers(include_cookie=True)
        self.timeout = max(1.0, timeout)
        self.sleeper = sleeper
        self.clock = clock
        self.last_finished_at = None
        self.rate_limit: dict[str, int] = {}
        self.blocked = False

    def get(self, resource: str, *, topic_id: int | None = None, page: int = 1):
        if resource not in {"member", "latest", "topic", "replies"}:
            raise ValueError("Only read-only member/topic resources are supported.")
        if not isinstance(page, int) or isinstance(page, bool) or page < 1:
            raise ValueError("Page must be a positive integer.")
        if resource in {"topic", "replies"} and (
            not isinstance(topic_id, int) or isinstance(topic_id, bool) or topic_id < 1
        ):
            raise ValueError("Topic ID must be a positive integer.")
        paths = {
            "member": "member",
            "latest": f"topics/latest?p={page}",
            "topic": f"topics/{topic_id}",
            "replies": f"topics/{topic_id}/replies?p={page}",
        }
        if self.blocked or self.rate_limit.get("remaining") == 0:
            raise APIError("API access stopped or quota exhausted; no further requests sent.")
        if self.last_finished_at is not None:
            limit = self.rate_limit.get("limit", 600)
            delay = max(MIN_REQUEST_DELAY, 3600 / max(1, limit) + 1)
            wait = delay - (self.clock() - self.last_finished_at)
            if wait > 0:
                self.sleeper(wait)
        request = urllib.request.Request(
            f"https://{self.host}/api/v2/{paths[resource]}",
            headers={
                **self.headers,
                "Authorization": f"Bearer {self.token}",
            },
            method="GET",
        )
        try:
            try:
                response = self.opener.open(request, timeout=self.timeout)
            except urllib.error.HTTPError as exc:
                response = exc
            with response:
                status = int(response.status)
                content_type = response.headers.get("Content-Type", "").lower()
                challenged = response.headers.get("cf-mitigated") == "challenge"
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                self.rate_limit = {}
                for key in ("limit", "remaining", "reset"):
                    value = nonnegative_int(response.headers.get(f"X-Rate-Limit-{key}"))
                    if value is not None:
                        self.rate_limit[key] = value
                retry_after = nonnegative_int(response.headers.get("Retry-After"))
                if retry_after is not None:
                    self.rate_limit["retry_after"] = retry_after
        except (urllib.error.URLError, OSError) as exc:
            self.blocked = True
            raise APIError(f"API connection failed ({type(exc).__name__}); no automatic retries.") from None
        finally:
            self.last_finished_at = self.clock()

        if challenged:
            self.blocked = True
            raise APIError(f"Cloudflare challenge (HTTP {status}); API token validity is unconfirmed.")
        if status == 429:
            self.blocked = True
            raise APIError("API rate limit reached (HTTP 429); stop until the quota resets.")
        if "application/json" not in content_type:
            self.blocked = True
            raise APIError(
                f"API returned non-JSON (HTTP {status}); this is not a confirmed "
                "API authentication result or a missing topic. No data imported."
            )
        if len(raw) > MAX_RESPONSE_BYTES:
            self.blocked = True
            raise APIError("API response exceeds the probe size limit.")
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeError):
            self.blocked = True
            raise APIError("API returned invalid JSON. No data imported.") from None
        if status != 200 or not isinstance(payload, dict) or payload.get("success") is not True:
            self.blocked = True
            if status in {401, 403}:
                raise APIError(f"API authorization failed (HTTP {status}); verify token validity and scope.")
            raise APIError(f"API did not return a successful result (HTTP {status}). No data imported.")
        if "result" not in payload:
            self.blocked = True
            raise APIError("API result schema is unexpected. No data imported.")
        return payload["result"]
