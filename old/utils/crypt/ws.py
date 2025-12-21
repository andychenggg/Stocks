from __future__ import annotations

import asyncio
import json
import logging
from typing import List, Optional

import websockets
from websockets.server import WebSocketServerProtocol


class BroadcastHub:
    """Manages outbound WebSocket clients for real-time updates."""

    def __init__(self) -> None:
        self.clients: set[WebSocketServerProtocol] = set()

    async def register(self, ws: WebSocketServerProtocol) -> None:
        self.clients.add(ws)

    async def unregister(self, ws: WebSocketServerProtocol) -> None:
        self.clients.discard(ws)

    async def send_snapshot(
        self, ws: WebSocketServerProtocol, snapshot: dict, alerts: Optional[List[dict]] = None
    ) -> None:
        try:
            await ws.send(json.dumps({"type": "snapshot", "data": snapshot, "alerts": alerts or []}))
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


async def start_client_ws_server(
    monitor,
    broadcaster: BroadcastHub,
    host: str,
    port: int,
    recent_limit: int = 50,
) -> None:
    async def handler(ws: WebSocketServerProtocol) -> None:
        await broadcaster.register(ws)
        alerts = await monitor.store.fetch_recent_alerts(limit=recent_limit)
        await broadcaster.send_snapshot(ws, monitor.snapshot(), alerts)
        try:
            async for _ in ws:
                pass
        finally:
            await broadcaster.unregister(ws)

    server = await websockets.serve(
        handler, host, port, ping_interval=20, ping_timeout=20
    )
    logging.info("Client WS server listening on ws://%s:%s", host, port)
    await server.wait_closed()
