"""LLM service wrappers: transient-error retry, key rotation, and 'did KB speak?' tracking."""

from __future__ import annotations

import asyncio

import openai
from loguru import logger
from pipecat.services.openrouter.llm import OpenRouterLLMService
from pipecat.services.sarvam._sdk import sdk_headers
from pipecat.services.sarvam.llm import SarvamLLMService
from pipecat.services.sarvam.tts import SarvamTTSService
from websockets.protocol import State

from kbos.config import settings
from kbos.voice.keypool import KeyPool

RETRYABLE = (openai.NotFoundError, openai.InternalServerError, openai.APIConnectionError, openai.APITimeoutError)
ROTATE = (openai.AuthenticationError, openai.PermissionDeniedError, openai.RateLimitError)


class _Tracking:
    """Mixin: remembers whether the current response contained spoken text.

    UI-only tools use this to skip the follow-up LLM call when KB already
    spoke in the same response (ADR 0004).
    """

    spoke = False

    async def _push_llm_text(self, text: str):
        if text and text.strip():
            self.spoke = True
        await super()._push_llm_text(text)  # type: ignore[misc]


class KBSarvamLLM(_Tracking, SarvamLLMService):
    def __init__(self, pool: KeyPool, key_index: int, **kwargs) -> None:
        self._pool = pool
        self._key_index = key_index
        super().__init__(api_key=pool.key(key_index), **kwargs)

    def _rotate(self, reason: str) -> None:
        self._key_index = self._pool.mark_bad(self._key_index, reason)
        self._client = self.create_client(api_key=self._pool.key(self._key_index), base_url=self._client.base_url)

    async def _process_context(self, context):
        for attempt in range(3):
            self.spoke = False
            try:
                return await super()._process_context(context)
            except openai.APIStatusError as e:
                if self.spoke or attempt == 2:
                    raise
                if isinstance(e, ROTATE) or e.status_code == 402:
                    self._rotate(str(e.status_code))
                elif not isinstance(e, RETRYABLE):
                    raise
                logger.warning(f"sarvam llm {e.status_code}, retrying ({attempt + 1})")
                await asyncio.sleep(0.25)
            except RETRYABLE as e:
                if self.spoke or attempt == 2:
                    raise
                logger.warning(f"sarvam llm {type(e).__name__}, retrying ({attempt + 1})")
                await asyncio.sleep(0.25)


class KBOpenRouterLLM(_Tracking, OpenRouterLLMService):
    pass


def make_llm(pool: KeyPool, key_index: int):
    if settings.llm_provider == "openrouter":
        return KBOpenRouterLLM(
            api_key=settings.openrouter_key,
            settings=OpenRouterLLMService.Settings(
                model="openai/gpt-oss-120b",
                max_tokens=400,
                extra={"provider": {"order": ["groq", "cerebras"]}, "reasoning": {"effort": "low"}},
            ),
        )
    return KBSarvamLLM(
        pool,
        key_index,
        settings=SarvamLLMService.Settings(model="sarvam-105b-conversations", max_tokens=400, temperature=0.3),
    )


class KBSarvamTTS(SarvamTTSService):
    """Sarvam TTS that retries the websocket connect: Sarvam's gateway sometimes answers 404 for a
    moment, and a single failed connect would otherwise mark TTS unusable for the whole session."""

    async def _connect_websocket(self):
        for attempt in range(5):
            if self._websocket and self._websocket.state is State.OPEN:
                return
            try:
                self._websocket = await self._websocket_connect(
                    self._websocket_url,
                    additional_headers={"api-subscription-key": self._api_key},
                    user_agent_header=sdk_headers()["User-Agent"],
                )
                await self._send_config()
                await self._call_event_handler("on_connected")
                return
            except Exception as e:
                self._websocket = None
                if attempt == 4:
                    break
                logger.warning(f"sarvam tts connect failed ({e}); retry {attempt + 1}")
                await asyncio.sleep(0.3 * (attempt + 1))
        await super()._connect_websocket()
