# Gnani (Vachana) speech APIs: research notes for KBOS

Researched 2026-10-01. Sources are primary unless noted. They are Gnani's docs at `docs.gnani.ai` (including the `llms-full.txt` dump), the public pricing endpoint, the JS bundle of the `app.gnani.ai/voice` dashboard, the PyPI wheels (`gnani-vachana` 0.7.9, `pipecat-gnani` 0.5.12, `livekit-plugins-gnani` 1.8.3), and the Pipecat and `pipecat-ai/docs` GitHub repos. I had no API key, so **nothing here was tested against the live API**. Claims marked **[inference]** are mine, not from a source. Claims marked **[marketing]** come from gnani.ai product pages, not the docs.

## TL;DR

- **Naming.** The developer product is "Gnani Speech APIs". The API host is `api.vachana.ai`, and the SDK is `gnani-vachana` (import name `gnani`). STT is **Gnani Prisma v2.5** and TTS is **Gnani Timbre v2.5**. The no-code agent product ("Agent Builder", formerly Inya) is separate, with its own API at `api.inya.ai/platform`. "Armour365" is not part of this developer platform.
- **"60 Request of API" is a rate limit of 60 requests per minute. It is not a quota of 60 calls.** The dashboard code renders that tile from a field called `requests_per_minute`. The public pricing endpoint lists `"limit":"60 requests/minute"` for STT REST, STT Batch and TTS, and `"20 concurrent sessions"` for STT WebSocket. The other two numbers are 1000 credits converted at list price: 1 credit = ₹1, STT is ₹27/hour (1000/27 = **37.04 h**), and TTS is ₹27 per 10,000 chars (**370,370 chars**). The math matches the trial screen exactly.
- **Live demo is viable.** Both STT and TTS have WebSocket streaming. STT returns **final transcripts only** (one per server-VAD segment, no partials). Gnani's own figure is "~300–500 ms from end of speech to transcript", on top of a 500 ms default silence timer that can be tuned down to 300 ms. TTS has a WebSocket with base64 PCM chunks. Gnani does not document TTS time-to-first-byte; its marketing claims range from "<250 ms" to "sub-100 ms".
- **Pipecat support: a community package exists, and it is currently broken on current Pipecat.** `pipecat-gnani` (maintained by Gnani, BSD-2) appears as **Community** in Pipecat's supported-services list. There is nothing Gnani in `pipecat-ai` itself (v1.12.0). Version 0.5.12 **fails to import on pipecat-ai ≥ 1.8** (`_NotGiven` was renamed). Its TTS also doesn't stop audio on barge-in, and its STT leaks sockets on errors. Open PRs #2, #3 and #4 fix all three, but none are merged. Plan to **vendor and patch it (~1–2 h)** or write your own (~0.5–1 day).
- **LLM / speech-to-speech: no usable public API.** Gnani markets Evon v3.3 (LLM) and Warp v2.0 (speech-to-speech) as "available via API in minutes" [marketing], but there are no developer docs. The dashboard only has a beta "LLM" playground. Bring your own LLM (Groq, Gemini, Sarvam, …). The 60 RPM limit has nothing to do with LLM calls.

## 1. Decoding the trial credits (verified)

| Trial screen | Source of the number | Meaning |
|---|---|---|
| 1000 credits | Pricing page: "1 Credit = ₹1" | ₹1000 of usage |
| ~37 Hours of STT | Pricing page JS: `stt_hours`; public price **₹27.00 per hour** for STT REST, WebSocket and Batch | 1000 / 27 = 37.04 h |
| ~3,70,370 Chars of TTS | JS: `tts_chars`; public price **₹27.00 per 10,000 chars** | 1000 / 27 × 10,000 = 370,370 |
| 60 Request of API | JS: `{value: W(x?.data?.requests_per_minute), unit:"Request", suffix:"of API"}` | **60 requests/minute rate limit** |

Public pricing endpoint (no auth): `GET https://paymentbck.vachana.ai/api/billing/payment/pricing-detail` returns:

