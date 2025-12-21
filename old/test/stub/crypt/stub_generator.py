from __future__ import annotations

import asyncio
import datetime as dt
import random
import time
from typing import Dict, Iterable
from zoneinfo import ZoneInfo

from utils.crypt.market import MarketMonitor


def build_stub_stats(
    open_price: float,
    current_price: float,
    threshold: float,
    alert_type: str,
    ts_ms: int,
    window_size_minutes: int,
) -> dict:
    if alert_type == "rapid_drop":
        peak_price = current_price * (1 + threshold + 0.001)
        trough_price = current_price * (1 - 0.001)
        drop_from_peak = (peak_price - current_price) / open_price
        rise_from_trough = (current_price - trough_price) / open_price
    else:
        trough_price = current_price * (1 - threshold - 0.001)
        peak_price = current_price * (1 + 0.001)
        rise_from_trough = (current_price - trough_price) / open_price
        drop_from_peak = (peak_price - current_price) / open_price
    return {
        "window_end": ts_ms,
        "change_close": (current_price - open_price) / open_price,
        "change_low": (trough_price - open_price) / open_price,
        "change_high": (peak_price - open_price) / open_price,
        "length": window_size_minutes,
        "reference_open": open_price,
        "reference_close": current_price,
        "reference_low": min(trough_price, current_price),
        "reference_high": max(peak_price, current_price),
        "peak_price": peak_price,
        "peak_ts": ts_ms,
        "peak_pct_from_open": (peak_price - open_price) / open_price,
        "trough_price": trough_price,
        "trough_ts": ts_ms,
        "trough_pct_from_open": (trough_price - open_price) / open_price,
        "current_price": current_price,
        "current_ts": ts_ms,
        "current_pct_from_open": (current_price - open_price) / open_price,
        "drop_from_peak": drop_from_peak,
        "rise_from_trough": rise_from_trough,
    }


async def stub_generator(
    monitor: MarketMonitor,
    symbols: Iterable[str],
    alert_thresholds: Iterable[float],
    timezone_keys: Dict[str, str],
    window_size_minutes: int,
    seed: int = 42,
) -> None:
    """Emit synthetic prices and alerts for local testing."""
    rng = random.Random(seed)
    symbols_list = [s.lower() for s in symbols]
    base_prices = {"btcusdt": 85000.0, "ethusdt": 3000.0}
    prices = {sym: base_prices.get(sym, 100.0) for sym in symbols_list}
    open_prices = dict(prices)
    for tz_key, tz_name in timezone_keys.items():
        day = dt.datetime.now(ZoneInfo(tz_name)).date()
        for sym in symbols_list:
            monitor.set_daily_open(tz_key, sym, day, prices[sym])
    last_alert_ms = 0
    thresholds = list(alert_thresholds)
    while True:
        ts_ms = int(time.time() * 1000)
        for sym in symbols_list:
            drift = prices[sym] * rng.uniform(-0.0006, 0.0006)
            prices[sym] = max(1.0, prices[sym] + drift)
            await monitor.publish_price(sym, prices[sym], ts_ms)
        if thresholds and ts_ms - last_alert_ms >= 12000:
            last_alert_ms = ts_ms
            sym = rng.choice(symbols_list)
            alert_type = rng.choice(["rapid_drop", "rapid_rebound"])
            threshold = rng.choice(thresholds)
            stats = build_stub_stats(
                open_price=open_prices[sym],
                current_price=prices[sym],
                threshold=threshold,
                alert_type=alert_type,
                ts_ms=ts_ms,
                window_size_minutes=window_size_minutes,
            )
            await monitor.emit_alert(alert_type, threshold, sym, stats, force=True)
        await asyncio.sleep(1)
