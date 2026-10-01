"""Benchmark cheap/fast tool-calling LLMs for KB's voice loop (tool call -> tool result -> spoken reply).
Never prints keys. Usage: python3 bench.py [runs]"""
import json, time, sys, statistics, urllib.request, urllib.error, pathlib, concurrent.futures as cf, re

ENV = pathlib.Path(__file__).resolve().parents[2] / ".env"
OUT = pathlib.Path(__file__).parent
env = {}
for line in ENV.read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) kbos-bench/0.1"}
RUNS = int(sys.argv[1]) if len(sys.argv) > 1 else 2

SYS = """You are KB, the voice assistant inside KBOS, a factory ticketing app. You are talking to Priya Nair, Operator, Night shift (20:00-08:00). Now is 22:10.
Plant machines: 4B (CNC lathe), 2A (hydraulic press), 3C (conveyor), 1D (compressor), 5A (CNC mill), 6B (grinder).
Rules:
- Speak in the user's language and style. If they speak Hinglish, reply in Hinglish written in Latin script. If English, reply in English. If Hindi in Devanagari, reply in Hindi in Devanagari.
- Spoken replies: one or two short sentences, no lists, no markdown, numbers as words.
- Use tools for every ticket action. ALL tool argument values must be in clear English, even when the user spoke Hindi. Translate.
- When filing a ticket, call update_ticket_draft as soon as you learn anything, then ask only for what is still missing.
- When the user asks what's open or about tickets, call search_tickets, then summarize briefly: count, and mention critical or overdue ones first."""

TOOLS = [
    {"type": "function", "function": {"name": "update_ticket_draft",
        "description": "Create or update the ticket draft the user is dictating. Call whenever you learn a field. Values in English.",
        "parameters": {"type": "object", "properties": {
            "machine_code": {"type": "string", "enum": ["4B", "2A", "3C", "1D", "5A", "6B"]},
            "title": {"type": "string", "description": "Short English title, e.g. 'Vibration on 4B after tool change'"},
            "symptom": {"type": "string", "description": "What was observed, in English"},
            "context": {"type": "string", "description": "What was happening when it started, in English"},
            "since": {"type": "string", "description": "When it started, e.g. '21:50' or 'about 20 minutes ago'"},
            "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
            "machine_running": {"type": "boolean"}}}}},
    {"type": "function", "function": {"name": "search_tickets",
        "description": "Find tickets to show on screen and summarize.",
        "parameters": {"type": "object", "properties": {
            "statuses": {"type": "array", "items": {"type": "string", "enum": ["open", "in_progress", "monitoring", "closed"]}},
            "machine_code": {"type": "string"},
            "assigned_to_me": {"type": "boolean"},
            "created_after": {"type": "string", "description": "ISO time"}}}}},
    {"type": "function", "function": {"name": "add_check",
        "description": "Record a Check on a ticket: what was checked and what was found, optionally changing status.",
        "parameters": {"type": "object", "required": ["ticket_id", "what_checked", "what_found"], "properties": {
            "ticket_id": {"type": "string"}, "what_checked": {"type": "string"}, "what_found": {"type": "string"},
            "new_status": {"type": "string", "enum": ["open", "in_progress", "monitoring", "closed"]}}}}},
    {"type": "function", "function": {"name": "assign_ticket",
        "description": "Set the assignees of a ticket.",
        "parameters": {"type": "object", "required": ["ticket_id", "person_names"], "properties": {
            "ticket_id": {"type": "string"}, "person_names": {"type": "array", "items": {"type": "string"}}}}}},
    {"type": "function", "function": {"name": "request_photo",
        "description": "Open the camera sheet on the user's phone so they can attach a photo or skip.",
        "parameters": {"type": "object", "properties": {}}}},
]

CASES = [
    {"name": "hinglish_file", "user": "4B machine mein tool change ke baad bahut vibration aa raha hai, machine abhi chal rahi hai",
     "tool": "update_ticket_draft", "lang": "latin_hi",
     "result": {"ok": True, "draft_id": "D-12", "still_missing": ["since"], "related_ticket": {"id": "KB-0141", "title": "Unusual vibration on 4B after tool change", "status": "monitoring", "last_check": "17:45 Ravi: 'Checked' (unclear)"}}},
    {"name": "hindi_deva_file", "user": "4B मशीन में टूल चेंज के बाद बहुत वाइब्रेशन आ रहा है, मशीन अभी चल रही है",
     "tool": "update_ticket_draft", "lang": "deva",
     "result": {"ok": True, "draft_id": "D-13", "still_missing": ["since"], "related_ticket": None}},
    {"name": "english_query", "user": "what's open today?", "tool": "search_tickets", "lang": "en",
     "result": {"count": 3, "tickets": [
         {"id": "KB-0141", "title": "Unusual vibration on 4B after tool change", "status": "monitoring", "severity": "high", "created": "14:20", "next_check_due": "20:00 (overdue)"},
         {"id": "KB-0142", "title": "Hydraulic oil leak on 2A", "status": "open", "severity": "critical", "created": "10:05"},
         {"id": "KB-0139", "title": "Conveyor 3C belt slipping", "status": "in_progress", "severity": "medium", "created": "09:40"}]}},
]


