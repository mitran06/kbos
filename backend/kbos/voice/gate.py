"""STT gate: Sarvam realtime STT that only bills while the orb is listening.

- Closed gate: no socket, no audio leaves the laptop.
- Opening the gate connects lazily. Audio that arrives while the socket is
  coming up is buffered (about 2 s) so the first words aren't lost.
- With manual endpointing the pipeline's VAD marks each utterance. Between
  utterances audio is held in a short pre-roll ring instead of being sent, and
  is flushed right after `speech_start`, so the first syllable ("KB, ...")
  survives VAD's start delay and silence is never billed.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from typing import Any

import numpy as np
from loguru import logger
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    Frame,
    InputAudioRawFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessorSetup
from pipecat.services.sarvam._sdk import sdk_headers
from pipecat.services.sarvam.stt import SarvamRealtimeSTTService
from pipecat.services.websocket_service import WebsocketService
from websockets.protocol import State

PRE_ROLL_S = 0.6
ECHO_TAIL_S = 0.9
CONNECT_BUFFER_S = 2.0


class GatedSarvamSTT(SarvamRealtimeSTTService):
    def __init__(self, *, keyterms: list[str] | None = None, **kwargs: Any) -> None:
        super().__init__(endpointing="manual", **kwargs)
        self._keyterms = keyterms or []
        self._gate_open = False
        self._in_speech = False
        self._ring: deque[bytes] = deque()
        self._ring_bytes = 0
        self._connecting: asyncio.Task | None = None
        self._keepalive: asyncio.Task | None = None
        self.sent_bytes = 0  # audio actually sent to Sarvam (billing proxy)
        self._bot_speaking = False
        self._echo_until = 0.0
        self._stats = [0, 0]
        self._peak = 0
        self._stats_at = 0.0

    def _hearing_self(self) -> bool:
        if self._bot_speaking or time.monotonic() < self._echo_until:
            if self._in_speech:
                self._in_speech = False  # drop any half-heard echo utterance
            self._clear_ring()
            return True
        return False

    # -- gate ---------------------------------------------------------------

    @property
    def gate_open(self) -> bool:
        return self._gate_open

    async def open_gate(self) -> None:
        if self._gate_open:
            return
        self._gate_open = True
        self._in_speech = False
        self._clear_ring()
        self._ensure_connecting()
        if not self._keepalive:
            self._keepalive = self.create_task(self._keepalive_loop())
        logger.info("stt gate open")

    def _ensure_connecting(self) -> None:
        if not self._is_websocket_open() and not self._connecting:
            self._connecting = self.create_task(self._lazy_connect())

    async def _keepalive_loop(self) -> None:
        # Sarvam drops a realtime socket that hears nothing for ~2 s; we hold audio between
        # utterances (no billing), so keep it alive with pings instead.
        while True:
            await asyncio.sleep(1.0)
            if self._gate_open and not self._in_speech and self._is_websocket_open():
                try:
                    await self._send_json({"event": "ping"})
                except Exception:
                    pass

    async def close_gate(self) -> None:
        if not self._gate_open:
            return
        self._gate_open = False
        self._in_speech = False
        self._clear_ring()
        for attr in ("_connecting", "_keepalive"):
            task = getattr(self, attr)
            if task:
                await self.cancel_task(task)
                setattr(self, attr, None)
        await self._disconnect()
        logger.info(f"stt gate closed (sent {self.sent_bytes / 32000:.1f}s audio so far)")

    async def _lazy_connect(self) -> None:
        try:
            await self._connect()
        finally:
            self._connecting = None
        if self._is_websocket_open() and not self.is_usable:
            await self.set_usable(True)
        if self._is_websocket_open() and self._in_speech:
            # speech started while connecting: replay what we held
            await self._send_json({"event": "speech_start"})
            await self._flush_ring()

    async def _connect_websocket(self):
        """Retry transient gateway failures (Sarvam sometimes answers 404 for a moment) before
        letting the parent report a connection error."""
        for attempt in range(4):
            if self._websocket and self._websocket.state is State.OPEN:
                return
            try:
                self._websocket = await self._websocket_connect(
                    self._build_ws_url(),
                    additional_headers={"API-SUBSCRIPTION-KEY": self._api_key},
                    user_agent_header=sdk_headers()["User-Agent"],
                )
                await self._call_event_handler("on_connected")
                return
            except Exception as e:
                self._websocket = None
                if not self._gate_open:
                    return
                logger.warning(f"sarvam stt connect failed ({e}); retry {attempt + 1}")
                await asyncio.sleep(0.3 * (attempt + 1))
        # Don't let the parent file a transient 404 as a permanent error: the next utterance
        # (or the next listen.start) tries again.
        logger.error("sarvam stt: could not connect; will retry on the next utterance")

    # -- pipecat hooks ----------------------------------------------------------

    async def setup(self, setup: FrameProcessorSetup):
        # Skip the parent's eager connect; the gate connects on demand.
        await super(SarvamRealtimeSTTService, self).setup(setup)

    def _query_params(self) -> dict[str, Any]:
        params = super()._query_params()
        if self._keyterms and str(self._settings.model).startswith("saaras:v4"):
            params["keyterms"] = json.dumps(self._keyterms[:50])
        return params

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        if isinstance(frame, BotStartedSpeakingFrame):
            self._bot_speaking = True
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._bot_speaking = False
            self._echo_until = time.monotonic() + ECHO_TAIL_S
        if isinstance(frame, InputAudioRawFrame):
            self._stats[0] += 1
            self._peak = max(self._peak, int(np.sqrt(np.mean(np.frombuffer(frame.audio, dtype=np.int16).astype(np.float32) ** 2))))
            now = time.monotonic()
            if self._gate_open and now - self._stats_at > 5:
                logger.debug(f"stt gate audio: {self._stats[0]} frames, {self._stats[1]} dropped as echo, peak rms {self._peak}, bot_speaking={self._bot_speaking}")
                self._stats, self._stats_at, self._peak = [0, 0], now, 0
        if isinstance(frame, InputAudioRawFrame) and self._gate_open and self._hearing_self():
            self._stats[1] += 1
        if isinstance(frame, InputAudioRawFrame) and (not self._gate_open or self._hearing_self()):
            # Closed gate: nothing reaches STT (no billing) and room noise can't open a user turn.
            # While KB speaks (and a short tail after) the phone speaker leaks into its mic and KB
            # would interrupt itself, so it's half-duplex: the Stop button is how you cut KB off.
            # Downstream still gets *silence*, not nothing: if VAD stopped receiving frames mid-
            # utterance it would stay stuck in "speaking" and never report the next speech start.
            frame.audio = bytes(len(frame.audio))
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, VADUserStartedSpeakingFrame):
            await self._speech_started()
            # let the base class see the frame for metrics, minus its own speech_start
            await super(SarvamRealtimeSTTService, self).process_frame(frame, direction)
            return
        if isinstance(frame, VADUserStoppedSpeakingFrame):
            await self._speech_stopped()
            await super(SarvamRealtimeSTTService, self).process_frame(frame, direction)
            return
        await super().process_frame(frame, direction)

    async def _speech_started(self) -> None:
        logger.debug(f"stt gate: vad start (gate_open={self._gate_open}, socket={self._is_websocket_open()})")
        if not self._gate_open:
            return
        self._in_speech = True
        if self._is_websocket_open():
            await self._send_json({"event": "speech_start"})
            await self._flush_ring()
        else:
            self._ensure_connecting()  # audio is held until the socket is back

    async def _receive_task_handler(self, report_error):
        # The parent marks the service unusable when its receive loop ends; ours reconnects on
        # demand, so end the loop without that (and finish any half-heard utterance).
        await WebsocketService._receive_task_handler(self, report_error)
        await self._complete_active_utterance()

    async def _maybe_try_reconnect(self, error_message, report_error, error=None) -> bool:
        """A dropped socket is not fatal here: end the receive loop quietly and let the next
        utterance reconnect lazily (with its audio held), instead of marking STT unusable."""
        if not self._disconnecting:
            logger.warning(f"sarvam stt socket dropped ({error or error_message}); will reconnect on demand")
        self._websocket = None
        self._receive_task = None
        if self._gate_open and self._in_speech:
            self._ensure_connecting()
        return False

    async def _speech_stopped(self) -> None:
        logger.debug(f"stt gate: vad stop (in_speech={self._in_speech})")
        if not self._gate_open or not self._in_speech:
            return
        self._in_speech = False
        if self._is_websocket_open():
            await self._flush_audio_buffer()
            await self._send_json({"event": "speech_end"})

    async def run_stt(self, audio: bytes):
        if not audio or not self._gate_open:
            yield None
            return
        if self._in_speech and self._is_websocket_open():
            self.sent_bytes += len(audio)
            async for f in super().run_stt(audio):
                yield f
            return
        self._hold(audio, CONNECT_BUFFER_S if self._in_speech else PRE_ROLL_S)
        yield None

    # -- ring ------------------------------------------------------------------

    def _hold(self, audio: bytes, max_s: float) -> None:
        self._ring.append(audio)
        self._ring_bytes += len(audio)
        limit = int(max_s * self.sample_rate * 2)
        while self._ring_bytes > limit and self._ring:
            self._ring_bytes -= len(self._ring.popleft())

    def _clear_ring(self) -> None:
        self._ring.clear()
        self._ring_bytes = 0

    async def _flush_ring(self) -> None:
        pending = b"".join(self._ring)
        self._clear_ring()
        if pending:
            self.sent_bytes += len(pending)
            async for _ in super().run_stt(pending):
                pass
