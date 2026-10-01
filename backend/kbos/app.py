"""FastAPI app: Pipecat SmallWebRTC signalling + REST + /ws + static."""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Request, Response
from loguru import logger
from pipecat.transports.smallwebrtc.request_handler import (
    IceCandidate,
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)

from kbos.config import settings
from kbos.voice.bot import run_bot
from kbos.voice.keypool import KeyPool


def create_app() -> FastAPI:
    pool = KeyPool(settings.sarvam_keys)
    webrtc = SmallWebRTCRequestHandler()
    pending: dict[str, dict[str, Any]] = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        asyncio.create_task(pool.probe())
        yield
        await webrtc.close()

    app = FastAPI(title="KBOS", lifespan=lifespan)
    app.state.pool = pool

    @app.post("/start")
    async def start(request: Request) -> dict[str, Any]:
        data = await request.json()
        session_id = str(uuid.uuid4())
        pending[session_id] = data.get("body") or {}
        return {"sessionId": session_id}

    @app.api_route("/sessions/{session_id}/api/offer", methods=["POST", "PATCH"])
    async def offer(session_id: str, request: Request, background_tasks: BackgroundTasks):
        if session_id not in pending:
            return Response("unknown session", status_code=404)
        data = await request.json()
        if request.method == "PATCH":
            await webrtc.handle_patch_request(
                SmallWebRTCPatchRequest(
                    pc_id=data["pc_id"],
                    candidates=[IceCandidate(**c) for c in data.get("candidates", [])],
                )
            )
            return {"status": "success"}
        body = pending[session_id]
        req = SmallWebRTCRequest(
            sdp=data["sdp"], type=data["type"], pc_id=data.get("pc_id"), restart_pc=data.get("restart_pc")
        )

        async def on_connection(connection) -> None:
            background_tasks.add_task(run_bot, connection, body, pool)

        return await webrtc.handle_web_request(request=req, webrtc_connection_callback=on_connection)

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "keys": pool.public_status()}

    logger.info("KBOS app ready")
    return app


app = create_app()
