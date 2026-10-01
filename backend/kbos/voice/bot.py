"""Per-session voice pipeline for one phone.

transport.input -> STT gate -> user aggregator (Silero VAD + Smart Turn)
-> context refresher (live system prompt) -> LLM + tools -> ReplyLanguage
-> TTS -> transport.output -> assistant aggregator
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    Frame,
    FunctionCallResultProperties,
    InterruptionWorkerFrame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMMessagesAppendFrame,
    LLMTextFrame,
    TranscriptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.observers.user_bot_latency_observer import UserBotLatencyObserver
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.frameworks.rtvi import RTVIFunctionCallReportLevel, RTVIObserverParams
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.sarvam.tts import SarvamTTSService
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.turns.user_mute.base_user_mute_strategy import BaseUserMuteStrategy
from pipecat.turns.user_start.vad_user_turn_start_strategy import VADUserTurnStartStrategy
from pipecat.turns.user_stop.turn_analyzer_user_turn_stop_strategy import TurnAnalyzerUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.workers.runner import WorkerRunner
from sqlmodel import select

from kbos import db
from kbos.config import settings
from kbos.domain.brief import brief_data
from kbos.domain.people import get_person
from kbos.models import GlossaryTerm, Photo, ShiftSession
from kbos.voice import prompts
from kbos.voice.gate import GatedSarvamSTT
from kbos.voice.language import ReplyLanguage, detect
from kbos.voice.services import GnaniTTS, KBSarvamTTS, make_llm
from kbos.voice.tools import TOOLS, KBState, closed_this_shift, discard_draft, draft_view, handover_tickets, run_tool

LANG_TAG = {"hi": " [reply in Hindi, Devanagari]", "en": " [reply in English]"}
UI_ONLY = {"show_tickets"}  # results don't change what KB says: skip the 2nd LLM call if KB already spoke
MACHINE_TERMS = ["4B", "2A", "3C", "1D", "5A", "6B"]


class EchoTailUserMuteStrategy(BaseUserMuteStrategy):
    """Half-duplex: ignore the mic while KB speaks and for a short tail after (speaker echo).

    Muted frames are dropped before the VAD (Pipecat's user-mute hook), so the VAD's volume
    window isn't drained by silence and reacts at once when the user speaks.
    """

    def __init__(self, tail_s: float = 0.9) -> None:
        super().__init__()
        self._tail_s = tail_s
        self._speaking = False
        self._until = 0.0

    async def process_frame(self, frame: Frame) -> bool:
        if isinstance(frame, BotStartedSpeakingFrame):
            self._speaking = True
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._speaking = False
            self._until = time.monotonic() + self._tail_s
        return self._speaking or time.monotonic() < self._until


class ContextRefresher(FrameProcessor):
    """Rewrites the system message (live context) right before every LLM run."""

    def __init__(self, refresh) -> None:
        super().__init__()
        self._refresh = refresh

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMContextFrame) and direction == FrameDirection.DOWNSTREAM:
            self._refresh()
        await self.push_frame(frame, direction)


class Activity(BaseObserver):
    """Watches the pipeline for speech activity (idle timeout) and transcript lines."""

    def __init__(self, state: KBState, llm) -> None:
        super().__init__()
        self.state = state
        self.llm = llm
        self.last = time.monotonic()
        self.bot_speaking = False
        self.user_speaking = False
        self.latest_user_lang = "en"
        self._reply: list[str] = []
        self._seen: set[int] = set()

    async def on_push_frame(self, data: FramePushed):
        f = data.frame
        if f.id in self._seen:
            return
        if isinstance(f, (BotStartedSpeakingFrame, BotStoppedSpeakingFrame, UserStartedSpeakingFrame,
                          UserStoppedSpeakingFrame, TranscriptionFrame)):  # fmt: skip
            self._seen.add(f.id)
            self.last = time.monotonic()
            if isinstance(f, BotStartedSpeakingFrame):
                self.bot_speaking = True
            elif isinstance(f, BotStoppedSpeakingFrame):
                self.bot_speaking = False
            elif isinstance(f, UserStartedSpeakingFrame):
                self.user_speaking = True
            elif isinstance(f, UserStoppedSpeakingFrame):
                self.user_speaking = False
            elif isinstance(f, TranscriptionFrame) and f.text.strip():
                self.latest_user_lang = detect(f.text)
                self.state.transcript.append({"who": "user", "text": f.text, "lang": self.latest_user_lang})
                logger.info(f"heard: {f.text}")
        elif data.source is self.llm and isinstance(f, (LLMFullResponseStartFrame, LLMTextFrame, LLMFullResponseEndFrame)):
            self._seen.add(f.id)
            if isinstance(f, LLMFullResponseStartFrame):
                self._reply = []
            elif isinstance(f, LLMTextFrame):
                self._reply.append(f.text)
            elif self._reply:
                text = "".join(self._reply).strip()
                if text:
                    self.state.transcript.append({"who": "kb", "text": text, "lang": detect(text)})
                self._reply = []
        if len(self._seen) > 5000:
            self._seen.clear()


async def run_bot(webrtc_connection: Any, live, manager) -> None:
    pool = manager.pool
    body = live.body
    key_index = pool.next_index()
    key = pool.key(key_index)
    person_id = int(body.get("person_id") or 1)
    with db.session() as s:
        person = get_person(s, person_id)
        glossary = [g.term for g in s.exec(select(GlossaryTerm)).all()]
    live.person_name = person.name
    tag = f"{person.name.split()[0]}#{live.id[:4]}"
    logger.info(f"[{tag}] voice session start key=#{key_index + 1}")

    worker_ref: dict[str, PipelineWorker] = {}

    async def push(msg: dict) -> None:
        w = worker_ref.get("w")
        if w is not None:
            await w.rtvi.send_server_message(msg)

    state = KBState(
        person_id=person_id,
        shift_session_id=body.get("shift_session_id"),
        session_id=live.id,
        push=push,
    )
    live.state = {"listening": False}

    transport = SmallWebRTCTransport(
        webrtc_connection=webrtc_connection,
        params=TransportParams(audio_in_enabled=True, audio_out_enabled=True, audio_out_10ms_chunks=2),
    )
    stt = GatedSarvamSTT(
        api_key=key,
        sample_rate=16000,
        keyterms=["KB", *MACHINE_TERMS, "vibration", "critical", "severity", "production", "assigned", "spindle bearing", *glossary],
        ttfs_p99_latency=1.6,
        settings=GatedSarvamSTT.Settings(
            model=settings.stt_model, language_code=settings.stt_language, mode=settings.stt_mode, stream_type="fast"
        ),
    )
    llm = make_llm(pool, key_index)
    start_lang = "hi-IN" if person.preferred_language == "hi" else "en-IN"
    if settings.tts_provider == "gnani":
        tts = GnaniTTS(api_key=settings.gnani_key, sample_rate=24000)
    else:
        tts = KBSarvamTTS(
            api_key=key,
            sample_rate=24000,
            settings=SarvamTTSService.Settings(
                model="bulbul:v3", voice=settings.tts_voice, language=start_lang, min_buffer_size=30, pace=1.05
            ),
        )
    reply_lang = ReplyLanguage(initial=start_lang)

    tools = ToolsSchema(
        standard_tools=[
            FunctionSchema(
                name=t["name"], description=t["description"],
                properties=t["parameters"]["properties"], required=t["parameters"]["required"],
            )
            for t in TOOLS
        ]
    )  # fmt: skip
    context = LLMContext(messages=[{"role": "system", "content": ""}], tools=tools)
    activity = Activity(state, llm)

    def refresh() -> None:
        # Language of the latest real user message in the context (not bracketed app notes).
        # A bracketed app note (brief/handover/photo) keeps whatever language was set with it.
        for m in reversed(context.messages):
            text = m.get("content") if m.get("role") == "user" else None
            if isinstance(text, str) and text.strip():
                if not text.startswith("["):
                    activity.latest_user_lang = detect(text.split(" [reply in")[0])
                    # Recency beats the system prompt: tag the turn itself with its reply language.
                    tag = LANG_TAG[activity.latest_user_lang]
                    if not text.endswith(tag):
                        m["content"] = text.split(" [reply in")[0] + tag
                break
        context.messages[0]["content"] = prompts.system_prompt(state, activity.latest_user_lang)

    refresh()

    async def tool_handler(params: FunctionCallParams) -> None:
        name = params.function_name
        result = await run_tool(state, name, dict(params.arguments or {}))
        refresh()
        # The follow-up LLM call reads this result last, so restate the reply language here too.
        result = {**result, "reply_in": "Hindi (Devanagari)" if activity.latest_user_lang == "hi" else "English"}
        run_llm = not (name in UI_ONLY and getattr(llm, "spoke", False) and "error" not in result)
        await params.result_callback(result, properties=FunctionCallResultProperties(run_llm=run_llm))

    for t in TOOLS:
        llm.register_function(t["name"], tool_handler, cancel_on_interruption=t["name"] in UI_ONLY)

    user_agg, assistant_agg = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            # Stricter than default so fans and distant chatter don't open turns (Sarvam hallucinates on noise).
            vad_analyzer=SileroVADAnalyzer(params=VADParams(confidence=0.7, start_secs=0.2, stop_secs=0.35, min_volume=0.6)),
            # A late final transcript must not open a phantom turn and interrupt KB.
            user_mute_strategies=[EchoTailUserMuteStrategy(0.9)],
            user_turn_strategies=UserTurnStrategies(
                start=[VADUserTurnStartStrategy()],
                # Smart Turn often calls short Hindi fragments "incomplete"; cap its silence fallback.
                stop=[TurnAnalyzerUserTurnStopStrategy(turn_analyzer=LocalSmartTurnAnalyzerV3(params=SmartTurnParams(stop_secs=1.4)))],
            ),
        ),
    )
    pipeline = Pipeline([
        transport.input(), stt, user_agg, ContextRefresher(refresh), llm,
        *([reply_lang] if settings.tts_provider != "gnani" else []), tts,
        transport.output(), assistant_agg,
    ])  # fmt: skip

    latency = UserBotLatencyObserver()

    @latency.event_handler("on_latency_breakdown")
    async def on_breakdown(observer, breakdown):
        lines = breakdown.turn_contribution_lines()
        for line in lines:
            logger.info(f"[latency {tag}] {line}")
        entry = {"at": time.strftime("%H:%M:%S"), "person": person.name, "lines": [ln.strip() for ln in lines]}
        manager.record_latency(entry)
        await push({"type": "ui.latency", **entry})

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(audio_in_sample_rate=16000, audio_out_sample_rate=24000, enable_metrics=True),
        observers=[latency, activity],
        idle_timeout_secs=None,
        rtvi_observer_params=RTVIObserverParams(function_call_report_level={"*": RTVIFunctionCallReportLevel.NAME}),
    )
    worker_ref["w"] = worker
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)

    async def say_after(note: str) -> None:
        refresh()
        await worker.queue_frames([LLMMessagesAppendFrame([{"role": "user", "content": note}], run_llm=True)])

    async def set_listening(on: bool, reason: str = "stop") -> None:
        live.state["listening"] = on
        if on:
            activity.last = time.monotonic()
            await stt.open_gate()
        else:
            await stt.close_gate()

    async def idle_watch() -> None:
        while True:
            await asyncio.sleep(0.5)
            if (
                stt.gate_open
                and not activity.bot_speaking
                and not activity.user_speaking
                and time.monotonic() - activity.last > settings.idle_timeout_s
            ):
                logger.info(f"[{tag}] idle {settings.idle_timeout_s:.0f}s: closing the gate")
                await set_listening(False)
                await push({"type": "ui.session_end", "reason": "idle"})
            if state.shift_ended and not activity.bot_speaking and time.monotonic() - activity.last > 1.5:
                state.shift_ended = False
                await set_listening(False)

    watcher = asyncio.create_task(idle_watch())

    @worker.rtvi.event_handler("on_client_message")
    async def on_client_message(rtvi, msg):
        t, data = msg.type, (msg.data or {})
        logger.info(f"[{tag}] client {t}")
        if t == "listen.start":
            await set_listening(True)
        elif t == "listen.stop":
            if activity.bot_speaking:  # cut KB off first, then tidy the gate
                await worker.queue_frames([InterruptionWorkerFrame()])
            await set_listening(False)
        elif t == "text.input":
            text = str(data.get("text", "")).strip()
            if text:
                activity.latest_user_lang = detect(text)
                state.transcript.append({"who": "user", "text": text, "lang": activity.latest_user_lang})
                activity.last = time.monotonic()
                await say_after(text)
        elif t == "brief.start":
            with db.session() as s:
                ss = s.get(ShiftSession, state.shift_session_id) if state.shift_session_id else None
                data_b = brief_data(s, person_id, ss.started_at if ss else None)
            await push({"type": "ui.tickets", "heading": "Shift Brief", "tickets": data_b["tickets"], "brief": True})
            activity.latest_user_lang = person.preferred_language
            await say_after(prompts.brief_instruction(data_b, person.preferred_language))
        elif t == "handover.start":
            keys = handover_tickets(state)
            state.mode = "handover"
            state.handover_keys = keys
            activity.latest_user_lang = person.preferred_language
            await say_after(prompts.handover_instruction(keys, person.preferred_language, closed_this_shift(state)))
        elif t == "photo.attached":
            ids = [int(i) for i in data.get("photo_ids", [])]
            with db.session() as s:
                for pid in ids:
                    p = s.get(Photo, pid)
                    if p:
                        p.session_id = state.session_id
                        s.add(p)
                        state.photos.append({"id": p.id, "url": f"/uploads/{p.path}"})
                s.commit()
            await push({"type": "ui.draft", "draft": draft_view(state)})
            await say_after("[The user attached a photo to the Draft.] Acknowledge in a few words, then read back a one-sentence summary and ask whether to file.")
        elif t == "photo.skipped":
            await say_after("[The user skipped the photo.] Read back a one-sentence summary and ask whether to file.")
        elif t == "draft.file":
            result = await run_tool(state, "file_ticket", {})
            if "error" in result:
                await say_after(f"[The user tapped File, but filing failed: {result['error']}] Ask for what's missing in one short question.")
            else:
                await say_after(
                    f"[The user tapped File. It is already filed as {result['ticket_key']}, assigned to "
                    f"{', '.join(result['assignees'])}; the card is on screen.] Confirm in one short line. Don't call any tool."
                )
        elif t == "draft.discard":
            await discard_draft(state)
            await say_after("[The user tapped Discard; the Draft is already gone.] Acknowledge in a few words. Don't call any tool.")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"[{tag}] client disconnected")
        await runner.cancel()

    try:
        await runner.run()
    finally:
        watcher.cancel()
        await stt.close_gate()
        logger.info(f"[{tag}] voice session end; STT audio sent {stt.sent_bytes / 32000:.1f}s")



