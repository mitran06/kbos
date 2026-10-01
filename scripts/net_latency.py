"""Quick Sarvam latency probe (LLM TTFT, TTS first audio, STT final) for comparing networks (e.g. WARP on/off).
Usage (from backend/): uv run python ../scripts/net_latency.py [label]"""

from __future__ import annotations

import asyncio
import base64
import json
import statistics
import sys
import time
import wave
from pathlib import Path

import httpx
import websockets

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from kbos.config import settings  # noqa: E402

KEY = settings.sarvam_keys[4]
AUDIO = Path(__file__).resolve().parents[1] / "backend" / "tests" / "audio" / "en_open.wav"


async def llm_ttft(client: httpx.AsyncClient) -> float:
    t = time.monotonic()
    async with client.stream("POST", "https://api.sarvam.ai/v1/chat/completions", headers={"api-subscription-key": KEY},
                             json={"model": "sarvam-105b-conversations", "stream": True, "max_tokens": 30,
                                   "messages": [{"role": "user", "content": "Say hello in five words."}]}) as r:  # fmt: skip
        async for line in r.aiter_lines():
            if '"content"' in line:
                return time.monotonic() - t
    return -1


async def tts_first_audio() -> float:
    t = time.monotonic()
    async with websockets.connect("wss://api.sarvam.ai/text-to-speech/ws?model=bulbul:v3",
                                  additional_headers={"api-subscription-key": KEY}) as ws:  # fmt: skip
        await ws.send(json.dumps({"type": "config", "data": {"target_language_code": "en-IN", "speaker": "ritu", "min_buffer_size": 30}}))
        t = time.monotonic()
        await ws.send(json.dumps({"type": "text", "data": {"text": "The 2A hydraulic leak is critical."}}))
        await ws.send(json.dumps({"type": "flush"}))
        while True:
            m = json.loads(await ws.recv())
            if m.get("type") == "audio":
                return time.monotonic() - t


async def stt_final() -> float:
    with wave.open(str(AUDIO)) as w:
        pcm = w.readframes(w.getnframes())
    url = ("wss://api.sarvam.ai/speech-to-text-realtime/ws?language_code=hi-IN&mode=codemix&model=saaras:v4"
           "&stream_type=fast&endpointing=manual&encoding=linear16&sample_rate=16000")  # fmt: skip
    async with websockets.connect(url, additional_headers={"API-SUBSCRIPTION-KEY": KEY}) as ws:
        await ws.send(json.dumps({"event": "speech_start"}))
        for i in range(0, len(pcm), 3200):
            await ws.send(json.dumps({"event": "audio_input", "audio": base64.b64encode(pcm[i:i + 3200]).decode()}))
            await asyncio.sleep(0.1)
        t = time.monotonic()
        await ws.send(json.dumps({"event": "speech_end"}))
        while True:
            m = json.loads(await asyncio.wait_for(ws.recv(), 5))
            if m.get("event") == "transcript.final":
                return time.monotonic() - t


async def main() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else "run"
    res: dict[str, list[float]] = {"llm_ttft": [], "tts_first_audio": [], "stt_final": []}
    async with httpx.AsyncClient(timeout=30) as c:
        for _ in range(4):
            for name, fn in (("llm_ttft", lambda: llm_ttft(c)), ("tts_first_audio", tts_first_audio), ("stt_final", stt_final)):
                try:
                    res[name].append(await fn())
                except Exception as e:
                    print(f"{name} failed: {e}")
    print(label, {k: round(statistics.median(v), 3) if v else None for k, v in res.items()})


asyncio.run(main())
