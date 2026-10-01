# Sarvam AI developer APIs for a real-time Indic voice agent: research notes for KBOS

Researched 2026-10-01. Primary sources: docs.sarvam.ai (fetched as `.md`), the API reference, sarvam.ai pricing and blog pages, the `sarvamai/skills` repo, PyPI, and Pipecat source and docs at the **v1.12.0** tag (released 2026-09-26). Claims marked **[inference]** are mine and are not stated by a source. Nothing in this document was run against a live key.

## TL;DR

- **Models today.** STT: `saaras:v4` (default for REST and legacy WS), plus `saaras:v3-realtime` (default on the new Realtime WS). TTS: `bulbul:v3`. Bulbul V4 is a research preview and is not in the API. LLM: `sarvam-105b` (128K context, reasoning on by default) and **`sarvam-105b-conversations`** (32K context, tuned for voice agents). `sarvam-m` and `sarvam-30b` are deprecated and rejected by the API.
- **Hinglish is first-class.** STT has a `codemix` mode that returns English words in Latin script and Hindi words in Devanagari. The 105B models are trained on native-script, romanized and code-mixed input. Bulbul v3 speaks mixed-script text, but romanized Hindi input "significantly reduces output quality".
- **Everything streams.** STT over WebSocket (`/speech-to-text-realtime/ws`) gives partial transcripts and server VAD events (`vad.speech_start` / `vad.speech_end`). TTS streams over WebSocket (`/text-to-speech/ws`) or chunked HTTP (`/text-to-speech/stream`). The LLM streams over SSE on an OpenAI-compatible `/v1/chat/completions` with tool calling.
- **Credits.** 1 credit = ₹1 (verified on the pricing FAQ). The 100 trial credits are the standard ₹100 signup grant, and they never expire. ₹100 buys about **200 min of STT**, **about 33K TTS characters (roughly 35 min of speech)**, or **about 3.4M input / 1.4M output LLM tokens**. A cascaded Pipecat demo costs roughly **₹2 per conversation-minute, about 50 minutes in total**, and TTS is the biggest line item **[inference]**. Sarvam's hosted Voice Agents platform costs ₹3.50/min, which is about 28 minutes.
- **Pipecat support is real and current.** `pipecat-ai[sarvam]` 1.12.0 ships `SarvamRealtimeSTTService` (added 1.8.0), `SarvamSTTService` (legacy WS), `SarvamTTSService` (WS), `SarvamHttpTTSService`, and `SarvamLLMService` (OpenAI-compatible, with function calling). Watch three traps: (1) since 1.8.0, `SarvamLLMService` sends every model **except `sarvam-105b-conversations` to `/v2`**, and `/v2` is a beta that needs per-key whitelisting; (2) Sarvam's own Pipecat guides are already out of date against 1.12 (constructor kwargs, chunking, VAD advice); (3) Pipecat requires Python ≥ 3.11.
- **Latency.** Vendor claims: Saaras V3 realtime "Fast" mode < 150 ms time-to-first-token, Bulbul TTS < 250 ms first byte, Voice Agents "< 500 ms" / "sub-second". Sarvam's own SLO for a cascaded pipeline counts e2e p50 < 900 ms as "good" and < 1.4 s as "acceptable". There is no published TTFT for 105B. For a tuned Pipecat demo, expect **about 1.0–1.5 s from end of speech to first audio [inference]**.
- **No speech-to-speech model.** The lower-latency option is Sarvam **Voice Agents** (formerly "Samvaad", at `indus.sarvam.ai/samvaad`). It is a hosted cascade (Saaras v4 → Sarvam LLMs → Bulbul v3) on co-located self-hosted models, with Python and Web SDKs (`sarvam-conv-ai-sdk`). You can't bring your own LLM, and it costs ₹3.50/min.

---

## 1. Speech-to-text (Saaras)

### Models

