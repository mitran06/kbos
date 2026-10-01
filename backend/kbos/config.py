"""Settings from the environment (.env at the repo root). Never log key values."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
load_dotenv(ROOT / ".env")


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    sarvam_keys: list[str] = field(default_factory=list)
    gnani_key: str = ""
    openrouter_key: str = ""
    llm_provider: str = "sarvam"
    tts_provider: str = "sarvam"
    tts_voice: str = "ritu"
    stt_model: str = "saaras:v4"
    stt_mode: str = "codemix"
    stt_language: str = "hi-IN"
    idle_timeout_s: float = 15.0
    public_host: str = ""
    db_path: Path = BACKEND / "data" / "kbos.db"
    uploads_dir: Path = BACKEND / "uploads"
    dashboard_dir: Path = ROOT / "dashboard" / "dist"


def load_settings() -> Settings:
    keys = [os.environ[k] for k in (f"SARVAM_API_KEY_{i}" for i in range(1, 9)) if os.environ.get(k)]
    return Settings(
        sarvam_keys=keys,
        gnani_key=_env("GNANI_API_KEY", ""),
        openrouter_key=_env("OPENROUTER_API_KEY", ""),
        llm_provider=_env("LLM_PROVIDER", "sarvam"),
        tts_provider=_env("TTS_PROVIDER", "sarvam"),
        tts_voice=_env("TTS_VOICE", "ritu"),
        stt_model=_env("STT_MODEL", "saaras:v4"),
        stt_mode=_env("STT_MODE", "codemix"),
        stt_language=_env("STT_LANGUAGE", "hi-IN"),
        idle_timeout_s=float(_env("IDLE_TIMEOUT_S", "15")),
        public_host=_env("PUBLIC_HOST", ""),
        db_path=Path(_env("KBOS_DB", str(BACKEND / "data" / "kbos.db"))),
    )


settings = load_settings()
