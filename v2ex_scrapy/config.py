import json
import os


def get_env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def get_bool_env(name: str, default: bool = False) -> bool:
    value = get_env(name)
    if value == "":
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def get_int_env(name: str, default: int) -> int:
    value = get_env(name)
    if value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def get_cookie_string() -> str:
    cookie_file = get_env("V2EX_COOKIES_FILE")
    if cookie_file != "":
        try:
            with open(cookie_file, encoding="utf-8") as fp:
                return fp.read().strip()
        except OSError:
            return ""
    return get_env("V2EX_COOKIES")


def get_proxies() -> list[str]:
    raw = get_env("V2EX_PROXIES")
    if raw == "":
        return []

    if raw.startswith("["):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    return [item.strip() for item in raw.replace("\n", ",").split(",") if item.strip()]
