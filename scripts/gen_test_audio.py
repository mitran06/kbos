"""Render test user utterances with Bulbul v3 into backend/tests/audio/*.wav (16 kHz mono).

Usage: cd backend && uv run python ../scripts/gen_test_audio.py [--only name1,name2]
Skips files that already exist, so re-running costs nothing.
"""

from __future__ import annotations

import argparse
import base64
import io
import sys
import wave
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from kbos.config import settings  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "backend" / "tests" / "audio"

# name -> (language_code, speaker, text)
UTTERANCES: dict[str, tuple[str, str, str]] = {
    "en_hello": ("en-IN", "aditya", "Hi KB, what can you do for me?"),
    "hi_hello": ("hi-IN", "aditya", "नमस्ते KB, आज कौन से tickets खुले हैं?"),
    "en_open": ("en-IN", "aditya", "What's open today?"),
    "en_vib": ("en-IN", "aditya", "Machine 4B is vibrating badly again since the tool change, ticket KB-0141 is still in monitoring."),
    "en_close": ("en-IN", "rahul", "Close one four two. I replaced the spindle bearing, vibration is back to two millimetres per second."),
    "hi_vib": ("hi-IN", "aditya", "4B मशीन में फिर से बहुत vibration आ रहा है, आवाज़ भी आ रही है।"),
    "hi_since": ("hi-IN", "rahul", "दस मिनट से हो रहा है, मशीन अभी चल रही है।"),
    "hi_leak": ("hi-IN", "aditya", "2A press के cylinder से hydraulic oil leak हो रहा है।"),
    "hing_vib": ("hi-IN", "aditya", "KB, 4B pe phir se bahut vibration aa raha hai, awaaz bhi aa rahi hai, machine abhi chal rahi hai."),
    "hing_yes": ("hi-IN", "rahul", "Haan, same issue hai. Das minute se ho raha hai."),
    "hing_check": ("hi-IN", "aditya", "3C checked. Bas check kar liya, sab theek hai."),
    "hing_same": ("hi-IN", "aditya", "हाँ, same problem है।"),
    "hing_since": ("hi-IN", "aditya", "दस minute से।"),
    "hing_critical": ("hi-IN", "aditya", "Critical, production रुक जाएगा।"),
    "hing_file": ("hi-IN", "aditya", "हाँ, file कर दो।"),
    "en_assigned": ("en-IN", "rahul", "What's assigned to me?"),
    "en_close141": ("en-IN", "rahul", "Close one four one too, same root cause."),
    "en_3c": ("en-IN", "rahul", "3C checked."),
    "hing_bas": ("hi-IN", "rahul", "बस check कर लिया।"),
    "en_handover": ("en-IN", "aditya", "Still vibrating a little, Imran is on it."),
}


def render(lang: str, speaker: str, text: str, key: str) -> bytes:
    r = httpx.post(
        "https://api.sarvam.ai/text-to-speech",
        headers={"api-subscription-key": key},
        json={
            "text": text,
            "target_language_code": lang,
            "speaker": speaker,
            "model": "bulbul:v3",
            "speech_sample_rate": 16000,
        },
        timeout=60,
    )
    r.raise_for_status()
    return base64.b64decode(r.json()["audios"][0])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    only = {s for s in args.only.split(",") if s}
    OUT.mkdir(parents=True, exist_ok=True)
    key = settings.sarvam_keys[-1]
    for name, (lang, speaker, text) in UTTERANCES.items():
        if only and name not in only:
            continue
        path = OUT / f"{name}.wav"
        if path.exists():
            continue
        data = render(lang, speaker, text, key)
        with wave.open(io.BytesIO(data)) as w:
            secs = w.getnframes() / w.getframerate()
            rate = w.getframerate()
        path.write_bytes(data)
        print(f"{name}: {secs:.1f}s @ {rate} Hz")


if __name__ == "__main__":
    main()
