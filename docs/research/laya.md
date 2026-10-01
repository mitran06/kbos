# Laya (convaiinnovations/laya): research notes for KBOS

Researched 2026-10-01. Sources are primary unless noted: the HF model card, the HF API file listing, config files, the GitHub repo `NandhaKishorM/laya` (README, BENCHMARKS.md, issues), the PyPI package, and Pipecat source on GitHub. Claims marked **[inference]** are mine, not from a source.

## TL;DR

- **"jev" means TypeSafe Jev.** It is not JEPA or Jarvis. Jev is a closed, hosted "System One" decision API from TypeSafe AI (released mid-Sept 2026, `POST https://api.typesafe.ai/v1/systemone`, $0.042 per 1M input tokens, no open weights). Laya is the Apache-2.0 open-weights alternative. Its HF repo includes `assets/laya_vs_jev.png`, and it ships a Jev-compatible HTTP server.
- **Laya is not a speech model.** It does not do STT, TTS, VAD or audio-based turn detection. It is a **text classifier/decision model**: you give it a text or JSON "state" plus typed questions (`choice`, `score`, `noul` = yes/no probability), and it returns calibrated probabilities from a single non-autoregressive forward pass. It never generates text.
- **Pipecat already supports Jev.** pipecat-ai 1.12.0 (2026-09-26) has `pipecat.classifiers.jev.JevClassifier` with a configurable `base_url`. Laya's `laya-serve` implements the same `/v1/systemone` wire format and ignores Jev's `model` field. So a self-hosted Laya can probably stand in for Jev in Pipecat by changing the base URL. **[inference, from reading both codebases; not tested end to end]**
- **It runs on our laptop.** The 322M multilingual checkpoint is about 1.3 GB in fp32 on the GPU [inference: 322M × 4 bytes]. Published single-question latency is about 33 ms on a T4 and 14 ms on an RTX 4070 Ti SUPER (2.8 ms with the TileLang fast path).
- **Zero-shot quality on Indian languages is weak.** On 20-way MASSIVE intent, accuracy is hi 0.46, bn 0.45, ta 0.31, kn 0.30, ml 0.28, te 0.22. Marathi, Gujarati and Punjabi have no published numbers. The authors say plainly that the capability comes from fine-tuning.

## 1. What Laya is

