import os
from typing import List


def _env_bool(key: str, default: bool = False) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float_list(key: str, default: List[float]) -> List[float]:
    value = os.getenv(key)
    if not value:
        return default
    items: List[float] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            items.append(float(item))
        except ValueError:
            continue
    return items or default


def _env_list(key: str, default: List[str]) -> List[str]:
    value = os.getenv(key)
    if not value:
        return default
    return [item.strip().lower() for item in value.split(",") if item.strip()]


SYMBOLS = _env_list("CRYPTO_SYMBOLS", ["btcusdt", "ethusdt"])
BINANCE_STREAMS = [
    f"{symbol}@kline_1m" for symbol in SYMBOLS
] + [f"{symbol}@miniTicker" for symbol in SYMBOLS]
DEFAULT_STREAM_URL = (
    "wss://stream.binance.com:9443/stream?streams=" + "/".join(BINANCE_STREAMS)
)
BINANCE_STREAM_URL = os.getenv("BINANCE_STREAM_URL", DEFAULT_STREAM_URL)

WINDOW_SIZE_MINUTES = _env_int("WINDOW_SIZE_MINUTES", 5)
ALERT_THRESHOLDS = _env_float_list("ALERT_THRESHOLDS", [0.01, 0.005])
ALERT_DEDUP_SECONDS = _env_int("ALERT_DEDUP_SECONDS", 180)
RETENTION_SECONDS = _env_int("RETENTION_SECONDS", 24 * 3600)
RECENT_ALERT_LIMIT = _env_int("RECENT_ALERT_LIMIT", 50)

TIMEZONE_KEYS = {
    "utc": "UTC",
    "us_west": "America/Los_Angeles",
    "us_east": "America/New_York",
    "beijing": "Asia/Shanghai",
}

STUB_MODE = _env_bool("STUB_MODE", False)
AUTO_CREATE_SCHEMA = _env_bool("CRYPTO_SCHEMA_AUTO_CREATE", False)
