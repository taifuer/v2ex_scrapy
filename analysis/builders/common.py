from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from time import perf_counter


LOCAL_TIMEZONE = timezone(timedelta(hours=8))


class BuildProgress:
    def __init__(self, label: str):
        self.label = label
        self.started_at = perf_counter()
        self.stage_started_at = self.started_at
        self.stage = ""

    def step(self, stage: str) -> None:
        now = perf_counter()
        if self.stage:
            print(f"[build] completed {self.stage} in {now - self.stage_started_at:.1f}s", flush=True)
        self.stage = stage
        self.stage_started_at = now
        print(f"[build] starting {stage}", flush=True)

    def finish(self) -> None:
        now = perf_counter()
        if self.stage:
            print(f"[build] completed {self.stage} in {now - self.stage_started_at:.1f}s", flush=True)
        print(f"[build] finished {self.label} in {now - self.started_at:.1f}s", flush=True)


class CommentTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag in {"img", "iframe"}:
            marker = "图片" if tag == "img" else "视频"
            self.parts.append(f"\n[{marker}]\n")
        elif tag in {"br", "div", "p", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str):
        if tag in {"div", "p", "li"}:
            self.parts.append("\n")

    def handle_data(self, data: str):
        self.parts.append(data)

    def text(self) -> str:
        return "\n".join(
            line for line in (" ".join(part.split()) for part in "".join(self.parts).splitlines())
            if line
        )


def comment_text(content: str | None) -> str:
    parser = CommentTextParser()
    parser.feed(content or "")
    parser.close()
    return parser.text()


def comment_prose_text(content: str | None) -> str:
    media_markers = {"[图片]", "[视频]"}
    return "\n".join(
        line for line in (content or "").splitlines()
        if line.strip() not in media_markers
    ).strip()


def month_for(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, LOCAL_TIMEZONE).strftime("%Y-%m")


def previous_period(period: str) -> str:
    year, month = map(int, period.split("-"))
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"


def source_complete_through(
    latest_topic_at: int,
    data_as_of: int,
    current_period: str,
) -> str:
    latest_topic_period = month_for(latest_topic_at)
    if latest_topic_period >= current_period:
        return previous_period(current_period)
    data_datetime = datetime.fromtimestamp(data_as_of, LOCAL_TIMEZONE)
    data_period = data_datetime.strftime("%Y-%m")
    if data_period > latest_topic_period:
        return latest_topic_period
    last_day = monthrange(data_datetime.year, data_datetime.month)[1]
    if data_period == latest_topic_period and data_datetime.day == last_day:
        return latest_topic_period
    return previous_period(latest_topic_period)


def period_end_timestamp(period: str) -> int:
    year, month = map(int, period.split("-"))
    if month == 12:
        year += 1
        month = 1
    else:
        month += 1
    return int(datetime(year, month, 1, tzinfo=LOCAL_TIMEZONE).timestamp())


def threshold_rows(values, thresholds) -> list[dict[str, int]]:
    normalized = [max(0, int(value or 0)) for value in values]
    return [
        {
            "threshold": threshold,
            "count": sum(value >= threshold for value in normalized),
        }
        for threshold in thresholds
    ]


def first_reply_bucket(delay: int | None) -> str:
    if delay is None:
        return "none"
    for label, upper_bound in (("10m", 600), ("1h", 3600), ("6h", 21600),
                               ("24h", 86400), ("3d", 259200), ("7d", 604800)):
        if delay < upper_bound:
            return label
    return "none"


def comment_age_bucket(delay: int) -> str | None:
    for label, upper_bound in (("10m", 600), ("1h", 3600), ("6h", 21600),
                               ("24h", 86400), ("3d", 259200), ("7d", 604800)):
        if delay < upper_bound:
            return label
    return None
