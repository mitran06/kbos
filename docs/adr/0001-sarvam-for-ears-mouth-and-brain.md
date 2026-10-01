# Sarvam for speech-to-text, text-to-speech and the LLM; no Gnani, OpenRouter or Laya in the main path

KB's voice loop runs entirely on Sarvam: `saaras` realtime STT, `bulbul:v3` TTS and `sarvam-105b-conversations` for the LLM. All three have first-class Pipecat 1.12 services. Our measurements from Bengaluru (`docs/research/llm-benchmark.md`) put Sarvam's full tool turn at a median of 1.46 s, against 2.2 s or more for every OpenRouter model, because Sarvam is hosted in India and OpenRouter adds a US round trip. We hold 8 Sarvam keys (₹800 in credits), and a key pool rotates to the next key on 401/402/429.

## Considered options

- **Gnani for STT/TTS.** It has the most trial credits. Rejected: streaming STT has no auto language detection and no partial transcripts, the `pipecat-gnani` plugin fails to import on Pipecat ≥ 1.8 and ignores barge-in, and Cloudflare blocks requests without a browser User-Agent. We keep Gnani only as an env-switchable TTS fallback.
- **OpenRouter LLMs (gpt-oss-120b on Groq/Cerebras, etc.).** Accurate, but the turn takes 2.7 s or more and the key is capped at $1. Kept as an env-switchable fallback.
- **Laya (convaiinnovations/laya).** It's a zero-shot text classifier, not a speech model, and scores 0.3–0.46 on Indic intent without fine-tuning. Detecting unclear Checks is done by the LLM instead.