| Model ID | Status | Where | Notes | Source |
|---|---|---|---|---|
| `saaras:v4` | Default and recommended (since 2026-08-18) | REST `/speech-to-text`, Batch, legacy WS `/speech-to-text/ws`, Realtime WS (since 2026-09-03) | Adds Global English to the 22 Indic languages and Indian English. Only model that supports `keyterms` (up to 50 terms of 64 chars; on streaming WS since 2026-09-22). | [Saaras](https://docs.sarvam.ai/api/getting-started/models/saaras), [changelog 2026-08-18](https://docs.sarvam.ai/changelog/2026/8/18), [2026-09-03](https://docs.sarvam.ai/changelog/2026/9/3), [2026-09-22](https://docs.sarvam.ai/changelog/2026/9/22) |
| `saaras:v3-realtime` | **Default on the Realtime WS** | `/speech-to-text-realtime/ws` only | Causal streaming encoder with true partials | [Realtime guide](https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/realtime-streaming), [Saaras V3 blog](https://www.sarvam.ai/blogs/asr) |
| `saaras:v3` | Still available | REST, Batch, legacy WS | Same five modes as v4 | [Saaras](https://docs.sarvam.ai/api/getting-started/models/saaras) |
| `saaras:v2.5`, `saarika:v2.5` | Legacy / being sunset | `/speech-to-text-translate` | Pipecat removed both in 1.8.0 | [Saaras](https://docs.sarvam.ai/api/getting-started/models/saaras), [Pipecat CHANGELOG](https://github.com/pipecat-ai/pipecat/blob/v1.12.0/CHANGELOG.md) |

**Languages:** 23, meaning 22 scheduled Indian languages plus English. Codes: `hi-IN bn-IN kn-IN ml-IN mr-IN od-IN pa-IN ta-IN te-IN en-IN gu-IN as-IN ur-IN ne-IN kok-IN ks-IN sd-IN sa-IN sat-IN mni-IN brx-IN mai-IN doi-IN`. On REST, language detection is automatic when you omit the code or pass `unknown`. On Realtime, `language_code` is **required**, and `auto` turns on detection. **Gotcha:** Realtime uses `or-IN` for Odia, while REST and legacy WS use `od-IN`. ([Models](https://docs.sarvam.ai/api/getting-started/models), [Realtime guide](https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/realtime-streaming))

### Output modes (all on v3/v4, REST and WS)

| `mode` | Output for "मेरा फोन नंबर है 9840950950" |
|---|---|
| `transcribe` (default) | `मेरा फोन नंबर है 9840950950` |
| `translate` | `My phone number is 9840950950` (always English) |
| `verbatim` | `मेरा फोन नंबर है नौ आठ चार zero ...` |
| `translit` | `mera phone number hai 9840950950` |
| **`codemix`** | **`मेरा phone number है 9840950950`**. The docs name this mode "Hinglish conversations, mixed-language customer support". |

On Realtime, `mode` applies to the **final** transcript only. Partials are always plain transcription. Source: [Saaras](https://docs.sarvam.ai/api/getting-started/models/saaras), [select output mode](https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/how-to/select-output-mode).

### Transports

| | REST | **Realtime WS (use this)** | Legacy WS | Batch |
|---|---|---|---|---|
| Endpoint | `POST https://api.sarvam.ai/speech-to-text` | `wss://api.sarvam.ai/speech-to-text-realtime/ws` | `wss://api.sarvam.ai/speech-to-text/ws` | `POST /speech-to-text/job/v1` |
| Default model | `saaras:v4` | `saaras:v3-realtime` (`saaras:v4` also accepted) | `saaras:v4` | `saaras:v4` |
| Partials | n/a | **yes** (`transcript.partial`) | no, final per utterance only | n/a |
| Max audio | 30 s | continuous | continuous | 2 h/file |
| Audio in | WAV, MP3, AAC, AIFF, OGG, OPUS, FLAC, MP4, AMR, WMA, WebM. Raw PCM must be 16 kHz with `input_audio_codec`. | **raw PCM only**: `linear16` (default), `linear32`, `mulaw`, `alaw`; mono; `sample_rate` **8000 or 16000 only** (anything else closes with 4000) | WAV or raw PCM (`pcm_s16le`, `pcm_l16`, `pcm_raw`), 8 or 16 kHz | most formats |
| Mid-call reconfig | n/a | `config.update`, no reconnect | reconnect | n/a |

Source: [Which STT API](https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/which-api-to-use). The legacy streaming page still labels Realtime as "`saaras:v3-realtime`, beta", and the API reference lists "beta denied" as one cause of close code `4000`. So **a trial key might be refused on Realtime. Fall back to the legacy WS if that happens** **[inference]**. ([legacy streaming](https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/streaming-api), [Realtime API ref](https://docs.sarvam.ai/api-reference/speech-to-text/transcribe/realtime/ws))

Browser auth on Realtime can go through a WebSocket subprotocol `api-subscription-key.<key>`. Don't ship a key to the browser. Proxy through your backend instead. ([API ref](https://docs.sarvam.ai/api-reference/speech-to-text/transcribe/realtime/ws))

### Realtime WS protocol (the one to build on)

Query parameters: `language_code` (required), `model`, `stream_type` (`fast` | `balanced` (default) | `simulated` (no partials)), `mode`, `endpointing` (`vad` default | `manual`), `encoding`, `sample_rate`, `threshold` (default 0.3), `silence_duration_ms` (default **500**), `min_speech_duration_ms` (default 250), `return_timestamps`, `prompt`, and `keyterms` (v4 only).

- Client → server: `{"event":"audio_input","audio":"<base64>"}`, `speech_start` / `speech_end` / `flush` (manual mode), `config.update`, `end`, `ping`.
- Server → client: `session.begin`, **`vad.speech_start` / `vad.speech_end`** (the end-of-speech signal), `transcript.partial`, `transcript.final`, `config.updated`, `pong`, `session.end` (`audio_duration_s` = **billed audio**), and `error` (`code`, `is_fatal`, `message`).
- Close codes: `1003` rate limit, quota or bad key; `1008` inactivity (send `ping`); `1011` server error; `4000` bad parameter, account not enabled, or beta denied.
- Sarvam's advice: use `stream_type="fast"` for agents, and trigger barge-in on `vad.speech_start` or early partials rather than on the final transcript.

Source: [Realtime guide](https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/realtime-streaming), [API ref](https://docs.sarvam.ai/api-reference/speech-to-text/transcribe/realtime/ws).

On the legacy WS, VAD signals are opt-in. Set `vad_signals=true` to get `START_SPEECH`/`END_SPEECH` events, and `high_vad_sensitivity=true` for an end-of-speech silence of about 64 ms at 16 kHz (the default is 1 s of silence). There are also 10 frame-count tuning parameters (1 frame = 512 samples = 32 ms at 16 kHz), and `flush_signal` for manual finalization. ([legacy streaming](https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/streaming-api))

### STT latency

| Claim | Value | Source |
|---|---|---|
| Saaras V3 realtime "Fast" mode | "guarantees less than 150 milliseconds time to first token" | [Saaras V3 blog](https://www.sarvam.ai/blogs/asr) (vendor claim) |
| STT processing latency (LiveKit plugin) | ~70 ms; Sarvam recommends `min_endpointing_delay=0.07` | [LiveKit guide](https://docs.sarvam.ai/api/integration/build-voice-agent-with-live-kit) |
| Sarvam SLO for `transcription_delay` p95 | good < 400 ms, acceptable < 700 ms | [LiveKit in Production](https://docs.sarvam.ai/api/integration/livekit-production-best-practices) |
| Pipecat's TTFS p99 constants | `SARVAM_TTFS_P99 = 1.17` s (legacy, measured with VAD `stop_secs=0.2`). `SARVAM_REALTIME_TTFS_P99 = 1.00` s, commented "Provisional until benchmarked". | [`stt_latency.py` v1.12.0](https://github.com/pipecat-ai/pipecat/blob/v1.12.0/src/pipecat/services/stt_latency.py) |
| Default end-of-turn silence | 500 ms (`silence_duration_ms`) on Realtime | [Realtime guide](https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/realtime-streaming) |

---

## 2. Text-to-speech (Bulbul)

| Item | Fact | Source |
|---|---|---|
| Model | `bulbul:v3` is the only served model. Pipecat 1.9.0 notes "Sarvam's API no longer serves `bulbul:v2` and rejects requests for it". Bulbul V4 was announced as a "Research preview" at Sarvam Epoch and is not in the API docs. | [Bulbul](https://docs.sarvam.ai/api/getting-started/models/bulbul), [Pipecat CHANGELOG 1.9.0](https://github.com/pipecat-ai/pipecat/blob/v1.12.0/CHANGELOG.md), [Epoch summary](https://www.sarvam.ai/epoch/summary) |
| Languages | 11: `hi-IN bn-IN ta-IN te-IN gu-IN kn-IN ml-IN mr-IN pa-IN od-IN en-IN` | [Bulbul](https://docs.sarvam.ai/api/getting-started/models/bulbul) |
| Voices (v3) | Shubh (default), Aditya, Ritu, Priya, Neha, Rahul, Pooja, Rohan, Simran, Kavya, Amit, Dev, Ishita, Shreya, Ratan, Varun, Manan, Sumit, Roopa, Kabir, Aayan, Ashutosh, Advait, Anand, Tanya, Tarun, Sunny, Mani, Gokul, Vijay, Shruti, Suhani, Mohit, Kavitha, Rehan, Soham, Rupali. Use lowercase IDs (`speaker="priya"`). v2 voices such as `anushka` are rejected. | [Bulbul](https://docs.sarvam.ai/api/getting-started/models/bulbul), [voices page](https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/voices) |
| Controls | `pace` 0.5–2.0, `temperature` 0.01–1.0 (default 0.6). **No `pitch`/`loudness` on v3 and no SSML.** Preprocessing is always on. | [Bulbul](https://docs.sarvam.ai/api/getting-started/models/bulbul), [Pipecat guide](https://docs.sarvam.ai/api/integration/pipecat-production-guide) |
| Sample rates | 8000 / 16000 / 22050 / **24000 (default)** on every transport. 32/44.1/48 kHz on REST only. Streaming is capped at 24 kHz. | [Bulbul](https://docs.sarvam.ai/api/getting-started/models/bulbul) |
| Codecs | `mp3 wav aac opus flac linear16 mulaw alaw`. On WS use `linear16` (no decode hop). | [TTS overview](https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/overview), [LiveKit in Production](https://docs.sarvam.ai/api/integration/livekit-production-best-practices) |
| Input text | Native script works best. "Romanised Indic input degrades quality": write `आपका order confirm हो गया है`, not `Aapka order confirm ho gaya hai`. **So prompt the LLM to emit Hindi words in Devanagari.** | [Bulbul known limitations](https://docs.sarvam.ai/api/getting-started/models/bulbul) |

### Transports

| | REST | HTTP stream | **WebSocket (use this)** |
|---|---|---|---|
| Endpoint | `POST /text-to-speech` | `POST /text-to-speech/stream` | `wss://api.sarvam.ai/text-to-speech/ws` |
| Output | base64 in JSON after full synthesis | raw binary chunks | base64 chunks, many utterances per socket |
| Max text | 2,500 chars | 3,500 chars | 2,500 per message (< 500 recommended) |
| TTFA | full synthesis time | low | lowest on a warm socket |

WS protocol: send a `config` message first (`speaker`, `language_code`, `pace`, `min_buffer_size` (default 50 chars), `max_chunk_length`, `output_audio_codec`, `output_audio_bitrate`). Then send `text` messages and `flush`. `send_completion_event=true` produces a `final` event. The socket closes after about 1 min idle, so send `ping`. Source: [which TTS API](https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/which-api-to-use), [WS guide](https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/streaming-api/web-socket), [HTTP stream](https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/streaming-api/http-stream).

### TTS latency

- "Sub-250ms first-byte latency" and "<250ms First-byte latency" ([sarvam.ai TTS for voice agents](https://www.sarvam.ai/text-to-speech/voice-agents), vendor claim).
- Sarvam's SLO: `tts_node_ttfb` p95 good < 350 ms, acceptable < 600 ms. They say TTFB "is dominated by connection state, not model speed", so pre-warm the socket and lower `min_buffer_size`. ([LiveKit in Production](https://docs.sarvam.ai/api/integration/livekit-production-best-practices))
- There is no in-band cancel on the WS. On barge-in, drop the audio you have already received, and keep each `convert()` short. ([WS guide](https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/streaming-api/web-socket))

---

## 3. LLM (chat completions)

| Model ID | Endpoint | Context | Notes | Source |
|---|---|---|---|---|
| **`sarvam-105b-conversations`** | `POST https://api.sarvam.ai/v1/chat/completions` (**v1 only**) | 32K | "post-trained for real-time dialogue and voice agents". Same request schema as 105B. Pipecat rejects `reasoning_effort` on it. | [Sarvam-105B](https://docs.sarvam.ai/api/getting-started/models/sarvam-105b), [Pipecat LLM docs](https://docs.pipecat.ai/api-reference/server/services/llm/sarvam) |
| `sarvam-105b` | `/v1` (GA) and `/v2` (beta) | 128K | MoE (128 experts) with MLA, Apache-2.0 weights. **Reasoning is ON by default**: the model page says `low`, the API reference says `medium`. Disable it with `reasoning_effort: null`. Reasoning tokens are billed as output and can eat a small `max_tokens`. | [Sarvam-105B](https://docs.sarvam.ai/api/getting-started/models/sarvam-105b), [v1 API ref](https://docs.sarvam.ai/api-reference/chat/chat-completions-v1) |
| `gemma4`, `glm5.3`, `deepseekv4-flash` | `/v2/chat/completions` only | 131K / 1M / 1M | **Beta, and each key must be whitelisted** (otherwise `400 invalid_request_error`) | [Beta APIs](https://docs.sarvam.ai/api-reference/beta-apis), [open-weight](https://docs.sarvam.ai/api/getting-started/models/openweight) |
| `sarvam-m`, `sarvam-30b` | none | | Deprecated. Requests fail (`400 ... has been deprecated`). | [Models](https://docs.sarvam.ai/api/getting-started/models), [changelog 2026-08-18](https://docs.sarvam.ai/changelog/2026/8/18), [sarvamai/skills](https://github.com/sarvamai/skills/blob/main/voice-agents/SKILL.md) |

- **OpenAI-compatible: yes.** Requests and responses use the OpenAI chat schema, and streaming is supported (`delta.content`, plus `delta.reasoning_content` when reasoning is on). Auth is `api-subscription-key: <key>`, and `Authorization: Bearer <key>` is also accepted on all endpoints "for OpenAI-compatible tooling". The `sarvamai/skills` repo says "NOT Authorization: Bearer", but that is outdated; the auth docs supersede it. ([Chat overview](https://docs.sarvam.ai/api/api-guides-tutorials/chat-completion/overview), [Authentication](https://docs.sarvam.ai/api-reference/authentication))
- **Tool calling: yes.** `tools` (function only) and `tool_choice` (`auto` / `none` / `required` / named) work, along with `response_format` for JSON. **`parallel_tool_calls: false` is NOT enforced on `sarvam-105b`.** ([Chat overview](https://docs.sarvam.ai/api/api-guides-tutorials/chat-completion/overview), [v1 API ref](https://docs.sarvam.ai/api-reference/chat/chat-completions-v1)) Sarvam's Epoch benchmark claims the conversational 105B scores 78.8 on tool calling, against 57.6 for GPT 5.4 Mini (vendor benchmark). ([Epoch](https://www.sarvam.ai/epoch/summary))
- **Speed:** no published TTFT or tokens/s for 105B on the API. The only numbers are Gemma 4 31B at "0.63 seconds p50 time to first token" and GLM 5.2 at "up to 80 tokens per second" ([Epoch](https://www.sarvam.ai/epoch/summary)). **[inference]** Expect 105B-conversations TTFT on the order of 0.4–1 s from India. Measure it before you commit:
  ```bash
  curl -sN -o /dev/null -w 'ttfb=%{time_starttransfer}s total=%{time_total}s\n' \
    https://api.sarvam.ai/v1/chat/completions -H "api-subscription-key: $SARVAM_API_KEY" \
    -H 'Content-Type: application/json' \
    -d '{"model":"sarvam-105b-conversations","stream":true,"max_tokens":120,"messages":[{"role":"user","content":"मुझे kal ka weather batao"}]}'
  ```
- Limits (v1): `max_tokens` max is Starter 4096 / Pro 16384 / Business 128000 (default 2048), `temperature` 0–2, `stop` ≤ 4. No `developer` role (Pipecat converts it to `user`). ([Sarvam-105B](https://docs.sarvam.ai/api/getting-started/models/sarvam-105b), [Pipecat llm.py](https://github.com/pipecat-ai/pipecat/blob/v1.12.0/src/pipecat/services/sarvam/llm.py))

**Recommendation:** use `sarvam-105b-conversations` on `/v1` for the voice loop. It is GA, needs no whitelist, has no reasoning overhead, and is tuned for colloquial code-mixed replies. Use `sarvam-105b` with `reasoning_effort` only for an offline or slow-path tool.

---

## 4. Pricing, credits, and what 100 credits buy

**Is 100 credits = ₹100? Yes.** The pricing FAQ says: "When you make a payment, you receive the same number of credits as the amount paid. For example, ₹1,000 gives you 1,000 credits." Every new user gets "₹100 worth of free credits". Credits never expire, and one organisation-level balance is shared across all Sarvam products, including Voice Agents. Once credits run out, calls return `402`. ([sarvam.ai/api-pricing](https://www.sarvam.ai/api-pricing) FAQ JSON-LD, [Credits & Rate Limits](https://docs.sarvam.ai/api/getting-started/ratelimits), [Billing](https://docs.sarvam.ai/api/platform/billing))

### Rates (₹, verified on the docs pricing page and the sarvam.ai pricing page)

| Service | Rate | ₹100 buys |
|---|---|---|
| STT (REST / streaming / batch, incl. translate) | ₹30 / hour, billed per second | **200 min = 3 h 20 m of audio** |
| STT with diarization | ₹45 / hour | 133 min |
| TTS Bulbul v3 (REST and streaming) | ₹30 / 10K chars (₹3 / 1K) | **33,333 characters ≈ 35–40 min of speech** (at ~15 chars/s **[inference]**) |
| LLM `sarvam-105b`, `-conversations` | ₹29.28 input / ₹10.98 cached / ₹73.20 output per 1M tokens | **3.4M input tokens or 1.37M output tokens** |
| LLM `deepseekv4-flash` (beta) | ₹19.8 / ₹0.63 / ₹59.4 per 1M | needs whitelist |
| LLM `gemma4` (beta) | ₹36.6 / ₹13.73 / ₹91.5 per 1M | needs whitelist |
| Voice Agents (hosted platform) | **₹3.50 / minute**, "authoring, simulation, phone numbers, evaluation, and analytics included" | **~28 min** |

Sources: [docs pricing](https://docs.sarvam.ai/api/getting-started/pricing), [sarvam.ai/api-pricing](https://www.sarvam.ai/api-pricing), [Epoch summary](https://www.sarvam.ai/epoch/summary) (for Voice Agents ₹3.50/min). Third-party blogs quote ₹1/min for voice agents, but that is not on any Sarvam page.

**Doc inconsistencies to know about:**
- The STT FAQ says "Speaker diarization (+20%)" and "Language detection (+10%)", but the pricing page shows diarization at +50% (₹45 vs ₹30) and no language-detection surcharge. ([STT FAQ](https://docs.sarvam.ai/api/speech-to-text/faq)) Treat `language_code="auto"` as possibly +10%.
- The docs list `glm5.3`, but the sarvam.ai pricing page and Pipecat list `glm5.2`.

### Budget for a cascaded demo [inference]

Streaming STT bills the audio you **send**. `session.end.audio_duration_s` is "the billed audio quantity". Pipecat streams mic audio continuously, so **an open session costs ₹0.50 per minute even when nobody is talking.**

Assume one conversation-minute has about 5 turns and the bot speaks about 40% of the time:
- STT: 60 s × ₹30/h = **₹0.50**.
- TTS: about 24 s × 15 chars/s ≈ 360 chars ≈ **₹1.08**.
- LLM: 5 turns × (about 1.5K prompt tokens + 80 output tokens) ≈ 5 × ₹0.05 ≈ **₹0.25**.

That is **about ₹1.8–2 per minute, or roughly 50 conversation-minutes from ₹100.** Rehearsals use the same pool. To make it last:
- close sockets when idle (`user_idle_timeout` → end session);
- pre-generate fixed prompts such as the greeting once and replay them;
- keep replies to 1–2 sentences;
- don't loop TTS tests.

### Rate limits (Starter = pay-as-you-go; the trial account is presumably on Starter **[inference]**)

| API | Starter |
|---|---|
| STT REST | 60 req/min |
| STT WebSocket | 20 concurrent |
| TTS REST | 60 req/min (**`bulbul:v3`: 30 req/min**) |
| TTS WebSocket | 60 concurrent (**`bulbul:v3`: 30 concurrent**) |
| LLM `sarvam-105b`/`-conversations` | **40 req/min** |
| LLM others | 60 req/min |

Limits apply per account, not per key, as a token bucket. WS connections opened in a fast burst can be rejected with close `1003` "well below" the ceilings, so space reconnects by about 300 ms or more. Your actual limits are at dashboard → Rate Limits. ([Credits & Rate Limits](https://docs.sarvam.ai/api/getting-started/ratelimits)) For a single-user demo these limits are fine.

---

## 5. Pipecat integration

### Status (verified against source at tag v1.12.0)

| Item | Fact | Source |
|---|---|---|
| Latest `pipecat-ai` | **1.12.0** (2026-09-26). Requires **Python ≥ 3.11**; Sarvam's guide still says 3.9+. | [PyPI](https://pypi.org/project/pipecat-ai/) |
| Install | `pip install "pipecat-ai[sarvam]"`. The extra pins **`sarvamai==0.1.28`** (latest SDK is 0.1.35, so don't pin a newer `sarvamai` alongside it). Add `silero`, `webrtc`, `runner` (or `daily`) for VAD and transport. | PyPI metadata |
| Services | `pipecat.services.sarvam.stt.SarvamRealtimeSTTService` (Realtime WS, added 1.8.0, `saaras:v4` accepted since 1.11.0); `SarvamSTTService` (legacy WS, default `saaras:v4`); `pipecat.services.sarvam.tts.SarvamTTSService` (WS, default `bulbul:v3` since 1.9.0); `SarvamHttpTTSService` (REST); `pipecat.services.sarvam.llm.SarvamLLMService` (subclass of `OpenAILLMService`, streaming and function calling) | [services/sarvam](https://github.com/pipecat-ai/pipecat/tree/v1.12.0/src/pipecat/services/sarvam), [Pipecat docs STT](https://docs.pipecat.ai/api-reference/server/services/stt/sarvam), [TTS](https://docs.pipecat.ai/api-reference/server/services/tts/sarvam), [LLM](https://docs.pipecat.ai/api-reference/server/services/llm/sarvam) |
| Official examples | `examples/voice/voice-sarvam.py`, `voice-sarvam-realtime.py` (manual endpointing + Silero), `voice-sarvam-realtime-turn-detection.py` (server VAD + Silero), `voice-sarvam-vad-http.py`, `function-calling/function-calling-sarvam.py`. Both realtime examples use **OpenAI** as the LLM. | [repo tree v1.12.0](https://github.com/pipecat-ai/pipecat/tree/v1.12.0/examples/voice) |
| Streaming | STT and TTS both use WebSockets. The LLM uses SSE. `SarvamHttpTTSService` is REST, and Sarvam says it is "too slow for live conversation". | [Sarvam Pipecat guide](https://docs.sarvam.ai/api/integration/pipecat-production-guide) |

### Known issues and gotchas

1. **`SarvamLLMService` sends models to `/v2` (beta) by default.** Since 1.8.0 the base URL is "`/v1` for `sarvam-105b-conversations`, `/v2` for all other models". `/v2` needs per-key whitelisting. So the default `SarvamLLMService(api_key=...)` (model `sarvam-105b`), and Sarvam's own quickstart snippet `Settings(model="sarvam-105b")`, will likely fail on a trial key with `400 invalid_request_error` **[inference from the two docs]**. **Fix:** use `model="sarvam-105b-conversations"`, or pass `base_url="https://api.sarvam.ai/v1"`. ([CHANGELOG 1.8.0](https://github.com/pipecat-ai/pipecat/blob/v1.12.0/CHANGELOG.md), [llm.py](https://github.com/pipecat-ai/pipecat/blob/v1.12.0/src/pipecat/services/sarvam/llm.py), [Beta APIs](https://docs.sarvam.ai/api-reference/beta-apis))
2. **You can't turn reasoning off for `sarvam-105b` through `Settings`.** In Pipecat `reasoning_effort=None` means "omit the field", so the server default (reasoning on) stays in effect, which adds latency and output tokens. The conversations variant avoids this. A possible workaround is `Settings(extra={"reasoning_effort": None})` **[inference, untested]**. ([llm.py](https://github.com/pipecat-ai/pipecat/blob/v1.12.0/src/pipecat/services/sarvam/llm.py))
3. **Sarvam's Pipecat docs are behind 1.12.** The [quickstart](https://docs.sarvam.ai/api/integration/build-voice-agent-with-pipecat) passes `language=`, `speaker=`, `language_code=` and `pace=` as constructor kwargs. In 1.12 these belong in `settings=...Settings(...)`. `SarvamRealtimeSTTService` raises `TypeError` for settings passed as kwargs, and `SarvamTTSService` has no `speaker` or `language_code` constructor args. The [production guide](https://docs.sarvam.ai/api/integration/pipecat-production-guide) says realtime `stream_type` defaults to `"fast"` with a 500 ms client-side chunk floor. In 1.12 source the default is **`"balanced"`** and the client always sends **50 ms chunks** (`_CLIENT_CHUNK_MS = 50`). **Set `stream_type="fast"` explicitly.** ([stt.py](https://github.com/pipecat-ai/pipecat/blob/v1.12.0/src/pipecat/services/sarvam/stt.py))
4. **The VAD advice conflicts.** Sarvam's guide says "Do not add `SileroVADAnalyzer`". Pipecat 1.12 docs say "A VAD analyzer is required in either endpointing mode. Under `vad` it times transcription latency." Both official Pipecat examples add Silero. In `endpointing="vad"` mode the service emits `ProposedUserStarted/StoppedSpeakingFrame` and auto-installs `ExternalUserTurnStrategies`, so Sarvam's server VAD still owns the turns. **Follow Pipecat's examples and add Silero** **[inference]**.
5. **No automatic reconnect** on the realtime STT socket. `reconnect_on_error` is forced off and passing it raises `TypeError`. Handle `on_connection_error` yourself. ([stt.py](https://github.com/pipecat-ai/pipecat/blob/v1.12.0/src/pipecat/services/sarvam/stt.py))
6. Realtime defaults: `language_code="en-IN"`, `model="saaras:v3-realtime"`, `mode="transcribe"`. **Set `hi-IN` (or `auto`) and `mode="codemix"` for Hinglish.**
7. TTS: always pass `model="bulbul:v3"` and v3 voices. Set the constructor `sample_rate` to match your transport (the default is 24000; `PipelineParams.audio_out_sample_rate` is ignored). Lower `min_buffer_size` from 50: Sarvam's Pipecat guide says 15–25, but the LiveKit plugin validates 30–200, so **30 is the safe value [inference]**. The WS service can't emit μ-law, which only matters for telephony. ([Sarvam Pipecat guide](https://docs.sarvam.ai/api/integration/pipecat-production-guide), [LiveKit in Production](https://docs.sarvam.ai/api/integration/livekit-production-best-practices))
8. Fixed in recent releases, so stay on ≥ 1.11: `SarvamSTTService` labelled every transcript as Hindi (fixed 1.9.0). It also sent `finalized=False`, which delayed turn end (fixed 1.11.0). `SarvamHttpTTSService` ignored `sample_rate` and played at the wrong speed (fixed 1.9.0). ([CHANGELOG](https://github.com/pipecat-ai/pipecat/blob/v1.12.0/CHANGELOG.md))

### Minimal pipeline (adapted from Pipecat v1.12.0 `voice-sarvam-realtime-turn-detection.py` and `function-calling-sarvam.py`; **not executed**)

```python
# pip install "pipecat-ai[sarvam,silero,webrtc,runner]==1.12.0" python-dotenv   (Python >= 3.11)
import os
from dotenv import load_dotenv
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair, LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.sarvam.llm import SarvamLLMService
from pipecat.services.sarvam.stt import SarvamRealtimeSTTService
from pipecat.services.sarvam.tts import SarvamTTSService
from pipecat.transports.base_transport import TransportParams
from pipecat.workers.runner import WorkerRunner

load_dotenv(override=True)
KEY = os.environ["SARVAM_API_KEY"]

async def bot(runner_args: RunnerArguments):
    transport = await create_transport(runner_args, {
        "webrtc": lambda: TransportParams(audio_in_enabled=True, audio_out_enabled=True),
    })

    stt = SarvamRealtimeSTTService(          # wss://api.sarvam.ai/speech-to-text-realtime/ws
        api_key=KEY,
        sample_rate=16000,                   # 8000 or 16000 only
        settings=SarvamRealtimeSTTService.Settings(
            model="saaras:v3-realtime",      # or "saaras:v4" (+ keyterms)
            language_code="hi-IN",           # or "auto"
            mode="codemix",                  # Hinglish: "मेरा phone number है"
            stream_type="fast",              # 1.12 default is "balanced"
            silence_duration_ms=300,         # server end-of-turn silence (default 500)
        ),
    )
    llm = SarvamLLMService(
        api_key=KEY,
        settings=SarvamLLMService.Settings(
            model="sarvam-105b-conversations",   # -> /v1 (GA). Plain sarvam-105b -> /v2 (beta whitelist)
            system_instruction=(
                "You are a voice assistant. Reply in one or two short spoken sentences, no markdown or emoji. "
                "Reply in the user's language; for Hinglish write Hindi words in Devanagari and English words in Latin script."
            ),
            max_tokens=200,
        ),
    )
    tts = SarvamTTSService(                  # wss://api.sarvam.ai/text-to-speech/ws
        api_key=KEY,
        sample_rate=24000,                   # match your output transport
        settings=SarvamTTSService.Settings(
            model="bulbul:v3", voice="priya", language="hi-IN",
            pace=1.1, min_buffer_size=30,
        ),
    )

    context = LLMContext()                   # pass tools=[...] here for function calling
    user_agg, assistant_agg = LLMContextAggregatorPair(
        context, user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )
    pipeline = Pipeline([transport.input(), stt, user_agg, llm, tts, transport.output(), assistant_agg])
    worker = PipelineWorker(pipeline, params=PipelineParams(
        audio_in_sample_rate=16000, audio_out_sample_rate=24000,
        enable_metrics=True, enable_usage_metrics=True,
    ))
    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        context.add_message({"role": "developer", "content": "Greet the user briefly in Hinglish."})
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        await runner.cancel()

    @stt.event_handler("on_connection_error")
    async def on_stt_error(service, error):
        await runner.cancel()                # realtime STT never auto-reconnects

    await runner.run()

if __name__ == "__main__":
    from pipecat.runner.run import main
    main()
```

Alternative framework: LiveKit Agents ships `livekit-plugins-sarvam` (`STTStreaming`, TTS with `prewarm()`, and LLM). Sarvam has a separate [LiveKit production guide](https://docs.sarvam.ai/api/integration/livekit-production-best-practices).

---

## 6. Lower-latency option: Sarvam Voice Agents (formerly "Samvaad")

- **What it is:** a hosted platform at [indus.sarvam.ai/samvaad](https://indus.sarvam.ai/samvaad) for building, testing, deploying and monitoring voice agents. Internally it is still a **cascade**, "a real-time ASR → LLM → TTS loop", built on Saaras v4, "a constellation of open-weight models along with `sarvam-105b-conversations`" (routed automatically), and Bulbul v3. All of these are self-hosted and co-located, with "no external network hops between stages". **No speech-to-speech endpoint exists in the API docs.** ([Voice Agents overview](https://docs.sarvam.ai/conversations/overview), [Models](https://docs.sarvam.ai/conversations/build/models))
- **Latency claims:** "sub-second latencies, even at scale" ([Run-time](https://docs.sarvam.ai/conversations/build/run-time)) and "<500ms Real-time latency" ([product page](https://www.sarvam.ai/products/voice-agents)). These are vendor claims.
- **Programmatic access:** Python `pip install "sarvam-conv-ai-sdk[all]"` (v1.1.1) with `AsyncSamvaadAgent`, plus a headless mode where you push 16-bit PCM yourself. Web: `npm install sarvam-conv-ai-sdk` with `ConversationAgent` and `BrowserAudioInterface` from `sarvam-conv-ai-sdk/browser`. React Native and Flutter SDKs also exist, and there is an embeddable widget. The SDKs need `org_id`, `workspace_id`, `app_id` (agent) and an API key. Keep the key server-side. ([Python SDK](https://docs.sarvam.ai/conversations/deploy/sdks/python), [Web SDK](https://docs.sarvam.ai/conversations/deploy/sdks/web), [Deploy with code](https://docs.sarvam.ai/conversations/deploy/deploy-with-code))
- **Constraints:** "Voice Agents does **not** support bringing your own models at any part of the stack". Custom logic goes through tools (HTTP/API tools; Python "Code Tools" are on request), a knowledge base, and states. It covers 11 languages (the Bulbul set plus Assamese) and handles code-mixing. Price is ₹3.50/min, or about 28 minutes from 100 credits. ([Models](https://docs.sarvam.ai/conversations/build/models), [Epoch](https://www.sarvam.ai/epoch/summary), [changelog 2026-08-15](https://docs.sarvam.ai/changelog/2026/8/15))
- **When to choose it [inference]:** pick it if the demo only needs a talking agent with a few HTTP tools, and you want the best latency for the least work. Pick the Pipecat cascade if KBOS needs its own orchestration, custom turn logic, a different LLM or classifier in the loop, or more demo minutes per credit.

---

## 7. Expected end-to-end latency for a Pipecat cascade [inference unless cited]

| Stage | Budget | Basis |
|---|---|---|
| End-of-speech detection | 300–500 ms | `silence_duration_ms` (default 500) |
| Final transcript after speech end | ~100–300 ms | Sarvam's 70 ms processing claim and < 150 ms Fast-mode TTFT claim, plus network |
| LLM TTFT (`sarvam-105b-conversations`, short prompt) | ~400–1000 ms | unmeasured; Gemma 4 31B p50 is 0.63 s |
| Pipecat sentence aggregation + TTS first byte | ~250–400 ms | < 250 ms claim; SLO p95 < 350 ms |
| **Total, end of speech to first audio** | **~1.0–2.0 s untuned, ~0.9–1.3 s tuned** | Sarvam's own target: p50 < 900 ms "good", < 1.4 s "acceptable" ([LiveKit in Production](https://docs.sarvam.ai/api/integration/livekit-production-best-practices)) |

The biggest levers are `stream_type="fast"`, a lower `silence_duration_ms`, a short system prompt and short replies, the conversations model with no reasoning, TTS `min_buffer_size` of about 30 on a warm socket, and running from an India region. Turn on `enable_metrics` and read the TTFB and TTFA metrics instead of guessing.

## Sources (primary)

- Sarvam docs index: https://docs.sarvam.ai/llms.txt ; Models: https://docs.sarvam.ai/api/getting-started/models
- STT: https://docs.sarvam.ai/api/getting-started/models/saaras , https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/which-api-to-use , https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/realtime-streaming , https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/streaming-api , https://docs.sarvam.ai/api-reference/speech-to-text/transcribe/realtime/ws , https://docs.sarvam.ai/api/speech-to-text/faq , https://www.sarvam.ai/blogs/asr
- TTS: https://docs.sarvam.ai/api/getting-started/models/bulbul , https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/which-api-to-use , https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/streaming-api/web-socket , https://www.sarvam.ai/text-to-speech/voice-agents
- LLM: https://docs.sarvam.ai/api/getting-started/models/sarvam-105b , https://docs.sarvam.ai/api/api-guides-tutorials/chat-completion/overview , https://docs.sarvam.ai/api-reference/chat/chat-completions-v1 , https://docs.sarvam.ai/api-reference/beta-apis , https://docs.sarvam.ai/api-reference/authentication
- Pricing/credits: https://docs.sarvam.ai/api/getting-started/pricing , https://www.sarvam.ai/api-pricing , https://docs.sarvam.ai/api/getting-started/ratelimits , https://docs.sarvam.ai/api/platform/billing , https://www.sarvam.ai/epoch/summary
- Integrations: https://docs.sarvam.ai/api/integration/build-voice-agent-with-pipecat , https://docs.sarvam.ai/api/integration/pipecat-production-guide , https://docs.sarvam.ai/api/integration/livekit-production-best-practices , https://github.com/sarvamai/skills/blob/main/voice-agents/SKILL.md
- Pipecat v1.12.0: https://pypi.org/project/pipecat-ai/ , https://github.com/pipecat-ai/pipecat/tree/v1.12.0/src/pipecat/services/sarvam , https://github.com/pipecat-ai/pipecat/blob/v1.12.0/CHANGELOG.md , https://docs.pipecat.ai/api-reference/server/services/stt/sarvam , https://docs.pipecat.ai/api-reference/server/services/tts/sarvam , https://docs.pipecat.ai/api-reference/server/services/llm/sarvam
- Voice Agents: https://docs.sarvam.ai/conversations/overview , https://docs.sarvam.ai/conversations/build/models , https://docs.sarvam.ai/conversations/build/run-time , https://docs.sarvam.ai/conversations/deploy/sdks/python , https://docs.sarvam.ai/conversations/deploy/sdks/web , https://www.sarvam.ai/products/voice-agents

---

## 8. Verified while building KBOS (2026-10-02)

- All 8 trial keys work on `sarvam-105b-conversations` (v1), realtime STT `saaras:v4` and `bulbul:v3` WS. Realtime STT is **not** beta-gated for them.
- **The gateway intermittently returns HTTP 404** on `/v1/chat/completions` and on the TTS WebSocket handshake (about 2 in 9 requests at one point, then fine). Retry them; the voice services retry connects.
- **Realtime STT keyterms:** pass `keyterms` as a JSON array string in the query (`["KB","4B",...]`); it works with `saaras:v4`.
- **Realtime STT, `endpointing=manual`:** audio sent before `speech_start` is ignored (the first syllable gets lost). An idle socket (no audio) drops after about 2 s without a close frame, so send `{"event":"ping"}` about every 1 s.
- Measured: speech_end → final ≈ 0.16–0.3 s (manual endpointing, `stream_type=fast`). TTS first audio ≈ 0.2–0.25 s. LLM TTFT ≈ 0.16–0.23 s for short prompts, 0.35–1.0 s with KB's ~2k-token prompt.
