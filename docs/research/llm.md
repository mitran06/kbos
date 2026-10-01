# LLM choice for the Indic voice agent (Groq / OpenRouter / Pipecat 1.12.0)

Researched 2026-10-01. Pipeline: Sarvam STT -> LLM (streaming + tool calls) -> TTS, on `pipecat-ai==1.12.0` (released to PyPI 2026-09-26).

Labels: **[V]** means verified in a primary source (link given). **[I]** means my inference or estimate, not measured.

---

## TL;DR

- **Primary: Groq `openai/gpt-oss-120b`** with `reasoning_effort="low"`, `temperature` around 0.2-0.3, through `GroqLLMService`. It is Groq's flagship production model, it supports tool calling and JSON-schema mode, and runs at about 500 tok/s. Expected TTFT is about 0.4-0.8 s for a 2-4k-token voice prompt **[I]**.
- **Fallback: Groq `openai/gpt-oss-20b`** (same API and settings, about 1000 tok/s, weaker on Indic languages and tools) **[V speed, I quality]**. Alternatively, `qwen/qwen3.8-27b` (preview) with `reasoning_effort="none"`.
- **The Groq free tier won't hold up in a live demo.** Free limits for gpt-oss-120b are 30 RPM and **8K TPM** **[V]**. A single voice turn with system prompt, tool schemas and history is about 2-4k input tokens, and a tool call doubles the requests, so 8K TPM runs out after about 2-3 turns per minute **[I]**. Upgrade to Groq Developer (pay-as-you-go: 1K RPM, 250K TPM) **[V]**. It costs pennies at $0.15/M input and $0.60/M output **[V]**.
- **Gone from Groq now (don't use):** Llama 3.1 8B and 3.3 70B (shut down 08/16/26 on free and dev tiers), Llama 4 Maverick (03/09/26), Llama 4 Scout and Qwen3-32B (07/17/26), Kimi K2 0905 (04/15/26), Qwen3.6-27B (09/14/26), and Compound (09/21/26) **[V]**.
- **OpenRouter free models aren't good enough for a live demo.** Limits are 20 RPM and **50 requests/day** (1,000/day only after buying 10 or more credits) **[V]**, and OpenRouter itself says free models "are usually not suitable for production use" **[V]**.

---

## 1. Groq

### 1.1 Current lineup (as of 2026-10-01)

Source: https://console.groq.com/docs/models and https://console.groq.com/docs/deprecations

| Model ID | Status | Context | Max output | Speed (Groq-stated) | Tool use | Parallel tools | Reasoning control |
|---|---|---|---|---|---|---|---|
| `openai/gpt-oss-120b` | Production | 131,072 | 65,536 | ~500 t/s | Yes | **No** | `reasoning_effort`: low / medium / high |
| `openai/gpt-oss-20b` | Production | 131,072 | 65,536 | ~1000 t/s | Yes | **No** | low / medium / high |
| `qwen/qwen3.8-27b` | **Preview** | 131,072 | 16,384 | ~450 t/s | Yes | Yes | none / default / low / medium / high |
| `minimaxai/minimax-m2.7` | Preview | 196,608 | 131,072 | ~260 t/s | Yes | Yes | n/a |
| `openai/gpt-oss-safeguard-20b` | Preview (moderation) | 131,072 | 65,536 | ~1000 t/s | Yes | No | - |
| `llama-3.3-70b-versatile`, `llama-3.1-8b-instant` | Still listed on the models page, but **shut down 08/16/26 for free and developer tiers** | - | - | - | - | - | - |

Notes:
- **[V]** The models page still lists the two Llama 3.x models under "Production". The deprecations page gives their shutdown as `08/16/26` (replacements: `openai/gpt-oss-20b` and `openai/gpt-oss-120b`), and the rate-limits page no longer lists them. Treat them as unavailable. https://console.groq.com/docs/deprecations
- **[V]** Other recent deprecations: Llama 4 Maverick (shut down 03/09/26, replacement gpt-oss-120b); Llama 4 Scout and Qwen3-32B (07/17/26); Kimi K2 Instruct 0905 (04/15/26, replacement gpt-oss-120b); `qwen/qwen3.6-27b` (09/14/26, replacement `qwen/qwen3.8-27b`); `groq/compound` and `compound-mini` (09/21/26).
- **[V]** Tool use: per https://console.groq.com/docs/tool-use, "all models hosted on Groq support tool use". **The gpt-oss models do not support parallel tool calls on Groq**; Qwen 3.8, MiniMax and the Llamas did.
- **[V]** If the model emits a malformed tool call, Groq returns an **HTTP 400** with a `failed_generation` field (for example "Tool call arguments are not valid JSON"). The docs recommend a retry strategy. Groq's own examples use `temperature: 0` and `tool_choice: "auto"` for tool calling. https://console.groq.com/docs/tool-use
- **[V]** gpt-oss-120b pricing: $0.15/M input, $0.075/M cached input, $0.60/M output. Supports JSON Object and JSON Schema modes. OpenAI claims "81+ languages", with an MMMLU average of 81.3. https://console.groq.com/docs/model/openai/gpt-oss-120b
- **[V]** Qwen 3.8 27B has a thinking mode and an instruct mode. `reasoning_effort="none"` selects instruct mode. Recommended instruct sampling: temperature 0.7, top_p 0.8, presence_penalty 1.5. It accepts text and images. https://console.groq.com/docs/model/qwen/qwen3.8-27b
- **[V]** groq.com/pricing did not render model pricing when fetched, so prices above come from the per-model docs page.

### 1.2 Free-tier vs Developer rate limits

Source: https://console.groq.com/docs/rate-limits (values read from the page's embedded table data)

| Model | Free RPM | Free RPD | Free TPM | Free TPD | Dev RPM | Dev RPD | Dev TPM |
|---|---|---|---|---|---|---|---|
| `openai/gpt-oss-120b` | 30 | 1K | **8K** | 200K | 1K | 500K | 250K |
| `openai/gpt-oss-20b` | 30 | 1K | **8K** | 200K | 1K | 500K | 250K |
| `qwen/qwen3.8-27b` | 30 | 1K | **8K** | 200K | 1K | 500K | 250K |
| `minimaxai/minimax-m2.7` | (not in the free table) | | | | | | |

**[I]** Budget for a voice agent: system prompt (about 800-1500 tokens covering multilingual rules, persona and English-args rule) plus about 6 tool schemas (about 800-1200 tokens) plus growing history comes to roughly 2-4k input tokens per request. A turn that triggers a tool makes 2 requests: one for the tool call and one for the spoken answer. At 8K TPM that is about 1-3 turns per minute, so expect 429s mid-demo. **Use the Developer plan for the demo.** Prompt caching (cached input is half price on gpt-oss-120b) also helps cost, but Groq's docs don't confirm it lowers TPM usage.

### 1.3 Reasoning controls for low latency

Source: https://console.groq.com/docs/reasoning

- **[V]** gpt-oss-20b and gpt-oss-120b take `reasoning_effort` = `low` | `medium` | `high`. They do **not** support `reasoning_format`; use `include_reasoning` (a bool) instead. On Groq, gpt-oss reasoning goes to a separate `reasoning` field, not into `content`.
- **[V]** Qwen 3.8 27B takes `none` | `default` | `low` | `medium` | `high`, plus `reasoning_format` (`parsed` / `raw` / `hidden`). `include_reasoning` and `reasoning_format` can't be used together.
- **[V]** Pipecat's `GroqLLMSettings` docstring (v1.12.0) warns that without `reasoning_effort="none"`, Qwen reasoning is "stream[ed] inline in `<think>` tags" into the spoken response. **Always set `none` for Qwen.**
- **[V]** Pipecat's OpenAI base streaming loop only pushes `delta.content` and `delta.tool_calls` (`services/openai/base_llm.py` lines ~552-595), so gpt-oss `delta.reasoning` text is never spoken. Reasoning tokens still delay the first content token, though, which is why `low` matters.

### 1.4 TTFT / speed evidence

- **[V, with caveats]** Artificial Analysis provider benchmark for gpt-oss-120b uses a 10,000-input-token workload with the model's default/high reasoning, median over 72 h. Groq: 471 tok/s, TTFT 4.95 s, time-to-first-answer-token 4.24 s. Cerebras: 1,781 tok/s, TTFT 1.56 s. SambaNova: 709 tok/s, 3.94 s. https://artificialanalysis.ai/models/gpt-oss-120b/providers
  - That setup is far heavier than a voice turn: 10k input tokens and high reasoning. **[I]** With 2-4k input tokens and `reasoning_effort="low"` (typically tens of reasoning tokens, about 0.1 s at 500 t/s), the first spoken token on Groq should land at roughly **0.4-0.8 s**. Measure it with `PipelineParams(enable_metrics=True)`; Pipecat logs TTFB per LLM call.
- **[V, low confidence]** The same site's gpt-oss-20b page showed Groq at about 943 tok/s and TTFT about 0.8 s, but the fetched summary was partly garbled. Re-check before quoting it.
- **[I]** Cerebras is the fastest gpt-oss-120b host on that benchmark and is reachable through OpenRouter (see section 2.3). That makes it a reasonable latency fallback if Groq misbehaves on demo day.

### 1.5 Which Groq model for Indic and tool calling

- **[V]** OpenAI's gpt-oss model card scores **82.2 on Hindi MMMLU at high reasoning**, but MMMLU's 14 languages include **only Hindi and Bengali among Indic languages**. Tamil, Telugu and Kannada aren't reported. https://arxiv.org/pdf/2508.10925
- **[I]** Ranking for this use case on Groq today:
  1. `openai/gpt-oss-120b`. It's the strongest model left on Groq, Groq itself names it as the replacement for Maverick, Kimi K2 and Llama 70B, it's in production, and it handles reliable JSON args well. It's the best bet for Hinglish, Tamil, Kannada and Telugu understanding plus English tool arguments. One limitation: no parallel tool calls, which is fine because `create_ticket` and `update_ticket` are sequential anyway.
  2. `qwen/qwen3.8-27b` with `reasoning_effort="none"`. It's quick in instruct mode and supports parallel tools, but it is **preview-only** (its predecessor was deprecated two weeks ago), max output is 16K, and there's no published Indic data.
  3. `openai/gpt-oss-20b`. It's the fastest option but has less world knowledge, and small models degrade first on Tamil, Telugu and Kannada generation.
- **[I]** Two prompt-level guards help with English tool arguments: (a) tool and parameter descriptions that say "always write values in English; translate or transliterate the user's words", and (b) `enum`s for status and priority fields.

---

## 2. OpenRouter

### 2.1 Free-tier limits

Sources: https://openrouter.ai/docs/api/reference/limits and https://openrouter.ai/docs/faq

| Credits purchased | Free-model RPM | Free-model RPD |
|---|---|---|
| < 10 | 20 | **50** |
| >= 10 | 20 | 1,000 |

- **[V]** A negative balance causes 402 errors even on free models. Cloudflare DDoS protection blocks traffic that "dramatically exceed[s] reasonable usage". Different models have different limits.
- **[V]** The FAQ says free models "are usually not suitable for production use."
- **[I]** For a live demo, 50 RPD covers only about 25 tool-using turns in a whole day of rehearsal plus demo. Each free model also typically has a **single upstream provider** (see below), so one provider's 429 or outage takes you down. **Not reliable enough as the primary.** As an emergency fallback after buying $10 of credits it's acceptable.

### 2.2 Free models with tool calling (from the live `/api/v1/models` and `/endpoints` API, 2026-10-01)

| Model ID | Context | Sole free provider | 1-day uptime | Notes |
|---|---|---|---|---|
| `google/gemma-4-31b-it:free` | 262K | Google AI Studio | 99.66% | Gemma models are broadly multilingual **[I]**; non-reasoning, so likely low TTFT **[I]** |
| `qwen/qwen3.8-27b:free` | 262K | ModelRun (fp4) | 97.4% | Same model as the Groq preview, but on a slower, quantized host **[I]** |
| `nvidia/nemotron-3-super-120b-a12b:free` | 262K | Nvidia | 98.2% | Reasoning model; check the latency **[I]** |

Others with `tools` support: `google/gemma-4-26b-a4b-it:free`, `nvidia/nemotron-3-ultra-550b-a55b:free`, `nvidia/nemotron-3.5-lightning:free`, `thinkingmachines/inkling(-small):free`, `poolside/laguna-*`, and more. There is **no `:free` variant of gpt-oss-120b or gpt-oss-20b** right now. **[V]** All fetched from https://openrouter.ai/api/v1/models?supported_parameters=tools

### 2.3 Paid OpenRouter fallback (inexpensive)

**[V]** OpenRouter's `openai/gpt-oss-120b` endpoints include Groq ($0.15/$0.60, 99.32% 1-day uptime), Cerebras ($0.35/$0.75, 99.89%), SambaNova, DeepInfra and Together. All support tools. **[I]** Pinning the provider to Cerebras or Groq gives a second network path to the same model, so prompts don't need to change.

---

## 3. Pipecat 1.12.0 integration

All verified against the 1.12.0 wheel from PyPI, which is byte-identical to tag `v1.12.0` on GitHub: https://github.com/pipecat-ai/pipecat/tree/v1.12.0/src/pipecat/services/groq/llm.py and `.../services/openrouter/llm.py`.

### 3.1 Services

```python
# uv add "pipecat-ai[groq]"        /  "pipecat-ai[openrouter]"
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.openrouter.llm import OpenRouterLLMService

llm = GroqLLMService(
    api_key=os.environ["GROQ_API_KEY"],
    # base_url defaults to "https://api.groq.com/openai/v1"
    settings=GroqLLMService.Settings(
        model="openai/gpt-oss-120b",        # this is also the default
        system_instruction=SYSTEM_PROMPT,
        temperature=0.2,
        max_completion_tokens=400,          # voice replies are short
        reasoning_effort="low",             # "none" for qwen/qwen3.8-27b
    ),
    # LLMService kwargs (pass-through): run_in_parallel=True, function_call_timeout_secs=..., etc.
)

fallback = OpenRouterLLMService(
    api_key=os.environ["OPENROUTER_API_KEY"],   # base_url "https://openrouter.ai/api/v1"
    settings=OpenRouterLLMService.Settings(
        model="openai/gpt-oss-120b",            # default is "openai/gpt-4.1"
        temperature=0.2,
        # extra=... is merged into the kwargs of client.chat.completions.create(**params);
        # wrap non-OpenAI fields in extra_body, e.g.
        # extra={"extra_body": {"provider": {"order": ["cerebras", "groq"]}}},
    ),
)
```

- **[V]** In 1.x the `settings=<Service>.Settings(...)` pattern is canonical. The `model=` constructor arg is deprecated since 0.0.105 and "will be removed in 2.0.0".
- **[V]** `GroqLLMSettings` adds only `reasoning_effort: Literal["none","default","low","medium","high"] | None`. It's sent only when set and not None. Inherited fields: `model`, `system_instruction`, `temperature`, `top_p`, `max_tokens`, `max_completion_tokens`, `frequency_penalty`, `presence_penalty`, `seed`, `extra` (dict merged into the request).
- **[V]** `OpenRouterLLMService` has `supports_developer_role = False`, so developer messages become user messages. It also rewrites duplicate system messages for Gemini models only.
- **[I]** OpenRouter's `provider` field isn't an OpenAI SDK kwarg, so it has to go under `extra_body`. The SDK otherwise raises `TypeError` on unknown kwargs.

### 3.2 Function calling (1.x universal context)

```python
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair, LLMUserAggregatorParams,
)
from pipecat.services.llm_service import FunctionCallParams
from pipecat.frames.frames import TTSSpeakFrame

async def create_ticket(params: FunctionCallParams):
    args = params.arguments            # Mapping[str, Any]
    ticket = await db.create(**args)   # params.app_resources is also available
    await params.result_callback({"ticket_id": ticket.id, "status": "open"})

create_ticket_schema = FunctionSchema(
    name="create_ticket",
    description="Create a support ticket. All string values MUST be in English.",
    properties={
        "title": {"type": "string", "description": "Short English summary"},
        "priority": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    required=["title", "priority"],
    handler=create_ticket,             # auto-registered when the context advertises the tool
)
tools = ToolsSchema(standard_tools=[create_ticket_schema, ...])

context = LLMContext(tools=tools)      # LLMContext(messages=None, tools=..., tool_choice=...)
user_agg, assistant_agg = LLMContextAggregatorPair(
    context, user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
)

# Alternative to handler=: manual registration
llm.register_function("create_ticket", create_ticket,
                      cancel_on_interruption=True, timeout_secs=10)

@llm.event_handler("on_function_calls_started")
async def _(service, function_calls):
    await tts.queue_frame(TTSSpeakFrame("Ek second, check kar raha hoon."))
```

- **[V]** Signatures (1.12.0): `register_function(function_name: str | None, handler, *, cancel_on_interruption=None, timeout_secs=None, cancellable_by_llm=None)`. Passing `None` as the name gives a catch-all handler. `FunctionSchema(name, description, properties, required, handler=None)`. `ToolsSchema(standard_tools, custom_tools=None)`. `LLMContextAggregatorPair(context, *, user_params=None, assistant_params=None, add_tool_change_messages=None, realtime_service_mode=None)`.
- **[V]** You can also pass plain "direct functions" to `LLMContext(tools=[fn, ...])`. Each takes `(params: FunctionCallParams, arg1: str, ...)` with a Google-style docstring, and options come from `@tool_options(cancel_on_interruption=..., timeout_secs=...)` (`pipecat.adapters.schemas.direct_function`). This is the pattern in `examples/function-calling/function-calling-groq.py` at v1.12.0.
- **[V]** 1.12.0 examples use `PipelineWorker` / `PipelineParams` from `pipecat.pipeline.worker` and `WorkerRunner`. There's more detail in `pipecat.md`.
- **[V]** `cancel_on_interruption=False` makes a call asynchronous: the LLM keeps talking and the result is injected later. Keep the default (`True`) for `create_ticket` so the confirmation is spoken after the tool returns.

### 3.3 Known issues relevant to Groq tool calling

- **[V]** Issue #1168 (2025, closed) reports Groq tool-call failures raising "Failed to call a function... See 'failed_generation'". That is Groq's 400 on a malformed tool call, and it was most common with older Llama models. https://github.com/pipecat-ai/pipecat/issues/1168
- **[V]** Issue #2787 (closed 2026-08-11) covers models (Kimi, Llama on Groq) that return content **and** tool_calls in one turn, which affects context ordering. Maintainers recommend `TTSSpeakFrame` in `on_function_calls_started` for the filler line. https://github.com/pipecat-ai/pipecat/issues/2787
- **[V]** Issue #3273 (closed 2026-07-01) was a race in `_run_parallel_function_calls` and is fixed in 1.x. https://github.com/pipecat-ai/pipecat/issues/3273
- **[V]** The OpenAI-compatible stream handler reads `delta.tool_calls[0]` per chunk (`base_llm.py` ~L569). That's fine for gpt-oss on Groq, which never emits parallel calls.
- **[I]** Mitigations: temperature 0.2 or lower, `enum`s and `required` in schemas, short tool descriptions, and a catch-and-retry on `failed_generation` 400s (or fail over to the OpenRouter service with Pipecat's `ServiceSwitcher`; not verified in this pass).

---

## 4. Recommendation

| | Model | Where | Settings | Expected TTFT |
|---|---|---|---|---|
| **Primary** | `openai/gpt-oss-120b` | Groq, **Developer tier** | `reasoning_effort="low"`, temp 0.2, `max_completion_tokens` ~400 | about 0.4-0.8 s for 2-4k-token prompts **[I]** (AA: 4.95 s at 10k input with default reasoning **[V]**) |
| **Fallback A (same vendor, faster)** | `openai/gpt-oss-20b` | Groq | same | about 0.3-0.5 s **[I]** |
| **Fallback B (different vendor)** | `openai/gpt-oss-120b` | OpenRouter, provider pinned to Cerebras | same, provider routing via `extra_body` | about 0.3-0.6 s **[I]** (AA: Cerebras is about 3x faster TTFT than Groq on the same workload **[V]**) |
| Experimental | `qwen/qwen3.8-27b` | Groq (preview) | `reasoning_effort="none"`, temp 0.7, top_p 0.8 | likely the lowest of all **[I]**, but preview churn risk |

Why gpt-oss-120b: it's the only large production model left on Groq, Groq names it as the replacement for every deprecated chat model, it has the best published Hindi score among Groq-hosted options, and it supports tool use and JSON-schema mode. Low reasoning effort keeps the hidden reasoning prefix short. **[I]** Before demo day, run a 20-utterance smoke test covering Hinglish (Latin and Devanagari), Tamil, Telugu and Kannada, and check that (a) the reply language matches the user's and (b) tool arguments come out in English. Tamil, Telugu and Kannada quality is unbenchmarked for these models.

## Sources

- https://console.groq.com/docs/models
- https://console.groq.com/docs/deprecations
- https://console.groq.com/docs/rate-limits
- https://console.groq.com/docs/tool-use
- https://console.groq.com/docs/reasoning
- https://console.groq.com/docs/model/openai/gpt-oss-120b
- https://console.groq.com/docs/model/qwen/qwen3.8-27b
- https://openrouter.ai/docs/api/reference/limits
- https://openrouter.ai/docs/faq
- https://openrouter.ai/api/v1/models?supported_parameters=tools (live API, 2026-10-01)
- https://openrouter.ai/api/v1/models/openai/gpt-oss-120b/endpoints (live API)
- https://pypi.org/project/pipecat-ai/1.12.0/
- https://github.com/pipecat-ai/pipecat/tree/v1.12.0 (`src/pipecat/services/groq/llm.py`, `services/openrouter/llm.py`, `services/openai/base_llm.py`, `services/llm_service.py`, `adapters/schemas/*`, `processors/aggregators/llm_context.py`, `llm_response_universal.py`, `examples/function-calling/function-calling-groq.py`)
- https://docs.pipecat.ai/server/services/llm/groq
- https://docs.pipecat.ai/server/services/llm/openrouter
- https://docs.pipecat.ai/guides/learn/function-calling
- https://github.com/pipecat-ai/pipecat/issues/1168 , /2787 , /3273
- https://artificialanalysis.ai/models/gpt-oss-120b/providers
- https://arxiv.org/pdf/2508.10925 (gpt-oss model card)
