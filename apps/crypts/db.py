from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from django.conf import settings
from django.db import close_old_connections, connection


@dataclass
class ClosedKline:
    symbol: str
    open_time: int
    close_time: int
    open: float
    high: float
    low: float
    close: float


class PostgresStore:
    """Persistence layer for market data and alerts (PostgreSQL)."""

    def __init__(self, retention_seconds: int, window_size_minutes: int) -> None:
        self.retention_seconds = retention_seconds
        self.window_size_minutes = window_size_minutes

    async def init(self, auto_create_schema: bool = False) -> None:
        if auto_create_schema:
            await self._apply_schema()
        if await self._table_exists("alerts"):
            await self._ensure_alert_columns()

    async def insert_kline(self, k: ClosedKline) -> None:
        await self._execute(
            """
            INSERT INTO klines(symbol, open_time, close_time, open, high, low, close)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, open_time) DO UPDATE SET
                close_time = EXCLUDED.close_time,
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close;
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
            INSERT INTO window_stats(symbol, window_end, change_close, change_low, change_high, length)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, window_end) DO UPDATE SET
                change_close = EXCLUDED.change_close,
                change_low = EXCLUDED.change_low,
                change_high = EXCLUDED.change_high,
                length = EXCLUDED.length;
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
            INSERT INTO alerts(
                symbol, alert_type, magnitude, ts, reference_open, reference_close,
                reference_low, reference_high, reference_peak_ts, reference_current_ts,
                drop_from_peak, anchor_type, anchor_price, anchor_ts, anchor_pct_from_open,
                current_pct_from_open, move_from_anchor
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
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
        rows = await asyncio.to_thread(self._fetch_alert_rows, limit, cutoff_ms)
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
        await self._execute("DELETE FROM klines WHERE close_time < %s;", (cutoff_ms,))
        await self._execute("DELETE FROM window_stats WHERE window_end < %s;", (cutoff_ms,))
        await self._execute("DELETE FROM alerts WHERE ts < %s;", (cutoff_ms,))

    async def _execute(self, query: str, params: Tuple = ()) -> None:
        await asyncio.to_thread(self._execute_sync, query, params)

    def _execute_sync(self, query: str, params: Tuple) -> None:
        close_old_connections()
        with connection.cursor() as cursor:
            cursor.execute(query, params)
        close_old_connections()

    async def _table_exists(self, table: str) -> bool:
        return await asyncio.to_thread(self._table_exists_sync, table)

    def _table_exists_sync(self, table: str) -> bool:
        close_old_connections()
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass(%s);", (f"public.{table}",))
            exists = cursor.fetchone()[0] is not None
        close_old_connections()
        return exists

    async def _ensure_alert_columns(self) -> None:
        await asyncio.to_thread(self._ensure_alert_columns_sync)

    def _ensure_alert_columns_sync(self) -> None:
        close_old_connections()
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS reference_peak_ts BIGINT;")
            cursor.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS reference_current_ts BIGINT;")
            cursor.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS drop_from_peak DOUBLE PRECISION;")
            cursor.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS anchor_type TEXT;")
            cursor.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS anchor_price DOUBLE PRECISION;")
            cursor.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS anchor_ts BIGINT;")
            cursor.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS anchor_pct_from_open DOUBLE PRECISION;")
            cursor.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS current_pct_from_open DOUBLE PRECISION;")
            cursor.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS move_from_anchor DOUBLE PRECISION;")
        close_old_connections()

    async def _apply_schema(self) -> None:
        await asyncio.to_thread(self._apply_schema_sync)

    def _apply_schema_sync(self) -> None:
        schema_path = Path(settings.BASE_DIR) / "sql" / "create-database-01-crypt.sql"
        if not schema_path.exists():
            return
        sql = schema_path.read_text(encoding="utf-8")
        statements = []
        for line in sql.splitlines():
            if line.strip().startswith("--"):
                continue
            statements.append(line)
        cleaned = "\n".join(statements)
        for stmt in cleaned.split(";"):
            if stmt.strip():
                self._execute_sync(stmt, ())

    def _fetch_alert_rows(self, limit: int, cutoff_ms: int) -> List[Tuple]:
        close_old_connections()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT symbol, alert_type, magnitude, ts, reference_open, reference_close,
                       reference_low, reference_high, reference_peak_ts, reference_current_ts,
                       drop_from_peak, anchor_type, anchor_price, anchor_ts,
                       anchor_pct_from_open, current_pct_from_open, move_from_anchor
                FROM alerts
                WHERE ts >= %s
                ORDER BY ts DESC
                LIMIT %s;
                """,
                (cutoff_ms, limit),
            )
            rows = cursor.fetchall()
        close_old_connections()
        return rows


async def retention_worker(store: PostgresStore, interval_seconds: int = 600) -> None:
    """Periodically prunes data older than the retention horizon."""
    while True:
        cutoff_ms = int((time.time() - store.retention_seconds) * 1000)
        try:
            await store.prune_older_than(cutoff_ms)
        except Exception:
            import logging

            logging.exception("Failed to prune old data")
        await asyncio.sleep(interval_seconds)