def stream(url, headers, body):
    r = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **UA, **headers})
    t0 = time.perf_counter()
    try:
        resp = urllib.request.urlopen(r, timeout=45)
    except urllib.error.HTTPError as e:
        return {"err": f"HTTP {e.code} {e.read()[:160]!r}"}
    except Exception as e:
        return {"err": repr(e)[:160]}
    first, text, calls, provider = None, "", {}, None
    try:
        for raw in resp:
            line = raw.decode(errors="replace").strip()
            if not line.startswith("data:") or line.endswith("[DONE]"):
                continue
            try:
                d = json.loads(line[5:])
            except Exception:
                continue
            if d.get("error"):
                return {"err": str(d["error"])[:160]}
            provider = d.get("provider") or provider
            delta = (d.get("choices") or [{}])[0].get("delta", {}) or {}
            if (delta.get("content") or delta.get("tool_calls")) and first is None:
                first = time.perf_counter() - t0
            text += delta.get("content") or ""
            for tc in delta.get("tool_calls") or []:
                c = calls.setdefault(tc.get("index", 0), {"id": tc.get("id"), "name": "", "args": ""})
                c["id"] = c["id"] or tc.get("id")
                fn = tc.get("function") or {}
                c["name"] += fn.get("name") or ""
                c["args"] += fn.get("arguments") or ""
    except Exception as e:
        return {"err": repr(e)[:160]}
    return {"first": first, "total": time.perf_counter() - t0, "text": text, "calls": list(calls.values()), "provider": provider}


def ascii_ratio(s):
    s = re.sub(r"\s", "", s)
    return sum(c.isascii() for c in s) / max(1, len(s))


def lang_ok(text, lang):
    deva = sum("ऀ" <= c <= "ॿ" for c in text)
    letters = sum(c.isalpha() for c in text) or 1
    if lang == "deva":
        return deva / letters > 0.5
    if lang == "latin_hi":
        hi_words = len(re.findall(r"\b(hai|hain|kya|ke|ki|ka|se|mein|aap|kab|raha|rahi|ho|toh|bataiye|batao|abhi|liye|par|nahi)\b", text.lower()))
        return deva == 0 and hi_words >= 2
    return deva == 0 and ascii_ratio(text) > 0.95


def run_case(target, case):
    name, url, headers, extra = target
    msgs = [{"role": "system", "content": SYS}, {"role": "user", "content": case["user"]}]
    body = {**extra, "stream": True, "max_tokens": 500, "temperature": 0.2, "tools": TOOLS, "messages": msgs}
    s1 = stream(url, headers, body)
    if "err" in s1:
        return {"err": s1["err"]}
    calls = s1["calls"]
    ok_tool = bool(calls) and calls[0]["name"] == case["tool"]
    args_ok, args = False, {}
    if calls:
        try:
            args = json.loads(calls[0]["args"] or "{}")
            args_ok = True
        except Exception:
            args_ok = False
    eng_args = all(ascii_ratio(str(v)) > 0.97 for v in args.values()) if args else False
    hindi_words_in_args = bool(re.search(r"\b(raha|rahi|hai|bahut|mein|ke baad)\b", json.dumps(args).lower()))
    schema_ok = args_ok and not (case["tool"] == "search_tickets" and "statuses" in args and not isinstance(args["statuses"], list))
    res = {"t1_first": s1["first"], "t1_total": s1["total"], "tool_ok": ok_tool, "args_ok": schema_ok,
           "eng_args": eng_args and not hindi_words_in_args, "args": args, "pre_text": s1["text"][:80], "provider": s1["provider"]}
    if not calls:
        res["reply"] = s1["text"][:160]
        res["lang_ok"] = lang_ok(s1["text"], case["lang"])
        return res
    call_id = calls[0]["id"] or "call_1"
    msgs2 = msgs + [
        {"role": "assistant", "content": s1["text"] or None, "tool_calls": [{"id": call_id, "type": "function", "function": {"name": calls[0]["name"], "arguments": calls[0]["args"] or "{}"}}]},
        {"role": "tool", "tool_call_id": call_id, "content": json.dumps(case["result"])},
    ]
    s2 = stream(url, headers, {**body, "messages": msgs2})
    if "err" in s2:
        res["err2"] = s2["err"]
        return res
    res.update({"t2_first": s2["first"], "t2_total": s2["total"], "reply": s2["text"][:200], "lang_ok": lang_ok(s2["text"], case["lang"]),
                "extra_calls": [c["name"] for c in s2["calls"]]})
    return res


