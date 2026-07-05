from http.cookies import SimpleCookie
import json
from typing import Union

import arrow


def time_to_timestamp(t: str) -> int:
    t = t.strip()
    a = None
    try:
        if t[-2:] == "00":
            a = arrow.get(t, "YYYY-MM-DD HH:mm:ss ZZ")
        else:
            a = arrow.utcnow().dehumanize(t.replace(" ", ""), "zh")
        return int(a.to("+08:00").timestamp())
    except Exception:
        return 0


def none_or_strip(s: Union[str, None]) -> Union[str, None]:
    if s is not None:
        return s.strip()
    return s


def json_to_str(j):
    return json.dumps(j, ensure_ascii=False)


def parse_int(value, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def parse_id_ranges(value: str | None) -> list[int]:
    if value is None or value.strip() == "":
        return []

    topic_ids: set[int] = set()
    for part in value.split(","):
        token = part.strip()
        if "-" not in token:
            topic_ids.add(int(token))
            continue

        start_text, end_text = token.split("-", 1)
        start = int(start_text)
        end = int(end_text)
        if start > end:
            raise ValueError(f"invalid descending ID range: {token}")
        topic_ids.update(range(start, end + 1))
    return sorted(topic_ids)


def cookie_str2cookie_dict(cookie_str: str):
    simple_cookie = SimpleCookie()
    simple_cookie.load(cookie_str)
    return {k: v.value for k, v in simple_cookie.items()}


if __name__ == "__main__":
    a = ["2022-04-28 13:24:38 +08:00", "287 天前", "1 小时前"]

    for i in a:
        print(time_to_timestamp(i))