```json
{"data":[
 {"service":"Speech to Text (REST)","price":"₹27.00","unit":"Per Hour","limit":"60 requests/minute"},
 {"service":"Speech to Text (WebSocket)","price":"₹27.00","unit":"Per Hour","limit":"20 concurrent sessions"},
 {"service":"Speech to Text (Batch)","price":"₹27.00","unit":"Per Hour","limit":"60 requests/minute"},
 {"service":"Text to Speech","price":"₹27.00","unit":"Per 10,000 Chars","limit":"60 requests/minute"}],
 "success":true}
```

Pricing FAQ (from the `PricingPage` JS chunk of `voice-mfe.gnani.ai`):
- "You'll receive 60 free credits when you first sign up." The user has 1000, so this is probably a promo grant [inference].
- "Speech APIs (STT/TTS) are billed per second of audio processed. Text APIs are billed per token processed." So "text APIs" exist in billing, but none are on the public price list.
- Purchased credits "never expire". Promotional credits **do** carry an expiry date: the dashboard has `promotionalCreditsExpiryDate` and a `__free_credits_expiry_banner__`. Check the expiry date in the dashboard.
- When credits run out, "API calls will start returning errors indicating insufficient credits".
- Higher rate limits require a custom plan ("Contact Sales").

[inference] It is unclear whether STT WebSocket bills streamed audio including silence or only VAD speech. Either way, 37 h is far more than a hackathon needs. It is also unclear whether each message on the TTS WebSocket counts against the 60 RPM. Pipecat sends one TTS request per sentence, so a single demo session (≈10–30 sentences/min) fits. Several teammates sharing one key could hit the limit.

## 2. Platform map

