from __future__ import annotations

import asyncio
import json
import logging

from utils.crypt.db import SQLiteStore


async def start_http_server(
    store: SQLiteStore, host: str, port: int, recent_limit: int = 50
) -> None:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_line = await reader.readline()
            if not request_line:
                writer.close()
                await writer.wait_closed()
                return
            try:
                method, path, _ = request_line.decode().strip().split(" ", 2)
            except ValueError:
                writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return
            while True:
                line = await reader.readline()
                if line in (b"\r\n", b"\n", b""):
                    break
            if method == "OPTIONS":
                headers = (
                    "HTTP/1.1 204 No Content\r\n"
                    "Access-Control-Allow-Origin: *\r\n"
                    "Access-Control-Allow-Methods: GET, OPTIONS\r\n"
                    "Access-Control-Allow-Headers: Content-Type\r\n"
                    "Access-Control-Max-Age: 600\r\n"
                    "\r\n"
                )
                writer.write(headers.encode())
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return
            if method != "GET":
                headers = (
                    "HTTP/1.1 405 Method Not Allowed\r\n"
                    "Access-Control-Allow-Origin: *\r\n"
                    "Access-Control-Allow-Methods: GET, OPTIONS\r\n"
                    "Access-Control-Allow-Headers: Content-Type\r\n"
                    "\r\n"
                )
                writer.write(headers.encode())
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return
            if path.startswith("/alerts/recent"):
                alerts = await store.fetch_recent_alerts(limit=recent_limit)
                body = json.dumps({"alerts": alerts}, separators=(",", ":")).encode()
                headers = (
                    "HTTP/1.1 200 OK\r\n"
                    "Content-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    "Access-Control-Allow-Origin: *\r\n"
                    "Access-Control-Allow-Methods: GET, OPTIONS\r\n"
                    "Access-Control-Allow-Headers: Content-Type\r\n"
                    "\r\n"
                )
                writer.write(headers.encode() + body)
            else:
                headers = (
                    "HTTP/1.1 404 Not Found\r\n"
                    "Access-Control-Allow-Origin: *\r\n"
                    "Access-Control-Allow-Methods: GET, OPTIONS\r\n"
                    "Access-Control-Allow-Headers: Content-Type\r\n"
                    "\r\n"
                )
                writer.write(headers.encode())
            await writer.drain()
        except Exception:
            logging.exception("HTTP handler error")
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    server = await asyncio.start_server(handle, host, port)
    logging.info("HTTP server listening on http://%s:%s", host, port)
    async with server:
        await server.serve_forever()
