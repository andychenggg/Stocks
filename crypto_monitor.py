#!/usr/bin/env python3
"""
Real-time crypto market monitor and alert system using Binance WebSocket APIs.

Key features:
- Ingests 1m klines (closed only) and mini-ticker last prices for BTCUSDT/ETHUSDT.
- Maintains 5-minute sliding windows on closed klines to detect rapid drops/rebounds.
- Persists klines, window stats, and alerts for the last 24 hours to SQLite.
- Broadcasts live prices, daily % change, and alerts to downstream clients via WebSocket.

Dependencies (install locally before running):
    pip install websockets

Usage:
    python crypto_monitor.py

Design notes:
- All networking is asyncio-based. Incoming Binance events are decoupled from alert logic.
- Alerts deduplicate per (symbol, type, threshold) within ALERT_DEDUP_SECONDS.
- Daily open tracks the first kline open of the UTC trading day.
"""
import asyncio
import datetime as dt
import json
import logging
import sqlite3
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional, Tuple

import websockets
from websockets.server import WebSocketServerProtocol

# Configuration
SYMBOLS = ["btcusdt", "ethusdt"]
BINANCE_STREAMS = [
    "btcusdt@kline_1m",
    "ethusdt@kline_1m",
    "btcusdt@miniTicker",
    "ethusdt@miniTicker",
]
BINANCE_STREAM_URL = (
    "wss://stream.binance.com:9443/stream?streams=" + "/".join(BINANCE_STREAMS)
)

WINDOW_SIZE_MINUTES = 5
ALERT_THRESHOLDS = [0.01, 0.005]  # 1% and 0.5%
ALERT_DEDUP_SECONDS = 180
RETENTION_SECONDS = 24 * 3600

CLIENT_WS_HOST = "0.0.0.0"
CLIENT_WS_PORT = 8765
DB_PATH = "crypto_monitor.db"


def utc_date_from_ms(ts_ms: int) -> dt.date:
    return dt.datetime.utcfromtimestamp(ts_ms / 1000).date()


def pct_change(base: Optional[float], value: Optional[float]) -> Optional[float]:
    if base is None or value is None:
        return None
    if base == 0:
        return None
    return (value - base) / base


def now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class ClosedKline:
    symbol: str
    open_time: int
    close_time: int
    open: float
    high: float
    low: float
    close: float


class SQLiteStore:
    """Lightweight persistence layer keeping the last 24h of market data."""

    def __init__(self, path: str = DB_PATH) -> None:
        self.path = path

    async def init(self) -> None:
        await self._execute(
            """
            CREATE TABLE IF NOT EXISTS klines (
                symbol TEXT NOT NULL,
                open_time INTEGER NOT NULL,
                close_time INTEGER NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                PRIMARY KEY (symbol, open_time)
            );
            """
        )
        await self._execute(
            """
            CREATE TABLE IF NOT EXISTS window_stats (
                symbol TEXT NOT NULL,
                window_end INTEGER NOT NULL,
                change_close REAL NOT NULL,
                change_low REAL NOT NULL,
                change_high REAL NOT NULL,
                length INTEGER NOT NULL,
                PRIMARY KEY (symbol, window_end)
            );
            """
        )
        await self._execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                magnitude REAL NOT NULL,
                ts INTEGER NOT NULL,
                reference_open REAL NOT NULL,
                reference_close REAL NOT NULL,
                reference_low REAL NOT NULL,
                reference_high REAL NOT NULL
            );
            """
        )

    async def insert_kline(self, k: ClosedKline) -> None:
        await self._execute(
            """
            INSERT OR REPLACE INTO klines(symbol, open_time, close_time, open, high, low, close)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (k.symbol, k.open_time, k.close_time, k.open, k.high, k.low, k.close),
        )

    async def insert_window_stats(
        self,
        symbol: str,
        window_end: int,
        change_close: float,
        change_low: float,
        change_high: float,
        length: int,
    ) -> None:
        await self._execute(
            """
            INSERT OR REPLACE INTO window_stats(symbol, window_end, change_close, change_low, change_high, length)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (symbol, window_end, change_close, change_low, change_high, length),
        )

    async def insert_alert(
        self,
        symbol: str,
        alert_type: str,
        magnitude: float,
        ts: int,
        reference_open: float,
        reference_close: float,
        reference_low: float,
        reference_high: float,
    ) -> None:
        await self._execute(
            """
            INSERT INTO alerts(symbol, alert_type, magnitude, ts, reference_open, reference_close, reference_low, reference_high)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                symbol,
                alert_type,
                magnitude,
                ts,
                reference_open,
                reference_close,
                reference_low,
                reference_high,
            ),
        )

    async def prune_older_than(self, cutoff_ms: int) -> None:
        await self._execute("DELETE FROM klines WHERE close_time < ?;", (cutoff_ms,))
        await self._execute("DELETE FROM window_stats WHERE window_end < ?;", (cutoff_ms,))
        await self._execute("DELETE FROM alerts WHERE ts < ?;", (cutoff_ms,))

    async def _execute(self, query: str, params: Tuple = ()) -> None:
        await asyncio.to_thread(self._execute_sync, query, params)

    def _execute_sync(self, query: str, params: Tuple) -> None:
        conn = sqlite3.connect(self.path)
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit()
        cur.close()
        conn.close()