OR = "https://openrouter.ai/api/v1/chat/completions"
ORH = {"Authorization": f"Bearer {env['OPENROUTER_API_KEY']}"}


def ort(model, provider=None, **extra):
    body = {"model": model, **extra}
    if provider:
        body["provider"] = {"order": [provider], "allow_fallbacks": False}
    return (f"{model}@{provider or 'auto'}", OR, ORH, body)


TARGETS = [
    ("sarvam-105b-conversations", "https://api.sarvam.ai/v1/chat/completions", {"api-subscription-key": env["SARVAM_API_KEY_3"]}, {"model": "sarvam-105b-conversations"}),
    ort("openai/gpt-oss-20b", "Groq", reasoning={"effort": "low"}),
    ort("openai/gpt-oss-120b", "Groq", reasoning={"effort": "low"}),
    ort("openai/gpt-oss-120b", "Cerebras", reasoning={"effort": "low"}),
    ort("openai/gpt-oss-120b", "SambaNova", reasoning={"effort": "low"}),
    ort("meta-llama/llama-3.3-70b-instruct", "Groq"),
    ort("meta-llama/llama-3.1-8b-instruct", "Groq"),
    ort("google/gemini-2.5-flash-lite", "Google AI Studio"),
    ort("google/gemini-3.1-flash-lite", "Google", reasoning={"effort": "minimal"}),
    ort("inception/mercury-2.5", "Inception"),
    ort("mistralai/mistral-small-3.2-24b-instruct", "Mistral"),
    ort("mistralai/ministral-8b-2512", "Mistral"),
    ort("openai/gpt-4.1-nano", "OpenAI"),
    ort("openai/gpt-4o-mini", "OpenAI"),
    ort("openai/gpt-6-luna", "OpenAI", reasoning={"effort": "minimal"}),
    ort("deepseek/deepseek-v4-flash", "Baidu", reasoning={"enabled": False}),
    ort("nvidia/nemotron-3.5-lightning", "DeepInfra", reasoning={"enabled": False}),
    ort("qwen/qwen3.7-flash", "Alibaba", reasoning={"enabled": False}),
    ort("google/gemma-4-26b-a4b-it", "Cloudflare"),
    ort("upstage/solar-mini4", "Upstage"),
    ort("bytedance-seed/seed-2.0-mini", "Seed", reasoning={"enabled": False}),
    ort("xiaomi/mimo-v2.6-flash", "Xiaomi", reasoning={"enabled": False}),
    ort("nvidia/nemotron-3.5-lightning:free", None, reasoning={"enabled": False}),
    ort("google/gemma-4-31b-it:free", None),
    ort("qwen/qwen3.8-27b:free", None, reasoning={"enabled": False}),
    ort("thinkingmachines/inkling-small:free", None),
]


def bench_target(t):
    out = []
    for r in range(RUNS):
        for c in CASES:
            out.append((c["name"], run_case(t, c)))
            if any("err" in x and "429" in x["err"] for _, x in out[-1:]):
                time.sleep(3)
    return t[0], out


results = {}
with cf.ThreadPoolExecutor(10) as ex:
    for name, out in ex.map(bench_target, TARGETS):
        results[name] = out
json.dump(results, open(OUT / "bench_results.json", "w"), ensure_ascii=False, indent=1)


def med(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return statistics.median(xs) if xs else None


def f(x):
    return f"{x:4.2f}" if isinstance(x, (int, float)) else "  - "


print(f"{'target':48s} {'t1':>5s} {'t2':>5s} {'turn':>5s} {'max':>5s} tool args eng lang errs")
rows = []
for name, out in results.items():
    ok = [x for _, x in out if "err" not in x]
    errs = len(out) - len(ok)
    t1 = med([x.get("t1_first") for x in ok])
    t2 = med([x.get("t2_first") for x in ok])
    turns = [x["t1_total"] + x["t2_first"] for x in ok if x.get("t2_first") and x.get("t1_total")]
    turn = med(turns)
    mx = max(turns) if turns else None
    tool = sum(x.get("tool_ok", False) for x in ok)
    args = sum(x.get("args_ok", False) for x in ok)
    eng = sum(x.get("eng_args", False) for x in ok)
    lang = sum(x.get("lang_ok", False) for x in ok)
    rows.append((turn if turn else 99, f"{name:48s} {f(t1)} {f(t2)} {f(turn)} {f(mx)} {tool:2d}/{len(out)} {args:2d}/{len(out)} {eng:2d}/{len(out)} {lang:2d}/{len(out)} {errs}"))
for _, line in sorted(rows):
    print(line)
print("\nt1 = time to first tool-call token; turn = tool call complete + time to first spoken token of the reply (median); max = worst turn")
