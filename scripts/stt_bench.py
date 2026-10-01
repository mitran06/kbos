"""Compare Sarvam realtime STT configs on the generated test audio (PLAN §6.3).

Streams each WAV in manual-endpointing mode (speech_start ... speech_end), the
way the STT gate does, and records the final transcript and the time from
speech_end to the final transcript.
Usage (from backend/): uv run python ../scripts/stt_bench.py
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
import time
import wave
from pathlib import Path
from urllib.parse import urlencode

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from kbos.config import settings  # noqa: E402

AUDIO = Path(__file__).resolve().parents[1] / "backend" / "tests" / "audio"
FILES = ["en_hello", "en_open", "en_vib", "hi_hello", "hi_vib", "hi_leak", "hing_vib", "hing_yes", "hing_check"]
KEYTERMS = ["KB", "4B", "2A", "3C", "1D", "5A", "6B", "Monitoring", "vibration", "TC", "SB", "LC", "hyd", "jhatka", "awaaz"]
CONFIGS = {
    "hi-IN codemix v4": {"language_code": "hi-IN", "mode": "codemix", "model": "saaras:v4"},
    "auto codemix v4": {"language_code": "auto", "mode": "codemix", "model": "saaras:v4"},
    "auto transcribe v4": {"language_code": "auto", "mode": "transcribe", "model": "saaras:v4"},
}


async def run(cfg: dict, name: str, key: str) -> tuple[str, float]:
    params = {**cfg, "stream_type": "fast", "endpointing": "manual", "encoding": "linear16", "sample_rate": 16000,
              "keyterms": json.dumps(KEYTERMS)}  # fmt: skip
    url = "wss://api.sarvam.ai/speech-to-text-realtime/ws?" + urlencode(params)
    with wave.open(str(AUDIO / f"{name}.wav")) as w:
        pcm = w.readframes(w.getnframes())
    async with websockets.connect(url, additional_headers={"API-SUBSCRIPTION-KEY": key}) as ws:
        await ws.send(json.dumps({"event": "speech_start"}))
        step = 1600 * 2  # 100 ms
        for i in range(0, len(pcm), step):
            await ws.send(json.dumps({"event": "audio_input", "audio": base64.b64encode(pcm[i : i + step]).decode()}))
            await asyncio.sleep(0.1)
        t_end = time.monotonic()
        await ws.send(json.dumps({"event": "speech_end"}))
        finals = []
        try:
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 4))
                if msg.get("event") == "transcript.final":
                    finals.append((msg.get("text") or msg.get("data", {}).get("text", ""), time.monotonic() - t_end))
                    break
        except TimeoutError:
            pass
    if not finals:
        return "(none)", -1
    return finals[-1]


async def main() -> None:
    key = settings.sarvam_keys[2]
    out = {}
    for cname, cfg in CONFIGS.items():
        print(f"\n## {cname}")
        out[cname] = {}
        for f in FILES:
            text, lat = await run(cfg, f, key)
            out[cname][f] = (text, lat)
            print(f"{f:11s} {lat:5.2f}s  {text}")
    lats = {c: sorted(v[1] for v in r.values() if v[1] >= 0) for c, r in out.items()}
    print()
    for c, ls in lats.items():
        print(f"{c}: median speech_end->final {ls[len(ls) // 2]:.2f}s")


asyncio.run(main())
