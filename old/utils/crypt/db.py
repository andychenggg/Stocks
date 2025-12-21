from __future__ import annotations

import asyncio
import sqlite3
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple


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
    """Lightweight persistence layer keeping market data and alerts."""

    def __init__(self, path: str, retention_seconds: int, window_size_minutes: int) -> None:
        self.path = path
        self.retention_seconds = retention_seconds
        self.window_size_minutes = window_size_minutes

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
                reference_high REAL NOT NULL,
                reference_peak_ts INTEGER,
                reference_current_ts INTEGER,
                drop_from_peak REAL,
                anchor_type TEXT,
                anchor_price REAL,
                anchor_ts INTEGER,
                anchor_pct_from_open REAL,
                current_pct_from_open REAL,
                move_from_anchor REAL
            );
            """
        )
        await self._ensure_alert_columns()

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
        reference_peak_ts: Optional[int],
        reference_current_ts: Optional[int],
        drop_from_peak: Optional[float],
        anchor_type: str,
        anchor_price: float,
        anchor_ts: int,
        anchor_pct_from_open: float,
        current_pct_from_open: float,
        move_from_anchor: float,
    ) -> None:
        await self._execute(
            """
            INSERT INTO alerts(symbol, alert_type, magnitude, ts, reference_open, reference_close, reference_low, reference_high, reference_peak_ts, reference_current_ts, drop_from_peak, anchor_type, anchor_price, anchor_ts, anchor_pct_from_open, current_pct_from_open, move_from_anchor)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
                reference_peak_ts,
                reference_current_ts,
                drop_from_peak,
                anchor_type,
                anchor_price,
                anchor_ts,
                anchor_pct_from_open,
                current_pct_from_open,
                move_from_anchor,
            ),
        )

    async def fetch_recent_alerts(self, limit: int = 50) -> List[dict]:
        cutoff_ms = int((time.time() - self.retention_seconds) * 1000)
        rows = await asyncio.to_thread(
            self._fetch_alert_rows,
            limit,
            cutoff_ms,
        )
        alerts: List[dict] = []
        for r in rows:
            (
                symbol,
                alert_type,
                magnitude,
                ts,
                reference_open,
                reference_close,
                reference_low,
                reference_high,
                reference_peak_ts,
                reference_current_ts,
                drop_from_peak,
                anchor_type,
                anchor_price,
                anchor_ts,
                anchor_pct_from_open,
                current_pct_from_open,
                move_from_anchor,
            ) = r
            anchor_type = anchor_type or ("peak" if alert_type == "rapid_drop" else "trough")
            anchor_price = anchor_price or (
                reference_high if alert_type == "rapid_drop" else reference_low
            )
            anchor_ts = anchor_ts or reference_peak_ts or ts
            move_from_anchor = move_from_anchor or drop_from_peak
            anchor_pct = anchor_pct_from_open
            current_pct = current_pct_from_open
            if anchor_pct is None and reference_open:
                anchor_pct = (anchor_price - reference_open) / reference_open
            if current_pct is None and reference_open:
                current_pct = (reference_close - reference_open) / reference_open
            alerts.append(
                {
                    "type": "alert",
                    "symbol": symbol.upper(),
                    "alert_type": alert_type,
                    "magnitude": magnitude,
                    "window_minutes": self.window_size_minutes,
                    "ts": ts,
                    "reference": {
                        "open": reference_open,
                        "close": reference_close,
                        "low": reference_low,
                        "high": reference_high,
                        "peak_price": reference_high,
                        "peak_ts": reference_peak_ts or ts,
                        "current_price": reference_close,
                        "current_ts": reference_current_ts or ts,
                        "drop_from_peak": drop_from_peak,
                        "anchor_type": anchor_type,
                        "anchor_price": anchor_price,
                        "anchor_ts": anchor_ts,
                        "anchor_pct_from_open": anchor_pct,
                        "current_pct_from_open": current_pct,
                        "move_from_anchor": move_from_anchor,
                    },
                }
            )
        return alerts

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

    async def _ensure_alert_columns(self) -> None:
        await asyncio.to_thread(self._ensure_alert_columns_sync)

    def _ensure_alert_columns_sync(self) -> None:
        conn = sqlite3.connect(self.path)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(alerts);")
        cols = {row[1] for row in cur.fetchall()}
        alters = []
        if "reference_peak_ts" not in cols:
            alters.append("ALTER TABLE alerts ADD COLUMN reference_peak_ts INTEGER;")
        if "reference_current_ts" not in cols:
            alters.append("ALTER TABLE alerts ADD COLUMN reference_current_ts INTEGER;")
        if "drop_from_peak" not in cols:
            alters.append("ALTER TABLE alerts ADD COLUMN drop_from_peak REAL;")
        if "anchor_type" not in cols:
            alters.append("ALTER TABLE alerts ADD COLUMN anchor_type TEXT;")
        if "anchor_price" not in cols:
            alters.append("ALTER TABLE alerts ADD COLUMN anchor_price REAL;")
        if "anchor_ts" not in cols:
            alters.append("ALTER TABLE alerts ADD COLUMN anchor_ts INTEGER;")
        if "anchor_pct_from_open" not in cols:
            alters.append("ALTER TABLE alerts ADD COLUMN anchor_pct_from_open REAL;")
        if "current_pct_from_open" not in cols:
            alters.append("ALTER TABLE alerts ADD COLUMN current_pct_from_open REAL;")
        if "move_from_anchor" not in cols:
            alters.append("ALTER TABLE alerts ADD COLUMN move_from_anchor REAL;")
        for stmt in alters:
            cur.execute(stmt)
        conn.commit()
        cur.close()
        conn.close()

    def _fetch_alert_rows(self, limit: int, cutoff_ms: int) -> List[Tuple]:
        conn = sqlite3.connect(self.path)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT symbol, alert_type, magnitude, ts, reference_open, reference_close, reference_low, reference_high, reference_peak_ts, reference_current_ts, drop_from_peak, anchor_type, anchor_price, anchor_ts, anchor_pct_from_open, current_pct_from_open, move_from_anchor
            FROM alerts
            WHERE ts >= ?
            ORDER BY ts DESC
            LIMIT ?;
            """,
            (cutoff_ms, limit),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows


async def retention_worker(store: SQLiteStore, interval_seconds: int = 600) -> None:
    """Periodically prunes data older than the retention horizon."""
    while True:
        cutoff_ms = int((time.time() - store.retention_seconds) * 1000)
        try:
            await store.prune_older_than(cutoff_ms)
        except Exception:
            import logging

            logging.exception("Failed to prune old data")
        await asyncio.sleep(interval_seconds)
