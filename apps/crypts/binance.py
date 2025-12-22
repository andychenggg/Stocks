from __future__ import annotations

import asyncio
import logging

import websockets


async def binance_listener(monitor, stream_url: str) -> None:
    """Consumes Binance combined streams with reconnect logic."""
    backoff_sec = 3
    while True:
        try:
            logging.info("Connecting to Binance stream: %s", stream_url)
            async with websockets.connect(
                stream_url, ping_interval=20, ping_timeout=20
            ) as ws:
                logging.info("Connected to Binance.")
                async for message in ws:
                    await monitor.handle_stream_message(message)
        except Exception:
            logging.exception("Binance stream failed; retrying in %ss", backoff_sec)
            await asyncio.sleep(backoff_sec)