class BroadcastHub:
    """Manages outbound WebSocket clients for real-time updates."""

    def __init__(self) -> None:
        self.clients: set[WebSocketServerProtocol] = set()

    async def register(self, ws: WebSocketServerProtocol) -> None:
        self.clients.add(ws)

    async def unregister(self, ws: WebSocketServerProtocol) -> None:
        self.clients.discard(ws)

    async def send_snapshot(self, ws: WebSocketServerProtocol, snapshot: dict) -> None:
        try:
            await ws.send(json.dumps({"type": "snapshot", "data": snapshot}))
        except Exception:
            logging.exception("Failed to send snapshot to client")

    async def broadcast(self, payload: dict) -> None:
        if not self.clients:
            return
        msg = json.dumps(payload, separators=(",", ":"))
        stale: List[WebSocketServerProtocol] = []
        for ws in list(self.clients):
            try:
                await ws.send(msg)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.clients.discard(ws)


class MarketMonitor:
    """Holds in-memory state for windows, alerting, and daily context."""

    def __init__(self, store: SQLiteStore, broadcaster: BroadcastHub) -> None:
        self.store = store
        self.broadcaster = broadcaster
        self.windows: Dict[str, Deque[ClosedKline]] = {
            s: deque(maxlen=WINDOW_SIZE_MINUTES) for s in SYMBOLS
        }
        self.today_open: Dict[str, Optional[float]] = {s: None for s in SYMBOLS}
        self.today_key: Dict[str, Optional[dt.date]] = {s: None for s in SYMBOLS}
        self.last_alert_at: Dict[Tuple[str, str, float], float] = {}
        self.last_price: Dict[str, Optional[float]] = {s: None for s in SYMBOLS}

    async def handle_stream_message(self, raw: str) -> None:
        payload = json.loads(raw)
        data = payload.get("data", {})
        event_type = data.get("e")
        if event_type == "kline":
            k = data.get("k", {})
            if not k.get("x"):  # ignore in-progress klines
                return
            symbol = data.get("s", "").lower()
            kline = ClosedKline(
                symbol=symbol,
                open_time=int(k["t"]),
                close_time=int(k["T"]),
                open=float(k["o"]),
                high=float(k["h"]),
                low=float(k["l"]),
                close=float(k["c"]),
            )
            await self.handle_closed_kline(kline)
        elif event_type == "24hrMiniTicker":
            symbol = data.get("s", "").lower()
            price = float(data.get("c"))
            event_ts = int(data.get("E", now_ms()))
            await self.handle_price_tick(symbol, price, event_ts)

    async def handle_closed_kline(self, kline: ClosedKline) -> None:
        await self.store.insert_kline(kline)
        self._update_daily_open(kline)
        window = self.windows[kline.symbol]
        window.append(kline)
        stats = self._compute_window_stats(window)
        if stats:
            await self.store.insert_window_stats(
                kline.symbol,
                stats["window_end"],
                stats["change_close"],
                stats["change_low"],
                stats["change_high"],
                stats["length"],
            )
            await self._check_alerts(kline.symbol, window, stats)
        await self._publish_price(kline.symbol, kline.close, kline.close_time)

    async def handle_price_tick(self, symbol: str, price: float, ts_ms: int) -> None:
        self.last_price[symbol] = price
        await self._publish_price(symbol, price, ts_ms)

    def _update_daily_open(self, kline: ClosedKline) -> None:
        day = utc_date_from_ms(kline.open_time)
        if self.today_key[kline.symbol] != day:
            self.today_key[kline.symbol] = day
            self.today_open[kline.symbol] = kline.open

    def _compute_window_stats(self, window: Deque[ClosedKline]) -> Optional[dict]:
        if len(window) < WINDOW_SIZE_MINUTES:
            return None
        open_base = window[0].open
        close_last = window[-1].close
        min_low = min(k.low for k in window)
        max_high = max(k.high for k in window)
        return {
            "window_end": window[-1].close_time,
            "change_close": (close_last - open_base) / open_base,
            "change_low": (min_low - open_base) / open_base,
            "change_high": (max_high - open_base) / open_base,
            "length": len(window),
            "reference_open": open_base,
            "reference_close": close_last,
            "reference_low": min_low,
            "reference_high": max_high,
        }

    async def _check_alerts(
        self, symbol: str, window: Deque[ClosedKline], stats: dict
    ) -> None:
        for threshold in ALERT_THRESHOLDS:
            if stats["change_close"] <= -threshold or stats["change_low"] <= -threshold:
                await self._emit_alert("rapid_drop", threshold, symbol, stats)
            if stats["change_close"] >= threshold or stats["change_high"] >= threshold:
                await self._emit_alert("rapid_rebound", threshold, symbol, stats)

    async def _emit_alert(
        self, alert_type: str, threshold: float, symbol: str, stats: dict
    ) -> None:
        key = (symbol, alert_type, threshold)
        now_sec = time.time()
        last_at = self.last_alert_at.get(key, 0)
        if now_sec - last_at < ALERT_DEDUP_SECONDS:
            return
        self.last_alert_at[key] = now_sec
        ts_ms = stats["window_end"]
        payload = {
            "type": "alert",
            "symbol": symbol.upper(),
            "alert_type": alert_type,
            "magnitude": threshold,
            "window_minutes": WINDOW_SIZE_MINUTES,
            "ts": ts_ms,
            "reference": {
                "open": stats["reference_open"],
                "close": stats["reference_close"],
                "low": stats["reference_low"],
                "high": stats["reference_high"],
            },
        }
        await self.store.insert_alert(
            symbol=symbol,
            alert_type=alert_type,
            magnitude=threshold,
            ts=ts_ms,
            reference_open=stats["reference_open"],
            reference_close=stats["reference_close"],
            reference_low=stats["reference_low"],
            reference_high=stats["reference_high"],
        )
        await self.broadcaster.broadcast(payload)
        logging.info("Alert emitted: %s", payload)

    async def _publish_price(self, symbol: str, price: float, ts_ms: int) -> None:
        self.last_price[symbol] = price
        pct = pct_change(self.today_open.get(symbol), price)
        payload = {
            "type": "price",
            "symbol": symbol.upper(),
            "price": price,
            "today_open": self.today_open.get(symbol),
            "pct_from_today_open": pct,
            "ts": ts_ms,
        }
        await self.broadcaster.broadcast(payload)

    def snapshot(self) -> dict:
        return {
            sym.upper(): {
                "price": self.last_price.get(sym),
                "today_open": self.today_open.get(sym),
                "pct_from_today_open": pct_change(
                    self.today_open.get(sym), self.last_price.get(sym)
                ),
            }
            for sym in SYMBOLS
        }


