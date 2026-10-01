"""Text mode: KB's prompt + tools loop without audio (tests, typed input debugging).

Uses the same prompts, tool schemas and handlers as the voice pipeline, talking
to the same LLM endpoint, so conversation logic can be tested without STT/TTS.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from kbos import db
from kbos.config import settings
from kbos.domain.brief import brief_data
from kbos.domain.people import get_person
from kbos.models import ShiftSession
from kbos.voice import prompts
from kbos.voice.language import detect
from kbos.voice.tools import TOOLS, KBState, handover_tickets, run_tool

SARVAM_URL = "https://api.sarvam.ai/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


@dataclass
class Turn:
    user: str
    said: list[str] = field(default_factory=list)
    tools: list[dict] = field(default_factory=list)
    ui: list[dict] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def text(self) -> str:
        return " ".join(self.said)

    def called(self, name: str) -> list[dict]:
        return [t for t in self.tools if t["name"] == name]


class TextSession:
    def __init__(self, person_id: int, shift_session_id: int | None = None, key_index: int = 0) -> None:
        self.ui: list[dict] = []

        async def push(msg: dict) -> None:
            self.ui.append(msg)

        self.state = KBState(person_id=person_id, shift_session_id=shift_session_id,
                             session_id=f"text-{time.time_ns()}", push=push)  # fmt: skip
        self.messages: list[dict[str, Any]] = []
        self.lang = "en"
        self.key_index = key_index

    # --- LLM plumbing ---
    async def _complete(self, client: httpx.AsyncClient, messages: list[dict]) -> dict:
        tools = [{"type": "function", "function": t} for t in TOOLS]
        if settings.llm_provider == "openrouter":
            body = {"model": "openai/gpt-oss-120b", "messages": messages, "tools": tools, "max_tokens": 600,
                    "provider": {"order": ["groq", "cerebras"]}, "reasoning": {"effort": "low"}}  # fmt: skip
            headers = {"Authorization": f"Bearer {settings.openrouter_key}"}
            url = OPENROUTER_URL
        else:
            body = {"model": "sarvam-105b-conversations", "messages": messages, "tools": tools, "max_tokens": 600}
            headers = {"api-subscription-key": settings.sarvam_keys[self.key_index % len(settings.sarvam_keys)]}
            url = SARVAM_URL
        for attempt in range(4):
            r = await client.post(url, json=body, headers=headers, timeout=60)
            if r.status_code in (404, 429, 500, 502, 503) and attempt < 3:
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
            if r.status_code in (401, 402, 403) and settings.llm_provider == "sarvam":
                self.key_index += 1
                headers = {"api-subscription-key": settings.sarvam_keys[self.key_index % len(settings.sarvam_keys)]}
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"LLM {r.status_code}: {r.text[:300]}")
            return r.json()["choices"][0]["message"]
        raise RuntimeError("LLM failed")

    async def _run(self, turn: Turn, max_steps: int = 5) -> Turn:
        t0 = time.monotonic()
        ui_before = len(self.ui)
        async with httpx.AsyncClient() as client:
            for _ in range(max_steps):
                system = {"role": "system", "content": prompts.system_prompt(self.state, self.lang)}
                msg = await self._complete(client, [system, *self.messages])
                content = (msg.get("content") or "").strip()
                calls = msg.get("tool_calls") or []
                entry: dict[str, Any] = {"role": "assistant", "content": content or None}
                if calls:
                    entry["tool_calls"] = calls
                self.messages.append(entry)
                if content:
                    turn.said.append(content)
                    self.state.transcript.append({"who": "kb", "text": content, "lang": detect(content)})
                if not calls:
                    break
                for c in calls:
                    name = c["function"]["name"]
                    try:
                        args = json.loads(c["function"].get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    result = await run_tool(self.state, name, args)
                    turn.tools.append({"name": name, "args": args, "result": result})
                    self.messages.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(result)})
                if self.state.shift_ended and content:
                    break
        turn.ui = self.ui[ui_before:]
        turn.seconds = time.monotonic() - t0
        return turn

    # --- public API ---
    async def say(self, text: str) -> Turn:
        self.lang = detect(text)
        self.messages.append({"role": "user", "content": text})
        self.state.transcript.append({"who": "user", "text": text, "lang": self.lang})
        return await self._run(Turn(user=text))

    async def client_message(self, type_: str, data: dict | None = None) -> Turn:
        """Mirror of the voice bot's client-message handling for photo/draft buttons."""
        data = data or {}
        if type_ == "photo.skipped":
            note = "[The user skipped the photo.] Continue: read back the summary and ask whether to file."
        elif type_ == "photo.attached":
            self.state.photos.extend({"id": i} for i in data.get("photo_ids", []))
            note = "[The user attached a photo.] Acknowledge briefly, then read back the summary and ask whether to file."
        else:
            raise ValueError(type_)
        self.messages.append({"role": "user", "content": note})
        return await self._run(Turn(user=type_))

    async def brief(self) -> Turn:
        with db.session() as s:
            p = get_person(s, self.state.person_id)
            ss = s.get(ShiftSession, self.state.shift_session_id) if self.state.shift_session_id else None
            data = brief_data(s, p.id, ss.started_at if ss else None)
        self.lang = p.preferred_language
        self.state.mode = "brief"
        await self.state.push({"type": "ui.tickets", "heading": "Shift Brief",
                               "tickets": data["tickets"], "brief": True})  # fmt: skip
        self.messages.append({"role": "user", "content": prompts.brief_instruction(data, self.lang)})
        turn = await self._run(Turn(user="[brief]"))
        self.state.mode = "chat"
        return turn

    async def handover(self) -> Turn:
        keys = handover_tickets(self.state)
        with db.session() as s:
            self.lang = get_person(s, self.state.person_id).preferred_language
        self.state.mode = "handover"
        self.state.handover_keys = keys
        self.messages.append({"role": "user", "content": prompts.handover_instruction(keys, self.lang)})
        return await self._run(Turn(user="[handover]"))
