"""Read a private browser request export as data, never as a shell command."""

from dataclasses import dataclass, field
from pathlib import Path
import shlex
from urllib.parse import urlsplit


V2EX_HOSTS = {"www.v2ex.com", "edge.v2ex.com", "v2ex.com"}
HTML_HOSTS = {"www.v2ex.com", "v2ex.com"}
DEFAULT_HTML_HOST = "www.v2ex.com"
PUBLIC_HEADERS = {
    "accept", "accept-language", "cache-control", "pragma", "priority",
    "referer", "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform",
    "sec-fetch-dest", "sec-fetch-mode", "sec-fetch-site", "user-agent",
}


class BrowserRequestError(ValueError):
    pass


def html_base_url(host: str = DEFAULT_HTML_HOST) -> str:
    if host not in HTML_HOSTS:
        raise BrowserRequestError("HTML crawling requires a www.v2ex.com or v2ex.com request export.")
    return f"https://{host}"


def same_html_origin(url: str, host: str) -> bool:
    try:
        parsed = urlsplit(url)
        return (
            host in HTML_HOSTS and parsed.scheme == "https" and parsed.hostname == host
            and parsed.port in {None, 443} and not parsed.username and not parsed.password
        )
    except ValueError:
        return False


@dataclass(frozen=True)
class BrowserRequest:
    host: str
    headers: dict[str, str] = field(repr=False)
    cookie: str = field(default="", repr=False)

    def request_headers(self, *, include_cookie: bool = False) -> dict[str, str]:
        headers = dict(self.headers)
        if include_cookie and self.cookie:
            headers["cookie"] = self.cookie
        return headers


def load_browser_request(path: Path) -> BrowserRequest:
    try:
        raw = path.expanduser().read_text(encoding="utf-8")
        args = shlex.split(raw.replace("\\\r\n", "").replace("\\\n", ""))
    except (OSError, UnicodeError, ValueError):
        raise BrowserRequestError("Cannot read a valid browser cURL (bash) export.") from None
    if not args or args[0] != "curl":
        raise BrowserRequestError("Expected a browser cURL (bash) export.")
    headers = {}
    urls = []
    index = 1
    while index < len(args):
        arg = args[index]
        if arg in {"-H", "--header", "-b", "--cookie", "--url", "-X", "--request"}:
            if index + 1 >= len(args):
                raise BrowserRequestError("Incomplete browser request option.")
            value = args[index + 1]
            if arg in {"-H", "--header"}:
                name, separator, value = value.partition(":")
                name = name.strip().lower()
                if not separator or not name or name in headers:
                    raise BrowserRequestError("Invalid or duplicate browser request header.")
                headers[name] = value.strip()
            elif arg in {"-b", "--cookie"}:
                if value.startswith("@") or "cookie" in headers:
                    raise BrowserRequestError("Expected a literal Cookie header, not a file.")
                headers["cookie"] = value
            elif arg == "--url":
                urls.append(value)
            elif value.upper() != "GET":
                raise BrowserRequestError("Only a read-only GET request export is supported.")
            index += 2
        elif arg == "--compressed":
            index += 1
        elif arg.startswith("https://"):
            urls.append(arg)
            index += 1
        else:
            raise BrowserRequestError("Unsupported browser request option; nothing executed.")
    if len(urls) != 1:
        raise BrowserRequestError("Expected exactly one official V2EX URL.")
    try:
        url = urlsplit(urls[0])
        valid = (
            url.scheme == "https" and url.hostname in V2EX_HOSTS
            and url.port in {None, 443} and not url.username and not url.password
        )
    except ValueError:
        valid = False
    if not valid:
        raise BrowserRequestError("Only HTTPS requests to official V2EX hosts are allowed.")
    if not headers.get("user-agent"):
        raise BrowserRequestError("Browser request export is missing User-Agent.")
    for value in headers.values():
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise BrowserRequestError("Browser request contains an invalid header value.")
    # Authorization from the export must never reach HTML or member-page requests.
    return BrowserRequest(
        host=url.hostname,
        headers={key: value for key, value in headers.items() if key in PUBLIC_HEADERS},
        cookie=headers.get("cookie", ""),
    )
