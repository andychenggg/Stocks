from __future__ import annotations

import datetime as dt
import json
import logging
import time
from collections import deque
from typing import Deque, Dict, Iterable, Optional, Tuple
from zoneinfo import ZoneInfo

from utils.crypt.db import ClosedKline, SQLiteStore


def pct_change(base: Optional[float], value: Optional[float]) -> Optional[float]:
    if base is None or value is None:
        return None
    if base == 0:
        return None
    return (value - base) / base


def now_ms() -> int:
    return int(time.time() * 1000)


class MarketMonitor:
    """Holds in-memory state for windows, alerting, and daily context."""

    def __init__(
        self,
        store: SQLiteStore,
        broadcaster,
        symbols: Iterable[str],
        window_size_minutes: int,
        alert_thresholds: Iterable[float],
        alert_dedup_seconds: int,
        timezone_keys: Dict[str, str],
    ) -> None:
        self.store = store
        self.broadcaster = broadcaster
        self.symbols = [s.lower() for s in symbols]
        self.window_size_minutes = window_size_minutes
        self.alert_thresholds = list(alert_thresholds)
        self.alert_dedup_seconds = alert_dedup_seconds
        self.timezone_keys = dict(timezone_keys)
        self.windows: Dict[str, Deque[ClosedKline]] = {
            s: deque(maxlen=window_size_minutes) for s in self.symbols
        }
        self.today_open_by_tz: Dict[str, Dict[str, Optional[float]]] = {
            tz: {s: None for s in self.symbols} for tz in self.timezone_keys
        }
        self.today_key_by_tz: Dict[str, Dict[str, Optional[dt.date]]] = {
            tz: {s: None for s in self.symbols} for tz in self.timezone_keys
        }
        self.last_alert_at: Dict[Tuple[str, str, float], float] = {}
        self.last_price: Dict[str, Optional[float]] = {s: None for s in self.symbols}

    async def handle_stream_message(self, raw: str) -> None:
        payload = json.loads(raw)
        data = payload.get("data", {})
        event_type = data.get("e")
        if event_type == "kline":
            k = data.get("k", {})
            if not k.get("x"):  # ignore in-progress klines
                return
            symbol = data.get("s", "").lower()
            if symbol not in self.windows:
                return
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
            if symbol not in self.last_price:
                return
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

    def set_daily_open(self, tz_key: str, symbol: str, day: dt.date, open_price: float) -> None:
        sym = symbol.lower()
        if tz_key not in self.today_key_by_tz or sym not in self.today_key_by_tz[tz_key]:
            return
        self.today_key_by_tz[tz_key][sym] = day
        self.today_open_by_tz[tz_key][sym] = open_price

    async def publish_price(self, symbol: str, price: float, ts_ms: int) -> None:
        await self._publish_price(symbol, price, ts_ms)

    async def emit_alert(
        self,
        alert_type: str,
        threshold: float,
        symbol: str,
        stats: dict,
        force: bool = False,
    ) -> None:
        if force:
            self.last_alert_at[(symbol, alert_type, threshold)] = 0
        await self._emit_alert(alert_type, threshold, symbol, stats)

    def _update_daily_open(self, kline: ClosedKline) -> None:
        for tz_key, tz_name in self.timezone_keys.items():
            tz_info = ZoneInfo(tz_name)
            day = dt.datetime.fromtimestamp(kline.open_time / 1000, tz_info).date()
            if self.today_key_by_tz[tz_key][kline.symbol] != day:
                self.today_key_by_tz[tz_key][kline.symbol] = day
                self.today_open_by_tz[tz_key][kline.symbol] = kline.open

    def _compute_window_stats(self, window: Deque[ClosedKline]) -> Optional[dict]:
        if len(window) < self.window_size_minutes:
            return None
        open_base = window[0].open
        if open_base == 0:
            return None
        latest = window[-1]
        peak = max(window, key=lambda k: k.high)
        trough = min(window, key=lambda k: k.low)
        close_last = latest.close
        drop_from_peak = (peak.high - close_last) / open_base
        rise_from_trough = (close_last - trough.low) / open_base
        return {
            "window_end": window[-1].close_time,
            "change_close": (close_last - open_base) / open_base,
            "change_low": (min(k.low for k in window) - open_base) / open_base,
            "change_high": (peak.high - open_base) / open_base,
            "length": len(window),
            "reference_open": open_base,
            "reference_close": close_last,
            "reference_low": min(k.low for k in window),
            "reference_high": peak.high,
            "peak_price": peak.high,
            "peak_ts": peak.close_time,
            "peak_pct_from_open": (peak.high - open_base) / open_base,
            "trough_price": trough.low,
            "trough_ts": trough.close_time,
            "trough_pct_from_open": (trough.low - open_base) / open_base,
            "current_price": close_last,
            "current_ts": latest.close_time,
            "current_pct_from_open": (close_last - open_base) / open_base,
            "drop_from_peak": drop_from_peak,
            "rise_from_trough": rise_from_trough,
        }

    async def _check_alerts(
        self, symbol: str, window: Deque[ClosedKline], stats: dict
    ) -> None:
        for threshold in self.alert_thresholds:
            if stats.get("drop_from_peak") is None:
                continue
            if stats["drop_from_peak"] >= threshold:
                await self._emit_alert("rapid_drop", threshold, symbol, stats)
            if stats["rise_from_trough"] >= threshold:
                await self._emit_alert("rapid_rebound", threshold, symbol, stats)

    async def _emit_alert(
        self, alert_type: str, threshold: float, symbol: str, stats: dict
    ) -> None:
        key = (symbol, alert_type, threshold)
        now_sec = time.time()
        last_at = self.last_alert_at.get(key, 0)
        if now_sec - last_at < self.alert_dedup_seconds:
            return
        self.last_alert_at[key] = now_sec
        ts_ms = stats.get("current_ts", stats["window_end"])
        if alert_type == "rapid_drop":
            anchor_price = stats["peak_price"]
            anchor_ts = stats["peak_ts"]
            anchor_pct = stats["peak_pct_from_open"]
            move_from_anchor = stats["drop_from_peak"]
        else:
            anchor_price = stats["trough_price"]
            anchor_ts = stats["trough_ts"]
            anchor_pct = stats["trough_pct_from_open"]
            move_from_anchor = stats["rise_from_trough"]
        payload = {
            "type": "alert",
            "symbol": symbol.upper(),
            "alert_type": alert_type,
            "magnitude": threshold,
            "window_minutes": self.window_size_minutes,
            "ts": ts_ms,
            "reference": {
                "open": stats["reference_open"],
                "close": stats["current_price"],
                "low": stats["reference_low"],
                "high": stats["peak_price"],
                "peak_price": stats["peak_price"],
                "peak_ts": stats["peak_ts"],
                "current_price": stats["current_price"],
                "current_ts": stats["current_ts"],
                "drop_from_peak": stats["drop_from_peak"],
                "rise_from_trough": stats["rise_from_trough"],
                "anchor_type": "peak" if alert_type == "rapid_drop" else "trough",
                "anchor_price": anchor_price,
                "anchor_ts": anchor_ts,
                "anchor_pct_from_open": anchor_pct,
                "current_pct_from_open": stats["current_pct_from_open"],
                "move_from_anchor": move_from_anchor,
            },
        }
        await self.store.insert_alert(
            symbol=symbol,
            alert_type=alert_type,
            magnitude=threshold,
            ts=ts_ms,
            reference_open=stats["reference_open"],
            reference_close=stats["current_price"],
            reference_low=stats["reference_low"],
            reference_high=stats["peak_price"],
            reference_peak_ts=stats.get("peak_ts"),
            reference_current_ts=stats.get("current_ts"),
            drop_from_peak=stats.get("drop_from_peak"),
            anchor_type="peak" if alert_type == "rapid_drop" else "trough",
            anchor_price=anchor_price,
            anchor_ts=anchor_ts,
            anchor_pct_from_open=anchor_pct,
            current_pct_from_open=stats["current_pct_from_open"],
            move_from_anchor=move_from_anchor,
        )
        await self.broadcaster.broadcast(payload)
        logging.info("Alert emitted: %s", payload)

    async def _publish_price(self, symbol: str, price: float, ts_ms: int) -> None:
        self.last_price[symbol] = price
        day_open_map = {
            tz_key: self.today_open_by_tz[tz_key].get(symbol) for tz_key in self.timezone_keys
        }
        pct_map = {tz_key: pct_change(day_open_map[tz_key], price) for tz_key in self.timezone_keys}
        payload = {
            "type": "price",
            "symbol": symbol.upper(),
            "price": price,
            "day_open": day_open_map,
            "pct_from_day_open": pct_map,
            # legacy keys for backward compatibility (UTC)
            "today_open": day_open_map.get("utc"),
            "pct_from_today_open": pct_map.get("utc"),
            "ts": ts_ms,
        }
        await self.broadcaster.broadcast(payload)

    def snapshot(self) -> dict:
        return {
            sym.upper(): {
                "price": self.last_price.get(sym),
                "day_open": {
                    tz_key: self.today_open_by_tz[tz_key].get(sym)
                    for tz_key in self.timezone_keys
                },
                "pct_from_day_open": {
                    tz_key: pct_change(self.today_open_by_tz[tz_key].get(sym), self.last_price.get(sym))
                    for tz_key in self.timezone_keys
                },
                "today_open": self.today_open_by_tz.get("utc", {}).get(sym),
                "pct_from_today_open": pct_change(
                    self.today_open_by_tz.get("utc", {}).get(sym), self.last_price.get(sym)
                ),
            }
            for sym in self.symbols
        }
