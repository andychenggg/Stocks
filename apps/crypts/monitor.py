from __future__ import annotations

import asyncio
import logging
import threading

from django.conf import settings

from .binance import binance_listener
from .broadcaster import ChannelBroadcaster
from .config import (
    ALERT_DEDUP_SECONDS,
    ALERT_THRESHOLDS,
    AUTO_CREATE_SCHEMA,
    BINANCE_STREAM_URL,
    RETENTION_SECONDS,
    STUB_MODE,
    SYMBOLS,
    TIMEZONE_KEYS,
    WINDOW_SIZE_MINUTES,
)
from .db import PostgresStore, retention_worker
from .market import MarketMonitor
from .state import set_monitor
from .stub import stub_generator


_monitor_task = None
_monitor_thread = None
_monitor_lock = threading.Lock()


async def run_monitor() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    store = PostgresStore(
        retention_seconds=RETENTION_SECONDS,
        window_size_minutes=WINDOW_SIZE_MINUTES,
    )
    await store.init(auto_create_schema=AUTO_CREATE_SCHEMA)
    broadcaster = ChannelBroadcaster()
    monitor = MarketMonitor(
        store=store,
        broadcaster=broadcaster,
        symbols=SYMBOLS,
        window_size_minutes=WINDOW_SIZE_MINUTES,
        alert_thresholds=ALERT_THRESHOLDS,
        alert_dedup_seconds=ALERT_DEDUP_SECONDS,
        timezone_keys=TIMEZONE_KEYS,
    )
    set_monitor(monitor)
    listeners = [
        retention_worker(store),
    ]
    if STUB_MODE:
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


def start_monitor_background() -> None:
    loop = _get_running_loop()
    if loop:
        _start_in_loop(loop)
        return
    backend = settings.CHANNEL_LAYERS.get("default", {}).get("BACKEND", "")
    if backend == "channels.layers.InMemoryChannelLayer":
        logging.warning(
            "Crypto monitor not started: InMemory channel layer requires a running event loop."
        )
        return
    _start_in_thread()


async def ensure_monitor_started() -> None:
    loop = _get_running_loop()
    if not loop:
        return
    _start_in_loop(loop)


def _start_in_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _monitor_task
    with _monitor_lock:
        if (_monitor_task and not _monitor_task.done()) or (
            _monitor_thread and _monitor_thread.is_alive()
        ):
            return
        _monitor_task = loop.create_task(run_monitor())


def _start_in_thread() -> None:
    global _monitor_thread
    with _monitor_lock:
        if (_monitor_thread and _monitor_thread.is_alive()) or (
            _monitor_task and not _monitor_task.done()
        ):
            return
        _monitor_thread = threading.Thread(target=_run_monitor_thread, daemon=True)
        _monitor_thread.start()


def _run_monitor_thread() -> None:
    try:
        asyncio.run(run_monitor())
    except Exception:
        logging.exception("Crypto monitor stopped unexpectedly")


def _get_running_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None
