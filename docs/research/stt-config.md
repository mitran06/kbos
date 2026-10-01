# STT config for KB (measured 2026-10-02 ~02:15 IST, laptop on campus Wi-Fi + WARP)

Test: `scripts/stt_bench.py` streams the 9 Bulbul-rendered test utterances (3 English, 3 Hindi, 3 Hinglish;
`backend/tests/audio/`) to Sarvam realtime STT in **manual endpointing** (`speech_start` … `speech_end`, as the
STT gate does), `saaras:v4`, `stream_type=fast`, keyterms = machine codes + glossary.

| config | accuracy | median speech_end → final |
|---|---|---|
| **`hi-IN` + `codemix`** (chosen) | 9/9 usable; Hindi in Devanagari, English words in Latin, "4B"/"2A"/"KB" kept | 0.27 s |
| `auto` + `codemix` | same text, except one Hinglish line came back romanized | 0.28 s |
| `auto` + `transcribe` | Hindi lines fully Devanagari incl. "फोर बी", "वाइब्रेशन": machine codes and English terms lost | 0.27 s |

Decision: `STT_MODEL=saaras:v4`, `STT_LANGUAGE=hi-IN`, `STT_MODE=codemix`. Latency is a wash; codemix keeps
machine codes and English terms in Latin, which both the LLM and our language detection need.

Other findings that shaped the pipeline:
- **Endpointing:** Sarvam's server VAD (`endpointing=vad`, default 500 ms silence) cost 1.25–1.5 s of
  "transcription" + 0.5 s turn detection per turn (v2v 3.6–4.1 s). Manual endpointing driven by local Silero +
  Smart Turn brought v2v to 1.1–2.1 s.
- **Manual mode drops audio sent before `speech_start`.** Silero fires ~0.2 s into speech, so the first syllable
  ("Hi KB") was lost. The gate holds a 0.6 s pre-roll and sends it right after `speech_start`.
- **Keyterms** are accepted as a JSON array string in the `keyterms` query param. Don't add full ticket keys like
  "KB-0141": it biased "KB, 4B pe" into "KB-0141".
- **Sarvam drops an idle realtime socket after ~2 s without audio** ("no close frame"). The gate pings every 1 s
  while open and reconnects lazily if a socket still drops.
- **Sarvam's gateway intermittently answers HTTP 404** (LLM ~2/9 requests at one point, TTS WS connects too).
  LLM/TTS/STT connects are retried.
- Through the air (laptop speaker → phone mic) accuracy drops and room noise can produce short hallucinated
  transcripts ("तो दोस्तों"); real speech close to the phone is fine.
