"""/ws hub: typed events broadcast to every connected app and dashboard.

`publish` is synchronous so domain code can call it anywhere; delivery happens
on the event loop. Every non-telemetry event is also stored as an Event row
(the dashboard's activity feed).
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC
from typing import Any

from fastapi import WebSocket
from loguru import logger

from kbos import db
from kbos.models import Event

FEED_SKIP = {"telemetry"}


def iso(dt) -> str | None:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


class Hub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._queue: asyncio.Queue[str] | None = None
        self.sent: list[dict[str, Any]] = []  # last events (tests + debugging)

    def attach_loop(self) -> None:
        self._queue = asyncio.Queue()

    def publish(self, type_: str, data: dict[str, Any] | None = None, *, store: bool = True) -> None:
        at = db.now()
        msg = {"type": type_, "at": iso(at), "data": data or {}}
        if type_ not in FEED_SKIP:
            self.sent.append(msg)
            del self.sent[:-200]
            if store:
                with db.session() as s:
                    s.add(Event(type=type_, payload=data or {}, at=at))
                    s.commit()
        if self._queue is not None:
            self._queue.put_nowait(json.dumps(msg, default=str))

    async def run(self) -> None:
        assert self._queue is not None
        while True:
            text = await self._queue.get()
            dead = []
            for ws in list(self._clients):
                try:
                    await ws.send_text(text)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._clients.discard(ws)

    async def serve(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)
        logger.info(f"/ws client connected ({len(self._clients)})")
        try:
            while True:
                await ws.receive_text()  # clients don't send; this detects close
        except Exception:
            pass
        finally:
            self._clients.discard(ws)

    @property
    def client_count(self) -> int:
        return len(self._clients)


hub = Hub()