async def binance_listener(monitor: MarketMonitor) -> None:
    """Consumes Binance combined streams with reconnect logic."""
    backoff_sec = 3
    while True:
        try:
            logging.info("Connecting to Binance stream: %s", BINANCE_STREAM_URL)
            async with websockets.connect(
                BINANCE_STREAM_URL, ping_interval=20, ping_timeout=20
            ) as ws:
                logging.info("Connected to Binance.")
                async for message in ws:
                    await monitor.handle_stream_message(message)
        except Exception:
            logging.exception("Binance stream failed; retrying in %ss", backoff_sec)
            await asyncio.sleep(backoff_sec)


async def retention_worker(store: SQLiteStore) -> None:
    """Periodically prunes data older than retention horizon."""
    while True:
        cutoff_ms = int((time.time() - RETENTION_SECONDS) * 1000)
        try:
            await store.prune_older_than(cutoff_ms)
        except Exception:
            logging.exception("Failed to prune old data")
        await asyncio.sleep(600)


async def start_client_ws_server(
    monitor: MarketMonitor, broadcaster: BroadcastHub
) -> None:
    async def handler(ws: WebSocketServerProtocol) -> None:
        await broadcaster.register(ws)
        await broadcaster.send_snapshot(ws, monitor.snapshot())
        try:
            async for _ in ws:
                # Clients can stay connected; inbound messages are ignored.
                pass
        finally:
            await broadcaster.unregister(ws)

    server = await websockets.serve(
        handler, CLIENT_WS_HOST, CLIENT_WS_PORT, ping_interval=20, ping_timeout=20
    )
    logging.info("Client WS server listening on ws://%s:%s", CLIENT_WS_HOST, CLIENT_WS_PORT)
    await server.wait_closed()


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    store = SQLiteStore(DB_PATH)
    await store.init()
    broadcaster = BroadcastHub()
    monitor = MarketMonitor(store=store, broadcaster=broadcaster)

    await asyncio.gather(
        binance_listener(monitor),
        retention_worker(store),
        start_client_ws_server(monitor, broadcaster),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Shutting down monitor.")
