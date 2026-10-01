"""Per-session Pipecat pipeline (M1 spike: STT -> LLM -> TTS, no tools)."""

from __future__ import annotations

import os
from typing import Any

from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.observers.user_bot_latency_observer import UserBotLatencyObserver
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.sarvam.llm import SarvamLLMService
from pipecat.services.sarvam.tts import SarvamTTSService
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.workers.runner import WorkerRunner

from kbos.config import settings
from kbos.voice.gate import GatedSarvamSTT
from kbos.voice.keypool import KeyPool

SYSTEM = (
    "You are KB, the voice assistant inside KBOS, a factory ticketing app. "
    "Reply in one or two short spoken sentences, no lists, no markdown, no emojis. "
    "Mirror the language of the user's latest message: English gets English; Hindi or Hinglish gets Hindi "
    "written in Devanagari, keeping technical English words in Latin script."
)


async def run_bot(webrtc_connection: Any, live, manager) -> None:
    pool: KeyPool = manager.pool
    body = live.body
    key_index = pool.next_index()
    key = pool.key(key_index)
    device_id = body.get("device_id", "?")
    logger.info(f"bot session start device={device_id} key=#{key_index + 1}")

    transport = SmallWebRTCTransport(
        webrtc_connection=webrtc_connection,
        params=TransportParams(audio_in_enabled=True, audio_out_enabled=True, audio_out_10ms_chunks=2),
    )
    stt = GatedSarvamSTT(
        api_key=key,
        sample_rate=16000,
        keyterms=["KB", "KBOS", "4B", "2A", "3C", "1D", "5A", "6B", "vibration", "Monitoring", "ticket"],
        settings=GatedSarvamSTT.Settings(
            model=settings.stt_model,
            language_code=settings.stt_language,
            mode=settings.stt_mode,
            stream_type="fast",
        ),
    )
    llm = SarvamLLMService(
        api_key=key,
        settings=SarvamLLMService.Settings(
            model="sarvam-105b-conversations", system_instruction=SYSTEM, max_tokens=300
        ),
    )
    tts = SarvamTTSService(
        api_key=key,
        sample_rate=24000,
        settings=SarvamTTSService.Settings(
            model="bulbul:v3", voice=settings.tts_voice, language="en-IN", min_buffer_size=30
        ),
    )
    context = LLMContext()
    user_agg, assistant_agg = LLMContextAggregatorPair(
        context, user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer())
    )
    pipeline = Pipeline([transport.input(), stt, user_agg, llm, tts, transport.output(), assistant_agg])

    latency = UserBotLatencyObserver()

    @latency.event_handler("on_latency_breakdown")
    async def on_breakdown(observer, breakdown):
        for line in breakdown.turn_contribution_lines():
            logger.info(f"[latency {device_id}] {line}")

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=16000, audio_out_sample_rate=24000, enable_metrics=True
        ),
        observers=[latency],
        idle_timeout_secs=None,
    )
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)

    @worker.rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        context.add_message({"role": "user", "content": "Say a one-line hello as KB."})
        await worker.queue_frames([LLMRunFrame()])
        if body.get("auto_listen", True):
            await stt.open_gate()

    @worker.rtvi.event_handler("on_client_message")
    async def on_client_message(rtvi, msg):
        logger.info(f"client message {msg.type}")
        if msg.type == "listen.start":
            await stt.open_gate()
        elif msg.type == "listen.stop":
            await stt.close_gate()

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        await runner.cancel()

    await runner.run()
    logger.info(f"bot session end device={device_id}")
