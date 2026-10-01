"""Sarvam key rotation. Logs only key indexes, never values."""

from __future__ import annotations

import asyncio
import itertools
from dataclasses import dataclass, field

import httpx
from loguru import logger


@dataclass
class KeyPool:
    keys: list[str]
    status: dict[int, str] = field(default_factory=dict)  # index -> ok | exhausted | untested
    _cursor: itertools.count = field(default_factory=itertools.count)

    def __post_init__(self) -> None:
        for i in range(len(self.keys)):
            self.status.setdefault(i, "untested")

    def _usable(self) -> list[int]:
        good = [i for i, s in self.status.items() if s != "exhausted"]
        return good or list(range(len(self.keys)))

    def next_index(self) -> int:
        if not self.keys:
            raise RuntimeError("no SARVAM_API_KEY_n configured in .env")
        usable = self._usable()
        return usable[next(self._cursor) % len(usable)]

    def key(self, index: int) -> str:
        return self.keys[index]

    def mark_bad(self, index: int, reason: str) -> int:
        """Mark a key exhausted (401/402/403/429) and return the next index to use."""
        self.status[index] = "exhausted"
        nxt = self.next_index()
        logger.warning(f"sarvam key #{index + 1} rotated out ({reason}); using key #{nxt + 1}")
        return nxt

    def public_status(self) -> list[dict[str, str | int]]:
        return [{"key": i + 1, "status": s} for i, s in sorted(self.status.items())]

    async def probe(self) -> None:
        """One tiny LLM call per key so /health can show which ones work."""

        async def one(client: httpx.AsyncClient, i: int) -> None:
            try:
                r = await client.post(
                    "https://api.sarvam.ai/v1/chat/completions",
                    headers={"api-subscription-key": self.keys[i]},
                    json={
                        "model": "sarvam-105b-conversations",
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "hi"}],
                    },
                )
                self.status[i] = "ok" if r.status_code == 200 else "exhausted" if r.status_code in (401, 402, 403) else "untested"
                if r.status_code != 200:
                    logger.warning(f"sarvam key #{i + 1} probe -> {r.status_code}")
            except Exception as e:  # network blips leave the key untested
                logger.warning(f"sarvam key #{i + 1} probe failed: {type(e).__name__}")

        async with httpx.AsyncClient(timeout=15) as client:
            await asyncio.gather(*(one(client, i) for i in range(len(self.keys))))
