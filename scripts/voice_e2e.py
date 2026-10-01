"""Headless SmallWebRTC client: talks to KB like the phone does.

Hits /start + the offer endpoint, streams WAVs at real-time pace over an aiortc
audio track, records KB's audio and every RTVI message, and prints a per-turn
summary (what STT heard, what KB said, which tools ran, voice-to-voice latency).

Usage (from backend/):
  uv run python ../scripts/voice_e2e.py --wav tests/audio/en_open.wav --wav tests/audio/hi_hello.wav
  uv run python ../scripts/voice_e2e.py --body '{"person_id": 3}' --listen --wav ...
Costs Sarvam credits (STT+LLM+TTS) per turn.
"""

from __future__ import annotations

import argparse
import asyncio
import fractions
import json
import time
import uuid
import wave
from pathlib import Path

import httpx
import numpy as np
from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription
from av import AudioFrame

RATE = 16000
FRAME_MS = 20
SAMPLES = RATE * FRAME_MS // 1000


class WavTrack(MediaStreamTrack):
    """Mic stand-in: silence, or a queued WAV played at real-time pace."""

    kind = "audio"

    def __init__(self) -> None:
        super().__init__()
        self._pcm = np.zeros(0, dtype=np.int16)
        self._pts = 0
        self._start: float | None = None
        self.done = asyncio.Event()
        self.done.set()

    def play(self, path: Path) -> float:
        with wave.open(str(path)) as w:
            assert w.getframerate() == RATE and w.getnchannels() == 1, "need 16 kHz mono"
            self._pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        self.done.clear()
        return len(self._pcm) / RATE

    async def recv(self) -> AudioFrame:
        if self._start is None:
            self._start = time.monotonic()
        target = self._start + self._pts / RATE
        delay = target - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        if len(self._pcm):
            chunk, self._pcm = self._pcm[:SAMPLES], self._pcm[SAMPLES:]
            if len(chunk) < SAMPLES:
                chunk = np.concatenate([chunk, np.zeros(SAMPLES - len(chunk), dtype=np.int16)])
            if not len(self._pcm):
                self.done.set()
        else:
            chunk = np.zeros(SAMPLES, dtype=np.int16)
        frame = AudioFrame.from_ndarray(chunk.reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate = RATE
        frame.pts = self._pts
        frame.time_base = fractions.Fraction(1, RATE)
        self._pts += SAMPLES
        return frame


class Session:
    def __init__(self, server: str, body: dict, verbose: bool) -> None:
        self.server = server.rstrip("/")
        self.body = body
        self.verbose = verbose
        self.pc = RTCPeerConnection()
        self.mic = WavTrack()
        self.events: list[tuple[float, dict]] = []
        self.bot_audio_at: list[float] = []  # monotonic times of loud bot audio frames
        self.bot_ready = asyncio.Event()
        self.channel = None

    def log(self, msg: dict) -> None:
        self.events.append((time.monotonic(), msg))
        if self.verbose:
            t = msg.get("type")
            if t not in ("bot-output", "metrics", "bot-tts-text", "bot-llm-text", "user-speaking", "bot-speaking"):
                print("  <-", json.dumps(msg, ensure_ascii=False)[:300])

    def send(self, type_: str, data: dict | None = None) -> None:
        msg = {"id": uuid.uuid4().hex[:8], "label": "rtvi-ai", "type": type_, "data": data or {}}
        self.channel.send(json.dumps(msg))

    def client_message(self, t: str, d: dict | None = None) -> None:
        self.send("client-message", {"t": t, "d": d or {}})

    async def connect(self) -> None:
        self.pc.addTrack(self.mic)
        self.channel = self.pc.createDataChannel("rtvi-ai", ordered=True)

        @self.channel.on("message")
        def on_message(raw):
            if isinstance(raw, str) and raw.startswith("ping"):
                return
            msg = json.loads(raw)
            if msg.get("type") == "bot-ready":
                self.bot_ready.set()
            self.log(msg)

        @self.pc.on("track")
        def on_track(track):
            asyncio.ensure_future(self._drain(track))

        async with httpx.AsyncClient(timeout=20) as http:
            r = await http.post(f"{self.server}/start", json={"transport": "webrtc", "body": self.body})
            r.raise_for_status()
            sid = r.json()["sessionId"]
            await self.pc.setLocalDescription(await self.pc.createOffer())
            r = await http.post(
                f"{self.server}/sessions/{sid}/api/offer",
                json={"sdp": self.pc.localDescription.sdp, "type": "offer"},
            )
            r.raise_for_status()
            ans = r.json()
            await self.pc.setRemoteDescription(RTCSessionDescription(sdp=ans["sdp"], type=ans["type"]))

        for _ in range(100):
            if self.channel.readyState == "open":
                break
            await asyncio.sleep(0.1)
        asyncio.ensure_future(self._keepalive())
        self.send("client-ready", {"version": "2.1.0", "about": {"library": "voice_e2e"}})
        await asyncio.wait_for(self.bot_ready.wait(), 20)

    async def _keepalive(self) -> None:
        while self.pc.connectionState not in ("closed", "failed"):
            try:
                self.channel.send("ping: " + str(time.time()))
            except Exception:
                return
            await asyncio.sleep(1)

    async def _drain(self, track) -> None:
        while True:
            try:
                frame = await track.recv()
            except Exception:
                return
            pcm = frame.to_ndarray().astype(np.float32)
            if np.sqrt(np.mean(pcm**2)) > 300:
                self.bot_audio_at.append(time.monotonic())

    async def quiet(self, gap: float = 1.2, timeout: float = 30) -> None:
        """Wait until KB has made no sound for `gap` seconds."""
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            last = self.bot_audio_at[-1] if self.bot_audio_at else 0
            if time.monotonic() - last > gap and time.monotonic() - t0 > gap:
                return
            await asyncio.sleep(0.1)

    async def turn(self, wav: Path, wait: float = 25) -> dict:
        n_events = len(self.events)
        secs = self.mic.play(wav)
        await self.mic.done.wait()
        end_of_speech = time.monotonic()
        # first bot audio after the user finished
        first_audio = None
        t0 = time.monotonic()
        while time.monotonic() - t0 < wait:
            later = [t for t in self.bot_audio_at if t > end_of_speech]
            if later:
                first_audio = later[0]
                break
            await asyncio.sleep(0.05)
        await self.quiet()
        return self._summary(wav.name, secs, n_events, end_of_speech, first_audio)

    async def text_turn(self, text: str, wait: float = 25) -> dict:
        n_events = len(self.events)
        sent = time.monotonic()
        self.client_message("text.input", {"text": text})
        first_audio = None
        t0 = time.monotonic()
        while time.monotonic() - t0 < wait:
            later = [t for t in self.bot_audio_at if t > sent]
            if later:
                first_audio = later[0]
                break
            await asyncio.sleep(0.05)
        await self.quiet()
        return self._summary(f"text:{text}", 0, n_events, sent, first_audio)

    def _summary(self, name: str, secs: float, n_events: int, t_end: float, first_audio: float | None) -> dict:
        evs = [m for _, m in self.events[n_events:]]
        heard = [m["data"]["text"] for m in evs if m.get("type") == "user-transcription" and m["data"].get("final")]
        said = [
            m["data"]["text"]
            for m in evs
            if m.get("type") == "bot-output" and m["data"].get("spoken_status") in (None, "completed")
            and m["data"].get("aggregated_by") == "sentence"
        ]
        tools = [
            m["data"].get("function_name")
            for m in evs
            if m.get("type") == "llm-function-call-started"
        ]
        server = [m["data"] for m in evs if m.get("type") == "server-message"]
        return {
            "turn": name,
            "audio_s": round(secs, 1),
            "heard": " ".join(heard),
            "said": " ".join(said),
            "tools": tools,
            "server_messages": [s.get("type") for s in server],
            "v2v_s": round(first_audio - t_end, 2) if first_audio else None,
        }

    async def close(self) -> None:
        await self.pc.close()


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://127.0.0.1:7860")
    ap.add_argument("--body", default='{"device_id": "e2e"}')
    ap.add_argument("--wav", action="append", default=[])
    ap.add_argument("--text", action="append", default=[])
    ap.add_argument("--listen", action="store_true", help="send listen.start before turns")
    ap.add_argument("--greet", type=float, default=0, help="seconds to wait for a greeting/brief first")
    ap.add_argument("--brief", action="store_true", help="send brief.start first and wait for it")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    s = Session(args.server, json.loads(args.body), args.verbose)
    await s.connect()
    print("connected, bot ready")
    if args.brief:
        s.client_message("brief.start")
        await asyncio.sleep(2)
        await s.quiet(gap=2.0, timeout=40)
    if args.greet:
        await asyncio.sleep(args.greet)
        await s.quiet()
    if args.listen:
        s.client_message("listen.start")
        await asyncio.sleep(0.3)
    results = []
    for w in args.wav:
        r = await s.turn(Path(w))
        results.append(r)
        print(json.dumps(r, ensure_ascii=False))
    for t in args.text:
        r = await s.text_turn(t)
        results.append(r)
        print(json.dumps(r, ensure_ascii=False))
    await s.close()


if __name__ == "__main__":
    asyncio.run(main())
