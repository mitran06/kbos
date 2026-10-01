"""Voice session registry: SmallWebRTC signalling and the per-phone bots."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import BackgroundTasks
from loguru import logger
from pipecat.transports.smallwebrtc.request_handler import (
    IceCandidate,
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)

from kbos.voice.keypool import KeyPool


@dataclass
class LiveSession:
    id: str
    body: dict
    person_name: str = ""
    task: asyncio.Task | None = None
    state: dict[str, Any] = field(default_factory=dict)


class SessionManager:
    def __init__(self) -> None:
        self.pool: KeyPool | None = None
        self.handler = SmallWebRTCRequestHandler()
        self.pending: dict[str, dict] = {}
        self.live: dict[str, LiveSession] = {}
        self.latency_log: list[dict] = []

    def register(self, body: dict) -> str:
        sid = str(uuid.uuid4())
        self.pending[sid] = body
        return sid

    async def offer(self, session_id: str, data: dict, background_tasks: BackgroundTasks) -> dict | None:
        body = self.pending.get(session_id)
        if body is None:
            return None
        req = SmallWebRTCRequest(
            sdp=data["sdp"], type=data["type"], pc_id=data.get("pc_id"), restart_pc=data.get("restart_pc")
        )

        async def on_connection(connection) -> None:
            from kbos.voice.bot import run_bot

            live = LiveSession(id=session_id, body=body)
            self.live[session_id] = live

            async def runner() -> None:
                try:
                    await run_bot(connection, live, self)
                except Exception:
                    logger.exception("voice session crashed")
                finally:
                    self.live.pop(session_id, None)

            live.task = asyncio.create_task(runner())

        return await self.handler.handle_web_request(request=req, webrtc_connection_callback=on_connection)

    async def patch(self, data: dict) -> None:
        await self.handler.handle_patch_request(
            SmallWebRTCPatchRequest(
                pc_id=data["pc_id"], candidates=[IceCandidate(**c) for c in data.get("candidates", [])]
            )
        )

    def record_latency(self, entry: dict) -> None:
        self.latency_log.append(entry)
        del self.latency_log[:-50]

    def public(self) -> list[dict]:
        return [
            {"id": s.id[:8], "person": s.person_name, "listening": s.state.get("listening", False)}
            for s in self.live.values()
        ]

    async def close(self) -> None:
        for s in list(self.live.values()):
            if s.task:
                s.task.cancel()
        self.live.clear()
        self.pending.clear()


sessions = SessionManager()