| Item | Fact | Source |
|---|---|---|
| Modality | Text in, typed probabilities out. Pipeline tag `text-classification`. No audio anywhere in the repo. | [HF API](https://huggingface.co/api/models/convaiinnovations/laya), [model card](https://huggingface.co/convaiinnovations/laya) |
| Task | "Multilingual, non-autoregressive System 1 decision model." Takes a state (text, email, ticket or JSON) and typed questions, and returns answers with probabilities in one forward pass. | [card](https://huggingface.co/convaiinnovations/laya/raw/main/README.md) |
| Question types | `choice` (pick one of N options with descriptions), `score` (ordinal levels), `noul` (yes/no probability) | card |
| Training | RLCD ("RL for Calibrated Decisions"): REINFORCE/GRPO-style updates with a strictly proper scoring-rule reward (log + spherical + RPS) | card; author's paper lineage [arXiv:2503.23303](https://arxiv.org/abs/2503.23303) (SalesRLAgent, Mar 2025) |
| License | Apache-2.0, weights and code | card front-matter, [GitHub](https://github.com/NandhaKishorM/laya) |
| Author | Nandakishor M / Convai Innovations. The org's earlier HF models are Hindi LLMs/embeddings, ECG MedGemma and others. None are speech models. | [HF org listing](https://huggingface.co/convaiinnovations), [dev.to write-up](https://dev.to/nandakishor_m_6cc0adfde9f/i-built-non-autoregressive-decision-models-a-year-ago-then-a-frontier-lab-called-it-a-18me) |

### Checkpoints (all in the one HF repo; the router downloads only what it uses)

| Checkpoint | Encoder | Params | Context | Weights on disk | Use |
|---|---|---|---|---|---|
| `laya` (repo root) | ModernBERT-large (28 layers, d=1024, vocab 50k) | 421M | 512 (head budget 192) | `model.safetensors` 843 MB (F16) | English only |
| `laya/multilingual` (also `convaiinnovations/laya-multilingual`) | mmBERT-base (`jhu-clsp/mmBERT-base`, 22 layers, d=768, vocab 256k) | 322M | 1024 by default, up to 8192 | 644 MB + 34 MB tokenizer | **anything non-English, including Indic** |
| `laya/typed-decisions` | ModernBERT-large | 421M | 1024 | 843 MB | fine-tuned for 4 business workflows |

Architecture: an encoder plus a decision head trained from scratch (2 transformer layers, an option-marker scorer, an act/escalate head). Each option is scored at its own `[MASK]` token and softmaxed over that question's options, so the label space is defined per request with no retraining. All questions in a call share one forward pass. Source: card "Architecture", `encoder/config.json`, `rl_agent_config.json`, `multilingual/rl_agent_config.json`.

Training budget from the configs: the multilingual checkpoint took 15,987 updates (4 epochs, about 4.97 h on one GPU). The English checkpoint took 7,313 updates (1 epoch, about 1.96 h, fine-tuned from an earlier checkpoint). These are small training runs.

### Languages

- The multilingual card's `language:` tag lists 51 codes, including **hi, bn, ta, te, kn, ml, ur**. It does **not** list mr, gu, pa or or. [laya-multilingual card](https://huggingface.co/convaiinnovations/laya-multilingual/raw/main/README.md)
- The router detects Devanagari, Bengali, Gurmukhi, Gujarati, Oriya, Tamil, Telugu, Kannada and Malayalam script ranges and sends them to the multilingual checkpoint. [`laya/lang.py`](https://github.com/NandhaKishorM/laya/blob/main/laya/lang.py). Hindi and Marathi routing regression tests were added in [PR #573](https://github.com/NandhaKishorM/laya/pull/573).
- **Gotcha: romanized Hindi (Hinglish).** `lang.py` has a stopword list for romanized *Bangla* only, not romanized Hindi. Latin-script Hinglish will likely be routed to the **English** checkpoint, which collapses on Indic languages while staying confident (Bengali 0.08 at about 0.94 confidence). **[inference from code]** Workaround: pass `model="multilingual"` or `lang_guess="hi"` explicitly. We know the language from STT anyway.

#### Measured Indic accuracy: MASSIVE intent, 20 options, random = 0.05, n ≈ 100 per language, refreshed numbers

Source: [BENCHMARKS.md](https://github.com/NandhaKishorM/laya/blob/main/BENCHMARKS.md), "All 51 MASSIVE languages".

| lang | `laya` (English ckpt) | `laya-multilingual` | multilingual ECE |
|---|---|---|---|
| hi | 0.100 | **0.460** | 0.368 |
| bn | 0.080 | **0.450** | 0.354 |
| ur | 0.070 | **0.420** | 0.336 |
| ta | 0.120 | **0.310** | 0.448 |
| kn | 0.110 | **0.300** | 0.388 |
| ml | 0.070 | **0.280** | 0.443 |
| te | 0.090 | **0.220** | 0.497 |
| en (reference) | **0.820** | 0.710 | 0.233 |
| mr / gu / pa / or | not measured | not measured | |

These are zero-shot results with 20 options, which is a hard setting. With 3 to 6 options the numbers would be higher **[inference]**, but nobody has published Indic results for few-option tasks.

## 2. How to run it

Install (from PyPI; latest on PyPI is 0.3.22, GitHub README describes 0.3.23):

```bash
uv venv --python 3.12          # README's own uv example; >=3.10 required
uv pip install laya --torch-backend=auto     # or: "laya[serve]" for the HTTP server, "laya[fast]" for TileLang kernels
```

PyPI `requires_dist`: `torch>=2.0.0`, `transformers>=4.48.0`, `safetensors>=0.4.0`, `huggingface_hub>=0.20.0`, `numpy>=1.20.0`. Extras: `serve` (fastapi, uvicorn), `fast` (tilelang>=0.1.14), `mcp`, `onnx`, `langchain`, `llamaindex`, `crewai`, `structured`. Source: [PyPI JSON](https://pypi.org/pypi/laya/json). The installation-details section says the dependency floor is set by "`huggingface_hub` 1.x, `transformers` 5.x and `torch` 2.14", and the configs were written by transformers 5.0.0.

In-process usage for Indic text (from the multilingual card):

```python
import laya
agent = laya.load("convaiinnovations/laya", subfolder="multilingual")   # ~647 MB download
result = agent.predict(
    {"body": "मुझसे इनवॉइस 4411 के लिए दो बार शुल्क लिया गया। कृपया आज ही धनवापसी करें।"},
    {"department": {"type": "choice", "instructions": "Which team should handle `body`?",
                    "criteria": {"billing": "invoices, payments, refunds",
                                 "technical": "bugs and outages", "sales": "pricing"}},
     "refund_requested": {"type": "noul", "instructions": "Does the sender ask for money back?"}},
)
result["answers"]["department"]["choice"], result["answers"]["department"]["probabilities"]
```

Router (auto-picks the checkpoint by script/language):

```python
from laya import Router
router = Router(preload=True, device="cuda")      # or Router(); max_loaded=2 by default
router.predict(state, questions, model="multilingual")   # force it for Hinglish/romanized text
```

Jev-compatible HTTP server:

```bash
uv pip install "laya[serve]"
LAYA_DEVICE=cuda LAYA_MODELS=multilingual LAYA_DEFAULT_MODEL=multilingual laya-serve   # 0.0.0.0:8000
curl -s localhost:8000/v1/systemone -H 'content-type: application/json' -d '{
  "state": {"body": "मेरा बिल दो बार कटा"},
  "questions": {"dept": {"type": "choice", "instructions": "which team?",
                "criteria": {"billing": "refunds", "tech": "bugs"}}}}'
```

Server env vars: `LAYA_HOST/PORT/DEVICE/PRELOAD/MODELS/THREADS/DEFAULT_MODEL/MAX_LOADED/API_KEY/MAX_CONCURRENT/MAX_TOKEN_BUDGET`. `POST /v1/systemone/batch` accepts up to 64 states. There is **no** `GET /v1/models` on main yet ([PR #667](https://github.com/NandhaKishorM/laya/pull/667) is still open). Source: [`laya/serve.py`](https://github.com/NandhaKishorM/laya/blob/main/laya/serve.py), README "Self-Hosting".

Gotchas listed in the README:
- If `laya.load()` hangs, set `USE_TF=0`. transformers probes for TensorFlow, and its abseil runtime can deadlock.
- The first CUDA call may JIT-compile a Triton shim with gcc and needs `Python.h`. A uv-managed Python ships headers, and gcc is present on this machine.
- `compile=True` takes about 46 s to warm up. Call `agent.warmup()` before traffic. The default (no compile) needs no warm-up beyond the first call.
- On CPU, pin `torch.set_num_interop_threads(1)` and set intra-op threads to roughly the physical core count. Default settings were 12x slower in one report.

### Streaming

Not applicable. The model is a one-shot classifier over a complete text with no token streaming. In a voice pipeline you call it on each final (or interim) transcript.

### Published latency

| Hardware | Checkpoint | 1 question | Notes | Source |
|---|---|---|---|---|
| Tesla T4 | multilingual | 32.8 ms | 10 q batched: 72.3 ms | card / BENCHMARKS |
| Tesla T4 | English | 39.5 ms | 10 q: 158.6 ms | card |
| RTX 4070 Ti SUPER, CUDA 13, torch 2.11 | multilingual | 14.1 ms stock / **2.8 ms fast path** | 72-token input, includes tokenization | BENCHMARKS "GPU fast path" |
| RTX 4070 Ti SUPER | English | 17.7 ms stock / 4.6 ms fast | | same |
| RTX 5060 Ti | (not stated) | ~10 ms per decision one at a time, ~1 ms batched | | README batch section |
| Intel i9-14900HX CPU, fp32 | multilingual | 50 ms at a 37-token state; 307 ms at 227 tokens | | [HF discussion #12](https://huggingface.co/convaiinnovations/laya/discussions/12) |
| AWS EPYC 4-core CPU, Python 3.14.4, torch 2.14 | multilingual | 193 ms | English ckpt: 580 ms | BENCHMARKS "Server CPU" |
| Apple M2 Ultra CPU (fine-tuned multilingual) | | 60 ms (ONNX int8: 39 ms) | | [es_phone_turns README](https://github.com/NandhaKishorM/laya/tree/main/research/benchmarks/es_phone_turns) |

Jev, for comparison, has been measured at 236–276 ms p50 by third parties. The card cites AbdelStark and nibzard. One HF user measured 1237 ms for Jev on their task.

## 3. Can it run on this machine?

Machine check (verified with `nvidia-smi`, `free` and `lscpu` on 2026-10-01): RTX 4060 Laptop, 8188 MiB, compute capability 8.9, driver 580.178 (CUDA 13.0). 15 GiB RAM with about 6.1 GiB available. i7-13620H, 10 cores / 16 threads. gcc and uv 0.12.9 are installed.

**Verdict: yes, comfortably.** Details:
- **VRAM.** The model is built in fp32 and moved to the device, with bf16 autocast used for compute on cc ≥ 8 (`laya/agent.py`). Multilingual is roughly 322M × 4 B ≈ **1.3 GB**, and English is about 1.7 GB, plus small activations **[inference]**. Loading only `multilingual` leaves more than 6 GB for a local STT model if we wanted one.
- **RAM.** One checkpoint load is transiently around 2–3 GB **[inference]**. The authors measured 9.3 GiB peak RSS with up to five checkpoints loaded at once on CPU. Set `LAYA_MODELS=multilingual` (or `max_loaded=1`) to stay well inside 6 GB.
- **Python/CUDA.** Laya is measured working on Python 3.14.4 + torch 2.14.0 (CPU), and torch 2.14.0+cu130 on CUDA (GB10). Pipecat needs Python ≥ 3.11. For safety, use a uv venv on 3.12 for both.
- **Expected latency on the 4060 Laptop: ~15–35 ms per call** for 1–3 questions on a short transcript (stock path), and under 10 ms with `laya[fast]` **[inference]**, interpolated from the T4 (33 ms) and 4070 Ti SUPER (14 ms) numbers. Small calls are bound by kernel-launch overhead, so the gap between laptop and desktop GPUs is narrow.
- **Download size.** About 680 MB for the multilingual weights and tokenizer, plus a CUDA torch wheel of a few GB.

## 4. Pipecat integration and KBOS role

### Pipecat already has a Jev classifier

pipecat-ai **1.12.0** (released 2026-09-26) added **Pipecat Classifiers** and a `jev` extra (`httpx[http2]`). Source: [release notes](https://github.com/pipecat-ai/pipecat/releases/tag/v1.12.0), [`src/pipecat/classifiers/jev/client.py`](https://github.com/pipecat-ai/pipecat/blob/main/src/pipecat/classifiers/jev/client.py), [`classifier.py`](https://github.com/pipecat-ai/pipecat/blob/main/src/pipecat/classifiers/jev/classifier.py), [`examples/features/features-classifiers.py`](https://github.com/pipecat-ai/pipecat/blob/main/examples/features/features-classifiers.py).

- Classifiers are plain objects, not pipeline processors: "It does not sit in a pipeline and no frames flow into it." You call `await classifier.ask(state, {name: YesNoQuestion|ChoiceQuestion|ScoreQuestion})`.
- Consumers inside Pipecat: `VoicemailDetector(classifier=...)`, `UIWorker(classifier=...)`, and the eval `EvalJudge`. The release notes demo semantic **turn completion** with Jev: `ChoiceQuestion("is the user's turn over?", {"complete", "short", "long"})`.
- `JevClient(api_key=..., base_url=DEFAULT_BASE_URL="https://api.typesafe.ai", model="jev-1.13.0")` posts `{"model", "state", "questions"}` to `/v1/systemone`.

### Pointing it at local Laya [inference from reading both codebases; untested]

```python
from pipecat.classifiers.jev.classifier import JevClassifier
laya = JevClassifier(api_key="local", base_url="http://127.0.0.1:8000")  # laya-serve
```

Compatibility notes:
- Laya's `_resolve_model` maps an unknown `model` like `"jev-1.13.0"` to None, which means auto-route. To force multilingual, set `LAYA_DEFAULT_MODEL=multilingual` or `LAYA_MODELS=multilingual`.
- With `LAYA_API_KEY` unset, the server accepts any `Authorization` header (`_authorized` returns True).
- `JevClient.connect()` calls `GET /v1/models`, which laya-serve doesn't implement yet. This returns 404, and `JevClassifier.setup` only logs a warning. `ask()` still works.
- Response shape matches what `_from_jev` reads: `choice`, `probabilities` (score keyed `"0","1",…`), `confidence`, `noul`, `usage`.
- **`confidence` semantics differ.** Laya reports 1 − normalised entropy, while Jev uses `(n·p_max−1)/(n−1)`. Thresholds don't transfer between them. Gate on the probabilities or refit thresholds.
- **`YesNoQuestion` with yes/no descriptions becomes `criteria: {"true":…, "false":…}`.** Laya has a documented bias where true/false label words can override the state ([#156](https://github.com/NandhaKishorM/laya/issues/156)). Prefer `ChoiceQuestion` with neutral keys (`A`/`B`) and descriptive text.
- laya-serve serializes inference behind an asyncio lock and a thread pool. That is fine for one call at a time.

Alternative: skip HTTP entirely. Write a ~40-line custom `BaseClassifier` subclass (implement `_ask`) or a `FrameProcessor` that runs `router.predict` via `asyncio.to_thread` on each `TranscriptionFrame`. That saves the HTTP hop (about 1 ms on loopback) and avoids the confidence and noul mapping issues.

### Where it fits in an Indian-language voice pipeline

| Pipeline stage | Can Laya do it? | Notes |
|---|---|---|
| STT (speech to text) | **No** | Keep Sarvam (Pipecat ships `SarvamSTTService`/`SarvamTTSService`/Sarvam LLM under `pipecat-ai[sarvam]`, `sarvamai==0.1.28`) or Gnani. Pipecat source has no Gnani service (GitHub code search for "gnani" in pipecat-ai/pipecat returned nothing), so Gnani needs a custom service. |
| TTS | **No** | Sarvam Bulbul / other. |
| VAD / acoustic end-of-turn | **No** | Silero VAD + Pipecat smart-turn (audio). |
| Semantic turn completion (text) | Possible, unvalidated | Pipecat's own Jev example does this. Laya has no published turn-completion numbers, and nothing at all for Indic. Treat as an experiment layered on smart-turn, not a replacement. |
| **Per-turn intent / routing** (which KB, which department, transfer, hang up, escalate) | **Best fit** | Runs in about 15–35 ms locally against about 400 ms for an LLM call. Zero-shot Indic accuracy is weak, so fine-tune or keep option counts small (see §5). |
| Guardrails (prompt injection/jailbreak on transcript) | Moderate | Held-out jailbreak detection 0.70–0.76 (English). |
| Sentiment / frustration / churn / escalate-to-human flags | Possible | `score` is the weakest primitive. Multilingual has position bias on `score` ([#131](https://github.com/NandhaKishorM/laya/issues/131)). |
| Voicemail detection (outbound) | Possible via `VoicemailDetector(classifier=...)` | Unvalidated. |

**Compared with Sarvam and Gnani [inference]:** these are not competitors. Sarvam and Gnani provide speech I/O (STT/TTS) and Indic LLMs. Laya would be a cheap, local, sub-50 ms text decision layer between STT and the LLM. Its real competitors for that slot are (a) the LLM doing routing via tool calls (simpler, more accurate zero-shot, about 300–1000 ms per turn) and (b) hosted Jev (better zero-shot, about 250 ms+, costs money, closed).

## 5. Quality caveats, known issues, maturity

### Quality, in the authors' own words (card "Honest Limits", BENCHMARKS "Limits, stated plainly")
- "Laya is a fast base to specialise, not a zero-shot decision engine." The base checkpoints sit **below majority-class** on the typed-decisions benchmark (0.362/0.342 against a 0.461 majority baseline). The 0.766 headline belongs to a checkpoint fine-tuned on that benchmark's own training split.
- Both checkpoints ship **over-confident**. The multilingual checkpoint ships with no fitted temperatures (`[1.0,1.0,1.0]`). Refit per (question type, option count) on your own data (ECE 0.314 → 0.106).
- Keep `choice` under about 20 options. Banking77 (77 labels) scores 0.425 against Jev's 0.870.
- Held-out moderation is 0.530 (barely above chance).
- `action.act_probability` is always 1.0 and useless ([#185](https://github.com/NandhaKishorM/laya/issues/185), open).

### Directly relevant to voice agents
- **Spanish phone-turn benchmark** ([PR #784](https://github.com/NandhaKishorM/laya/pull/784), [README](https://github.com/NandhaKishorM/laya/tree/main/research/benchmarks/es_phone_turns)): this is a voice-agent "transfer / hang up / keep talking" 6–7-way choice. Zero-shot `laya-multilingual` scored **0.396** with 124 wrong actions out of 217. After fine-tuning it scored **0.912**, level with qwen2.5-7b tool calling (0.908) at 60 ms CPU against about 405 ms GPU time-to-first-token. Zero-shot, **English option descriptions beat Spanish ones by 20–30 points** on Spanish sentences. Negation fails zero-shot: "No me pase con ventas…" was routed to `ventas` at confidence 1.00. INT8 ONNX flipped 24 of 221 decisions.
- **Short voice commands in Chinese** ([#218](https://github.com/NandhaKishorM/laya/issues/218), [HF discussion #7](https://huggingface.co/convaiinnovations/laya/discussions/7)): Laya scored 10/20, against 20/20 for Jev and 19/20 for a regex. Adding criteria or context made it *worse*.
- Independent head-to-heads: Laya trails Jev, mostly on multi-class questions. [HF #6](https://huggingface.co/convaiinnovations/laya/discussions/6): 6-way intent 0.725 for Laya against 0.975 for Jev. [HF #20](https://huggingface.co/convaiinnovations/laya/discussions/20): sealed 1,190 cases, laya 0.686 against Jev 0.907. Both used the English checkpoint.
- Community advice ([HF #7](https://huggingface.co/convaiinnovations/laya/discussions/7)): it behaves more like a similarity matcher than a reasoner. "Give it the relation in words, not the raw fields."

### Maturity
- HF repo created 2026-09-18, last modified 2026-09-24. 4,769 likes, trending score 1250, about 60 Spaces using it, 24 HF discussions. HF reports 0 downloads, almost certainly because there is no root `config.json` for HF's counter **[inference]**. PyPI shows about 149k downloads in the last week ([pypistats](https://pypistats.org/api/packages/laya/recent)).
- GitHub: about 29.7k stars, 2.6k forks, 93 open issues, pushed 2026-10-01. Very active (0.3.23 merged "64 PRs from 21 contributors").
- It is two weeks old, viral, and changing daily (the package went from 0.2 to 0.3.23 in 13 days). The authors have already had to correct benchmark tables once (the multilingual sweep didn't reproduce: [#208](https://github.com/NandhaKishorM/laya/issues/208)). Pin a version and a weights revision (`55cf4c4…`).

## 6. Verdict for KBOS

- **Role:** an optional local **text decision layer** on STT transcripts, for intent/KB routing, escalate/transfer flags, guardrails and maybe voicemail detection. It does **not** replace Sarvam/Gnani STT/TTS or VAD/smart-turn.
- **Latency cost:** about 15–35 ms per turn on the 4060 Laptop **[inference]**, about 1.3 GB VRAM, no per-token cost.
- **Effort:** about 30 min to install and serve. About 1–2 h to wire into Pipecat via `JevClassifier(base_url=...)` or a small custom classifier. Accuracy is the real cost. Zero-shot Indic routing is unreliable (hi 0.46, ta 0.31, te 0.22 at 20-way; Spanish phone turns 0.40), so usable quality likely needs a few hundred labelled utterances plus a fine-tune (Kaggle 2×T4 notebook, hours) and a temperature refit. For a hackathon, the cheaper path is to let the LLM route via tool calls. Add Laya only if LLM routing latency becomes the bottleneck, and then use few options, English criteria text, `model="multilingual"`, and a confidence fallback to the LLM.
