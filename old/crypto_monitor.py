#!/usr/bin/env python3
"""
Real-time crypto market monitor and alert system using Binance WebSocket APIs.

Key features:
- Ingests 1m klines (closed only) and mini-ticker last prices for BTCUSDT/ETHUSDT.
- Maintains 5-minute sliding windows on closed klines to detect rapid drops/rebounds.
- Persists klines, window stats, and alerts for the last 24 hours to SQLite.
- Broadcasts live prices, daily % change, and alerts to downstream clients via WebSocket.
"""
from __future__ import annotations

import asyncio
import logging
import os

from utils.crypt.db import SQLiteStore, retention_worker
from utils.crypt.env import load_env
from utils.crypt.http_server import start_http_server
from utils.crypt.market import MarketMonitor
from utils.crypt.ws import BroadcastHub, binance_listener, start_client_ws_server


ENV_FILE = os.getenv("ENV_FILE", ".env")
if not os.path.isabs(ENV_FILE):
    ENV_FILE = os.path.join(os.path.dirname(__file__), ENV_FILE)
load_env(ENV_FILE)

# Configuration
SYMBOLS = ["btcusdt", "ethusdt"]
BINANCE_STREAMS = [
    "btcusdt@kline_1m",
    "ethusdt@kline_1m",
    "btcusdt@miniTicker",
    "ethusdt@miniTicker",
]
DEFAULT_STREAM_URL = (
    "wss://stream.binance.com:9443/stream?streams=" + "/".join(BINANCE_STREAMS)
)
BINANCE_STREAM_URL = os.getenv("BINANCE_STREAM_URL", DEFAULT_STREAM_URL)

WINDOW_SIZE_MINUTES = int(os.getenv("WINDOW_SIZE_MINUTES", "5"))
ALERT_THRESHOLDS = [0.01, 0.005]  # 1% and 0.5%
ALERT_DEDUP_SECONDS = int(os.getenv("ALERT_DEDUP_SECONDS", "180"))
RETENTION_SECONDS = int(os.getenv("RETENTION_SECONDS", str(24 * 3600)))
RECENT_ALERT_LIMIT = int(os.getenv("RECENT_ALERT_LIMIT", "50"))
TIMEZONE_KEYS = {
    "utc": "UTC",
    "us_west": "America/Los_Angeles",
    "us_east": "America/New_York",
    "beijing": "Asia/Shanghai",
}

STUB_MODE = os.getenv("STUB_MODE", "").lower() in {"1", "true", "yes"}
DEFAULT_CLIENT_WS_HOST = "127.0.0.1"
DEFAULT_CLIENT_WS_PORT = 8765
DEFAULT_HTTP_HOST = "0.0.0.0"
DEFAULT_HTTP_PORT = 8080
if STUB_MODE:
    CLIENT_WS_HOST = os.getenv("CLIENT_WS_HOST", DEFAULT_CLIENT_WS_HOST)
    CLIENT_WS_PORT = int(os.getenv("CLIENT_WS_PORT", str(DEFAULT_CLIENT_WS_PORT)))
    HTTP_HOST = os.getenv("HTTP_HOST", DEFAULT_HTTP_HOST)
    HTTP_PORT = int(os.getenv("HTTP_PORT", str(DEFAULT_HTTP_PORT)))
else:
    CLIENT_WS_HOST = DEFAULT_CLIENT_WS_HOST
    CLIENT_WS_PORT = DEFAULT_CLIENT_WS_PORT
    HTTP_HOST = DEFAULT_HTTP_HOST
    HTTP_PORT = DEFAULT_HTTP_PORT
DB_PATH = os.getenv("DB_PATH", "crypto_monitor.db")


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    store = SQLiteStore(
        DB_PATH,
        retention_seconds=RETENTION_SECONDS,
        window_size_minutes=WINDOW_SIZE_MINUTES,
    )
    await store.init()
    broadcaster = BroadcastHub()
    monitor = MarketMonitor(
        store=store,
        broadcaster=broadcaster,
        symbols=SYMBOLS,
        window_size_minutes=WINDOW_SIZE_MINUTES,
        alert_thresholds=ALERT_THRESHOLDS,
        alert_dedup_seconds=ALERT_DEDUP_SECONDS,
        timezone_keys=TIMEZONE_KEYS,
    )
    listeners = [
        retention_worker(store),
        start_client_ws_server(
            monitor, broadcaster, CLIENT_WS_HOST, CLIENT_WS_PORT, RECENT_ALERT_LIMIT
        ),
        start_http_server(store, HTTP_HOST, HTTP_PORT, RECENT_ALERT_LIMIT),
    ]
    if STUB_MODE:
        from test.stub.crypt.stub_generator import stub_generator

        listeners.append(
            stub_generator(
                monitor,
                symbols=SYMBOLS,
                alert_thresholds=ALERT_THRESHOLDS,
                timezone_keys=TIMEZONE_KEYS,
                window_size_minutes=WINDOW_SIZE_MINUTES,
            )
        )
    else:
        listeners.append(binance_listener(monitor, BINANCE_STREAM_URL))

    await asyncio.gather(*listeners)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Shutting down monitor.")
