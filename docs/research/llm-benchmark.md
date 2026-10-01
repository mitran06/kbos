# LLM benchmark for KB's voice loop (measured 2026-10-02, from the KBOS laptop in Bengaluru)

What I measured is one realistic KB turn, done the way Pipecat does it. The model gets the KB system prompt and 5 ticket tools and returns a **tool call**. The tool result goes back, and the model streams the **spoken reply**.

- "turn" = time until the tool call is complete + time to the first spoken token of the reply. This is what the worker waits for after STT finalizes. Add about 0.3 s for STT finalization and about 0.3 s for TTS first byte to get voice-to-voice.
- There were 3 cases: a Hinglish ticket filing in Latin script, a Hindi ticket filing in Devanagari (what Sarvam STT emits for Hindi), and the English query "what's open today?". Each ran twice, so 6 turns per target.
- The script is `docs/research/llm_bench.py` (`python3 docs/research/llm_bench.py 2`). The run cost $0.03 of OpenRouter credit.

| target | first tool token (median) | first reply token (median) | **turn median** | worst turn | right tool | English tool args | reply language right |
|---|---|---|---|---|---|---|---|
| **sarvam-105b-conversations** (Sarvam API, India) | 0.66 s | 0.72 s | **1.46 s** | 2.31 s | 6/6 | 6/6 | 5/6 |
| llama-3.1-8b @ Groq | 0.99 | 0.97 | 2.20 | 3.00 | 6/6 | 4/6 | 6/6 (weak replies) |
| llama-3.3-70b @ Groq | 1.08 | 0.92 | 2.36 | 2.92 | 5/6 | 4/6 | 3/6, 1 Groq `failed_generation` |
| gpt-oss-20b @ Groq | 1.38 | 1.29 | 2.67 | 4.57 | 6/6 | 6/6 | 3/6 |
| **gpt-oss-120b @ Groq** | 1.43 | 1.13 | 2.71 | 3.89 | 6/6 | 6/6 | 3/6 |
| gpt-oss-120b @ Cerebras | 1.29 | 1.33 | 2.86 | 3.45 | 6/6 | 6/6 | 3/6 |
| nemotron-3.5-lightning @ DeepInfra | 1.14 | 1.24 | 2.89 | 3.39 | 6/6 | 6/6 | 3/6 |
| qwen3.7-flash @ Alibaba | 1.34 | 1.04 | 2.86 | 2.91 | 3/6 | 3/6 | 5/6 |
| gemma-4-26b @ Cloudflare | 1.58 | 1.27 | 3.22 | 5.11 | 6/6 | 6/6 | 4/6 |
| gpt-4o-mini @ OpenAI | 1.60 | 1.36 | 3.47 | 4.08 | 6/6 | 6/6 | 4/6 |
| gemini-2.5-flash-lite @ AI Studio | 1.94 | 1.68 | 3.82 | 7.48 | 6/6 | 6/6 | 4/6 |
| gpt-4.1-nano @ OpenAI | 1.85 | 1.62 | 4.14 | 5.73 | 6/6 | 6/6 | 4/6 |
| gemini-3.1-flash-lite @ Google | 2.04 | 2.04 | 4.40 | 6.12 | 6/6 | 6/6 | 4/6 |
| gpt-oss-120b @ SambaNova | 2.50 | 1.65 | 4.43 | 6.05 | 6/6 | 6/6 | 4/6 |
| mercury-2.5 @ Inception | 5.82 | — | 7.85 | — | 1/6 | 0/6 | broken tool calls |
| free models (nemotron-3.5-lightning:free, gemma-4-31b:free, inkling-small:free) | — | — | 28 s+ / 429 / 403 | — | — | — | unusable live |

## Notes

- **OpenRouter's own numbers are measured server-side and don't hold from India.** The discover page and provider tables list gpt-oss-120b at 0.19–0.24 s latency on Crusoe, Groq and Cerebras. From this laptop every OpenRouter call pays about 0.5–0.8 s more for the round trip to the US plus reasoning tokens. Sarvam is hosted in India, which is why it wins end to end.
- **Reply language.** Sarvam and gpt-oss both answered the English "what's open today?" in Hinglish. Fix: pass the STT-detected language (`en-IN` / `hi-IN`) as a hint on every user turn and say "reply in the detected language".
- **gpt-oss replied in English to Devanagari Hindi.** The same per-turn language hint fixes this.
- **llama-3.1-8b** put raw Hinglish into the `symptom` field and invented dates. Rejected.
- **Decision:** primary is `sarvam-105b-conversations`. The fallback, selectable by env, is `openai/gpt-oss-120b` via OpenRouter pinned to Groq, then Cerebras. The OpenRouter key has a $1 cap, so the fallback is for emergencies only.
- **Latency design that follows from this:** a tool round trip costs about 0.7 s extra. KB should therefore know the open tickets from its context, refreshed each turn, and the UI tools (show tickets, update draft) should be fire-and-forget. That way most turns need only one LLM call.