| Thing | Value | Source |
|---|---|---|
| Base URL | `https://api.vachana.ai` (WebSocket: `wss://api.vachana.ai/...`) | [API intro](https://docs.gnani.ai/api/introduction/introduction) |
| Auth | Header `X-API-Key-ID: <key>`. The STT WebSocket uses lowercase `x-api-key-id`. Get a key at https://app.gnani.ai/voice. | intro, [quick start](https://docs.gnani.ai/api/introduction/quick-start) |
| Transport | REST, SSE, WebSocket. **No gRPC** on the current platform. | intro |
| Legacy | `gnani-ai/API-service` (gRPC to `asr.gnani.ai`, token emailed, last push 2023-10). **Ignore it**; it is the old platform. | [GitHub](https://github.com/gnani-ai/API-service) |
| Edge | Cloudflare (`cf-ray …-BOM` from our network, `x-envoy-upstream-service-time: 4`). Origin region is not documented; it is probably India [inference]. | `curl -D -` |
| Python SDK | `pip install gnani-vachana` (0.7.9, 2026-07-20, Python ≥ 3.10, deps `requests`, `websockets>=12`) | [PyPI](https://pypi.org/project/gnani-vachana/), [SDK docs](https://docs.gnani.ai/python-sdk/introduction) |
| Docs feedback / support | Discord linked from docs | intro |

## 3. Speech-to-text: Gnani Prisma v2.5

### Endpoints

| Mode | Endpoint | Limits |
|---|---|---|
| REST | `POST /stt/v3`, multipart `audio_file`, `language_code` | ≤ 60 s audio (ideal ≤ 30 s). WAV/MP3/OGG/FLAC/AAC/M4A, 8–44.1 kHz, converted to 16 kHz mono server-side. |
| **Realtime** | `wss://api.vachana.ai/stt/v3/stream` | Raw PCM only. **Session hard cap 15 minutes.** 20 concurrent sessions on the trial. |
| Batch | `/stt/v3/batch/jobs…` | Async jobs with diarization. Not relevant for live use. |

Sources: [STT REST](https://docs.gnani.ai/api/STT/speech-to-text), [STT Realtime](https://docs.gnani.ai/api/STT/stt-websocket).

### Languages (STT)

`bn-IN, en-IN, gu-IN, hi-IN, kn-IN, ml-IN, mr-IN, pa-IN, ta-IN, te-IN`: **10 languages**, the same list for REST and streaming. Output is in native script. The Pipecat docs page lists Assamese and Odia too, and the plugin maps `as-IN`/`or-IN`. But Gnani's API docs and the SDK's `STREAM_SUPPORTED_LANGUAGES` do not include them, so treat them as **unsupported**. The marketing page says "40+ languages" [marketing]. The docs say 10.

### Code-mixed Hinglish (STT)

- `en-IN`: the docs tooltip says it "Accepts English-Hindi mixed audio and generates output in English (Latin script)." (STT Realtime, Supported Languages)
- `hi-IN`: Devanagari output. The docs' code-mixed ITN example keeps English words in Latin script: "कल 15:50 को ₹500 transfer करना है". So mixed-script output is expected.
- REST also supports multiple languages at once (`multi_lang_codes`, "multilingual model (supports en-IN, hi-IN)"). LiveKit's plugin docs say the `en-IN,hi-IN` bilingual mode is **batch/REST-only**, not streaming. ([LiveKit Gnani STT](https://docs.livekit.io/agents/models/stt/gnani/))
- **Streaming has no language auto-detect.** `lang_code` is fixed per connection, and changing it means reconnecting.
- Marketing claims "96% Code-Switch Accuracy" and "Under 4% WER" [marketing, unverified] ([STT page](https://www.gnani.ai/speech-to-text-api)).

### Realtime protocol (everything you need to write a client)

Connect with **upgrade headers**. Browsers can't set these, so connect from the server.

| Header | Req | Default | Notes |
|---|---|---|---|
| `x-api-key-id` | yes | | |
| `lang_code` | yes | `en-IN` | BCP-47 code |
| `x-sample-rate` | no | `16000` | `8000`, `16000`, `44100`, `48000`. 44.1k and 48k are resampled server-side. |
| `x-format` | no | `verbatim` | `transcribe` turns on ITN (₹, dates, phone numbers) |
| `itn_native_numerals` | no | `false` | |
| `x-vad-threshold` | no | `0.7` | Clean mic: 0.45–0.55 |
| `x-min-silence-ms` | no | **`500`** | 100–2000. **The main end-of-utterance latency knob.** Use 300–400 for snappy turns. |
| `x-min-speech-ms` | no | `100` | |
| `x-min-segment-ms` | no | `120` | Raising it silently drops short "haan"/"yes" answers |
| `x-max-speech-s` | no | off | Force-close long monologues |
| `x-bias-list` / `x-bias-score` | no | | Word boosting: ≤ 100 single words, score 0/0.5/1/1.5/2. Can be updated mid-session. |
| `x-enable-substitution` / `x-substitution-map` | no | | ≤ 10 find/replace rules |

**Client → server:**
- Binary frames of PCM s16le mono, **exactly 1024 bytes** (512 samples: 32 ms at 16 kHz, 64 ms at 8 kHz), sent at **real-time cadence**. The docs say "Do not buffer and burst; this degrades VAD accuracy."
- Optional JSON text frame `{"type":"update_settings","bias":{…},"substitution":{…}}`.

**Server → client** (JSON text):
- `connected`: sent once, with `config.sample_rate` and `config.chunk_size`=512.
- `processing`: VAD detected **end of speech** and transcription started. This is the end-of-utterance signal, and it arrives before the text.
- `transcript`: `text`, `segment_id`, `segment_index`, `audio_duration_ms`, `latency` (ms from end-of-speech detection to delivery; the doc examples show 318–320). There is **one final transcript per VAD segment**.
- `error`: may be recoverable, in which case the socket stays open.
- `settings_updated`.

**No interim/partial transcripts in the documented protocol.** The `pipecat-gnani` source says "Gnani currently sends final transcripts only", and LiveKit's plugin declares `interim_results=False`. The docs do mention an undocumented `x-partials` header producing `partial_transcript` messages, and a `/stt/v4/stream` route, but only in passing inside the word-boosting section. Neither is specified anywhere [unverified; worth one curl test].

### STT latency

- Docs intro: "P95 ~200 ms for STT". Hugging Face card: "STT latency: P95 < 200ms (streaming)". These numbers measure **after** end-of-speech detection.
- Gnani's own use-case guide: "Latency: ~300–500ms from end of speech to transcript" ([real-time compliance guide](https://docs.gnani.ai/api/use-cases/real-time-compliance)).
- [inference] Expected time from end of the user's speech to final text ≈ `x-min-silence-ms` (500 default, 300 tuned) + ~200–320 ms + RTT. That is **~0.55–0.9 s**. You can't start the LLM early on partials.

## 4. Text-to-speech: Gnani Timbre v2.5

| Mode | Endpoint | Output |
|---|---|---|
| REST | `POST /api/v1/tts/inference` | Full binary audio |
| SSE | `POST /api/v1/tts/sse` | `event: start` / `chunk` (`{"chunk_index","audio":<b64>,"is_final"}`) / `complete` |
| **Realtime** | `wss://api.vachana.ai/api/v1/tts` (header `X-API-Key-ID`) | JSON `{"type":"start"}`, `{"type":"audio","data":{"chunk_index","audio":<b64>,"is_final":false}}`, `{"type":"complete","data":{…,"is_final":true}}`, `{"type":"error"}` |

Sources: [TTS Realtime](https://docs.gnani.ai/api/TTS/tts-websocket), [TTS SSE](https://docs.gnani.ai/api/TTS/tts-sse), [TTS REST](https://docs.gnani.ai/api/TTS/tts-inference).

- **Models:** `timbre-v2.5` (recommended), `timbre-v2.0` (deprecated, 4 voices), `vachana-vc-v1` (voice clone with `speaker_embedding`).
- **Request body:** `{"text","voice","model":"timbre-v2.5","language","speed"(0.85–1.15),"audio_config":{"sample_rate","num_channels":1,"sample_width":2,"encoding","container","bitrate"}}`.
- **Formats:** `sample_rate` 8000/16000/22050/24000/44100/48000. Containers `wav`, `raw` (headerless PCM; best for Pipecat), `mp3`, `ogg` (Opus, **delivered as one chunk at the end, so not streamable**), `mulaw`/`alaw` (forced to 8 kHz).
- **Languages:** `auto` (detects from script; "recommended for mixed content"), `hi-IN, en-IN, ta-IN, te-IN, kn-IN, ml-IN, mr-IN, pa-IN, bn-IN, gu-IN`, and **`hi-en` (Hinglish)**.
- **Voices:** 42 total ([catalog](https://docs.gnani.ai/api/TTS/available-voices)). Hindi: Nalini, Bhavna, Yashvi, Urmila, Jwala, Chitra, Ambuja, Deepak, Roopesh, Vikrant, Hemraj, Jalaj, Omkar. English: Kaveri, Trupti, Devika, Pranav, Shlok, Girish. **Hinglish: Poorvi** (the only one). Tamil 5, Telugu 5, and 2 each for kn/ml/mr/bn/gu/pa. Each voice has a preferred language, and the docs warn that a mismatch lowers quality.
- **Streaming model:** **one complete text per request**, and "send one synthesis request at a time" per socket. There is no token-by-token text input and no context id carrying prosody across sentences [inference: prosody resets per sentence]. Pipecat's default sentence aggregation fits this.
- **Text formatting:** the realtime page says to pass numbers, dates and currency as spoken words, but there is also a [normalization guide](https://docs.gnani.ai/api/TTS/tts-input-formating) describing automatic normalization. Prompt the LLM to write numbers out in words to be safe.
- **TTFB:** **not stated in the docs.** Marketing claims "First Byte Latency <250ms", "P95 242 ms" ([TTS page](https://www.gnani.ai/text-to-speech-api)), and "Sub-100ms time-to-first-audio" ([models page](https://www.gnani.ai/models)). These contradict each other, so plan for ~200–300 ms [inference].

## 5. LLM / agent / speech-to-speech

| Offering | Status | Usable for our demo? |
|---|---|---|
| **Gnani Evon v3.3** LLM ("302 ms first token", 30B, 128K) [marketing] | No API docs. The dashboard JS has a **beta "LLM" playground** with models `gnani-evon-v3` ("reasoning… Hindi, Tamil and Hinglish") and `gnani-evon-v2`, served by internal session-auth endpoints (`/api/v1/llm-playground/sessions/{id}/chat`), not by API key. | **No.** Bring your own LLM. |
| **Gnani Warp v2.0** speech-to-speech ("sub-200ms P95") [marketing] | No docs, no SDK, no Pipecat/LiveKit plugin | No. Sales-gated in practice [inference]. |
| **Agent Builder** (formerly Inya), REST at `https://api.inya.ai/platform`, header `x-api-key` | Hosted no-code telephony agents. Its LLM list includes Gnani "Pampa Go" / "Pampa Priority" plus OpenAI and Anthropic, and its ASR list includes `gnani_vachana_rest` and Microsoft. Separate keys and credits. | Only if you want a hosted phone bot instead of a Pipecat pipeline. Not covered by these trial credits [inference]. |

**The "60 Request of API" tile is not an LLM or agent quota.** It is the per-minute rate limit on the speech APIs (see §1).

## 6. Pipecat integration

### Status (verified)

- `pipecat-ai` v1.12.0 (2026-09-26) `src/pipecat/services/` has **no `gnani`**. Sarvam is built in.
- Pipecat's docs list Gnani STT and TTS as **Community**, installed with `uv add pipecat-gnani` ([pipecat docs repo](https://github.com/pipecat-ai/docs/blob/main/api-reference/server/services/stt/gnani.mdx)).
- Package: [`pipecat-gnani`](https://pypi.org/project/pipecat-gnani/) 0.5.12 (2026-08-17), repo [Gnani-AI-Mintlify/pipecat-gnani](https://github.com/Gnani-AI-Mintlify/pipecat-gnani). Gnani says it is "Tested with Pipecat v1.5.0". It depends on `gnani-vachana>=0.7.9` and `pipecat-ai>=0.0.50`, which is unpinned.
- Classes: `GnaniSTTService` (WebSocket), `GnaniHttpSTTService` (REST + local VAD), `GnaniTTSService` (WebSocket, `InterruptibleTTSService`), `GnaniSSETTSService`, `GnaniHttpTTSService`.
- Example: `examples/foundational/agent.py` (Gnani STT + Groq `llama-3.1-8b-instant` + Gnani TTS + Silero, WebRTC transport).
- For comparison, LiveKit's plugin `livekit-plugins-gnani` is in the official `livekit/agents` repo (1.8.3, 2026-09-23) and is better maintained.

### Known bugs in pipecat-gnani 0.5.12 (read the source and the open PRs)

1. **ImportError on pipecat-ai ≥ 1.8.** `stt.py` and `tts.py` import `_NotGiven` from `pipecat.services.settings`. In v1.12.0 that module only has `NotGiven` (`from pipecat.utils.types import NOT_GIVEN, NotGiven, is_given`); I confirmed this in the source. Fix: [PR #2](https://github.com/Gnani-AI-Mintlify/pipecat-gnani/pull/2), open since 2026-09-18.
2. **Barge-in doesn't stop TTS.** The service only implements `_connect_websocket`/`_disconnect_websocket`, so `InterruptibleTTSService`'s reconnect-on-interrupt does nothing. The PR author measured 17 audio frames still pushed after an interruption, and a dead socket is never replaced. Fix: [PR #3](https://github.com/Gnani-AI-Mintlify/pipecat-gnani/pull/3).
3. **STT leaks WebSockets** after `error` messages and failed handshakes. Fix: [PR #4](https://github.com/Gnani-AI-Mintlify/pipecat-gnani/pull/4).
4. **No 1024-byte re-framing.** `GnaniSTTService.run_stt` forwards each Pipecat audio chunk as-is (typically 10–20 ms, i.e. 320–640 bytes), but the API requires exactly 1024-byte frames. LiveKit's plugin re-chunks to 1024 bytes. Whether the server tolerates other sizes is untested [inference: Gnani's demo video suggests it works, but add a re-chunker anyway].
5. **VAD headers not exposed.** Settings cover only `language`, `sample_rate`, `format` and `itn_native_numerals`. You can't set `x-min-silence-ms` without patching `_connect`, and the SDK docs confirm the SDK doesn't expose VAD tuning either.
6. **TTS defaults to `timbre-v2.0` (deprecated, voice "Pranav").** Pass `model="timbre-v2.5"` and a v2.5 voice explicitly.
7. **`hi-en` is rejected client-side.** The SDK's `SUPPORTED_TTS_LANGUAGES` omits `hi-en`, so `_validate_timbre_options` raises `ValueError`. For the Hinglish voice Poorvi, use `language="auto"`.
8. TTS `speed` isn't passed. The TTS default `container="wav"` makes the plugin strip WAV headers per chunk; `container="raw"` is cleaner.
9. The STT 15-minute session cap is handled only by reconnect-on-send-failure, which is the leaky path from #3.

### Options

**A. Vendor and patch (recommended, ~1–2 h) [inference].** Copy `pipecat_gnani/` into the repo, or `pip install` from the PR #2+#3+#4 branches. Then:
- fix the import (`from pipecat.utils.types import NotGiven`)
- apply PR #3 and PR #4
- add a 1024-byte re-chunker in `run_stt`
- add VAD headers in `_connect` (`x-min-silence-ms: 300–400`, `x-vad-threshold: 0.5`)
- set `model="timbre-v2.5"`, `container="raw"`

Pinning `pipecat-ai==1.7.*` also avoids the ImportError, but it gives up 1.8–1.12 features (e.g. the `JevClassifier` mentioned in `laya.md`) and keeps bugs 2–5.

**B. Write your own (~0.5–1 day for both services including testing) [inference].** The protocol is small:
- **STT:** subclass `STTService` (or `WebsocketSTTService`).
  - In `start()`, open `wss://api.vachana.ai/stt/v3/stream` with the headers above and wait for `{"type":"connected"}`.
  - In `run_stt(audio)`, append to a buffer and send each 1024-byte slice. Pipecat already delivers audio in real time, so cadence is free.
  - In the receive task: on `processing`, optionally start TTFB metrics; on `transcript`, push `TranscriptionFrame(text, user_id, time_now_iso8601(), language)`; on `error`, log it.
  - Reconnect before the 15-minute cap. About 120–150 LOC.
- **TTS:** subclass `InterruptibleTTSService` (copy the shape from Neuphonic or another built-in).
  - In `run_tts(text)`, send one JSON request with `container:"raw"`, `sample_rate` = the pipeline output rate, and `model:"timbre-v2.5"`.
  - On `audio`, base64-decode, then push `TTSAudioRawFrame`.
  - On `complete`, push `TTSStoppedFrame`.
  - On interruption, close and reopen the socket.
  - About 120–150 LOC.

**C. Hybrid.** Use Gnani STT plus Sarvam TTS (built into Pipecat), or the reverse, if one side gives trouble.

## 7. Latency budget for a live demo [inference]

| Stage | Expected |
|---|---|
| User stops speaking → Gnani `processing` | `x-min-silence-ms` (500 default; set 300–400) |
| `processing` → `transcript` | ~200–320 ms (docs: P95 ~200 ms; examples show 318–320) |
| LLM TTFT (e.g. Groq 8B) | ~150–400 ms |
| TTS first audio (first sentence) | ~150–300 ms (no documented figure) |
| **Voice-to-voice** | **~0.9–1.5 s** tuned, ~1.2–1.8 s with defaults |

Barge-in comes from Pipecat's local Silero VAD, not Gnani's. It works once TTS bug #2 is fixed.

## 8. Rate limits, concurrency, gotchas

- **60 requests/minute** for STT REST, Batch and TTS; **20 concurrent STT WebSocket sessions**. These are verified from the public pricing endpoint. The 429 body is `{"type":"RATE_LIMIT_ERROR","message":"Rate limit exceeded. Please try again later."}` (OpenAPI in the docs). Raising limits requires a custom plan from sales.
- STT WebSocket **session cap: 15 minutes**.
- **No browser-direct STT.** Browser `WebSocket` can't set the headers, so proxy through the backend. That is the Pipecat server anyway.
- **Server VAD and local VAD both run.** Gnani segments on its own VAD, and Pipecat runs Silero/smart-turn. With final-only STT, the user aggregator waits for Gnani's transcript, so tune both [inference].
- **One language per STT connection.** Switching languages means reconnecting. Pipecat-gnani reconnects on `STTUpdateSettingsFrame(language=…)`.
- **Signup and access are self-serve**, not sales-gated: dashboard sign-up, a key from the API Keys page, Razorpay top-ups (minimum purchase applies). There is also a "Claim ₹1,00,000 free credits" corporate-email promo flow in the dashboard JS. I didn't check whether it is active.
- Third-party pages claim Gnani is enterprise-only with no free trial. That is out of date for the speech APIs.

## 9. Suggested demo config

```python
# pip install "pipecat-ai[silero,webrtc,groq]" gnani-vachana  + vendored/patched pipecat_gnani
stt = GnaniSTTService(api_key=KEY, sample_rate=16000,
        settings=GnaniSTTService.Settings(language=Language.HI_IN, format="transcribe"))
# patch _connect headers: x-min-silence-ms=350, x-vad-threshold=0.5 ; re-chunk to 1024 B
tts = GnaniTTSService(api_key=KEY, sample_rate=24000,   # pick one of 8/16/22.05/24/44.1/48k
        settings=GnaniTTSService.Settings(model="timbre-v2.5", voice="Nalini",
                                          language="hi-IN", container="raw"))
# Hinglish voice: voice="Poorvi", language="auto"   (not "hi-en": SDK validator rejects it)
```

## Sources

- Gnani docs index: https://docs.gnani.ai/llms.txt and full dump https://docs.gnani.ai/llms-full.txt
- API intro: https://docs.gnani.ai/api/introduction/introduction · Quick start: https://docs.gnani.ai/api/introduction/quick-start
- STT REST: https://docs.gnani.ai/api/STT/speech-to-text · STT Realtime: https://docs.gnani.ai/api/STT/stt-websocket
- TTS Realtime: https://docs.gnani.ai/api/TTS/tts-websocket · SSE: https://docs.gnani.ai/api/TTS/tts-sse · REST: https://docs.gnani.ai/api/TTS/tts-inference · Voices: https://docs.gnani.ai/api/TTS/available-voices
- Real-time compliance guide (latency figure): https://docs.gnani.ai/api/use-cases/real-time-compliance
- Python SDK: https://docs.gnani.ai/python-sdk/introduction · PyPI https://pypi.org/project/gnani-vachana/
- Pipecat plugin docs (Gnani): https://docs.gnani.ai/pipecat/introduction · PyPI https://pypi.org/project/pipecat-gnani/ · repo https://github.com/Gnani-AI-Mintlify/pipecat-gnani (PRs #2, #3, #4)
- Pipecat docs, Gnani STT (community): https://github.com/pipecat-ai/docs/blob/main/api-reference/server/services/stt/gnani.mdx · supported services: https://docs.pipecat.ai/api-reference/server/services/supported-services
- Pipecat source v1.12.0: https://github.com/pipecat-ai/pipecat/tree/v1.12.0/src/pipecat/services (no gnani; `settings.py` uses `NotGiven`)
- LiveKit plugin: https://docs.livekit.io/agents/models/stt/gnani/ · https://github.com/livekit/agents/tree/main/livekit-plugins/livekit-plugins-gnani
- Agent Builder Platform API: https://docs.gnani.ai/Platform/platform-introduction · LLM models: https://docs.gnani.ai/Platform/Get_LLM_Models
- Public pricing endpoint: https://paymentbck.vachana.ai/api/billing/payment/pricing-detail
- Dashboard bundle (pricing FAQ, `requests_per_minute`, LLM playground): https://voice-mfe.gnani.ai/remoteEntry.js → `assets/PricingPage-*.js`
- Marketing (treat as unverified): https://www.gnani.ai/models · https://www.gnani.ai/speech-to-text-api · https://www.gnani.ai/text-to-speech-api · https://huggingface.co/gnani-ai/gnani
- Legacy gRPC (obsolete): https://github.com/gnani-ai/API-service
