# KBOS: build plan (the spec the implementation session works from)

Read alongside these files:
- `CONTEXT.md`: the glossary. Use these exact words in code, UI copy and prompts.
- `docs/adr/`: why the architecture looks the way it does.
- `docs/research/*.md`: verified API facts and gotchas.
  - `pipecat.md`: Pipecat 1.12 API and the React Native client.
  - `sarvam.md`: STT, TTS, LLM and credits.
  - `llm-benchmark.md`: measured latencies.
  - `gnani.md`: TTS fallback only.
  - `laya.md`: rejected.

Deadline: presenting at about **08:00 on 2026-10-02**. **Feature-freeze at 06:30.** After that it's only rehearsal, fixes and the runbook.

---

## 1. The product in one paragraph

KBOS is a voice-first ticketing app for a small factory floor. A worker taps their face to start a shift. KB, the assistant, gives a spoken **Shift Brief** while the relevant ticket cards animate in. After that, the whole interface is one glowing orb: tap it and it morphs into a pill docked at the bottom, with a live waveform and a stop button.

Workers talk to KB in English, Hindi or Hinglish. KB files tickets by interviewing them, and the **Draft** card fills in live as they speak. KB also shows tickets on request, records **Checks**, changes status, and reassigns. It never accepts a bare "checked" without asking once what was checked and found; if the worker won't say, the Check is permanently flagged **Unclear**. At end of shift, KB runs a **Handover**. A web dashboard lets an Admin watch and moderate everything live and drive the demo (fault injection, reset).

The pitch: *the static dashboard is replaced by a conversation, and the night shift never again inherits a mystery.*

## 2. Settled decisions (don't relitigate)

| Area | Decision |
|---|---|
| Platform | Android only. Expo **SDK 55** dev build (RN 0.83.4). Not Expo Go. APK sideloaded via adb. |
| Voice transport | Pipecat **1.12.0** SmallWebRTC, phone straight to laptop (ADR 0003). |
| STT | Sarvam realtime STT (`saaras:v4`, or `saaras:v3-realtime` if v4 underperforms), `stream_type="fast"`. Pick `mode`/`language_code` by test (§6.3). |
| LLM | `sarvam-105b-conversations`. Fallback via env: OpenRouter `openai/gpt-oss-120b` pinned to Groq, then Cerebras (key capped at $1). |
| TTS | Sarvam `bulbul:v3` over WebSocket. Fallback via env: Gnani `timbre-v2.5` (needs a browser User-Agent header, see gnani.md). |
| Laya | Not used. |
| Languages | Conversation in English, Hindi or Hinglish, mirroring the user. **All UI text is English** except live captions, which show exactly what was heard and said. Tickets are stored in English (ADR 0002). |
| Roles | Operator, Supervisor, Maintenance Technician (mobile); Admin (dashboard only). |
| Close permission | Only Supervisors and Maintenance Technicians can close. Operators can file, add Checks and set In Progress or Monitoring. If an Operator asks to close, KB explains and offers Monitoring. |
| Status | Open → In Progress → Monitoring → Closed. Every status change carries a Check. Monitoring needs an owner and a next-check time; when that time passes it shows as **overdue**. No verification step. |
| Unclear Check | KB asks **once** for what was checked and what was found. If the worker brushes it off, KB records the Check as given with `unclear=true`, shown as an amber badge forever. The next Shift Brief calls it out. |
| Required Draft fields | Machine, symptom, since when, context, severity, production impact (machine running?). KB asks only for what's missing, once each. If the worker is vague or says "don't know", accept "not given" and move on. **Never force.** |
| Photos | Optional. KB offers once via the in-app camera sheet; the worker can skip. No AI vision; photos are only attached. |
| Proactive speech | KB speaks unprompted **only** for the Shift Brief (login) and the Handover (logout). All other live updates are silent: a card plus a haptic. |
| Telemetry alerts | **Not required.** Fault injection changes telemetry only; the worker notices and reports it. |
| Login | People grid: tap your face and your shift starts. The top bar shows avatar + shift chip on the left and **End shift** on the right. |
| Conversation mode | Hands-free while the pill is open, with barge-in. The stop button closes it, and so does 15 s of silence. The connection stays warm in the background, so a tap gives instant listening (§6.5). |
| Visual direction | **Light, calm, Siri/ChatGPT-voice style**: off-white background, a soft multicolor orb, clean white cards, restrained colour used only for meaning. The dashboard uses the same language. |
| Network (demo) | All devices on one phone hotspot. The server URL is editable in the app. Tailscale is the fallback. |
| Dashboard | Vite + React + TS + Tailwind + shadcn/ui, served by the backend at `/admin`. |
| Names | App: **KBOS**. Assistant: **KB**. Seed people are made up (§5.6). |

## 3. Architecture

```
 Phone (Expo app)                          Laptop (one Python process, uvicorn :7860)
 ┌───────────────────────┐   WebRTC audio  ┌──────────────────────────────────────────────┐
 │ orb / pill / cards    │◄──────────────► │ SmallWebRTC handler ─► per-session Pipecat bot│
 │ @pipecat-ai/client-js │   RTVI data ch. │   STT(Sarvam) → user agg(VAD+SmartTurn)       │
 │  + RN SmallWebRTC     │◄──────────────► │   → LLM(Sarvam 105b, tools) → TTS(Bulbul v3)  │
 │ REST + /ws (live data)│◄──── HTTP/WS ──►│ FastAPI: REST, /ws broadcast, /uploads        │
 └───────────────────────┘                 │ Domain services + SQLite (WAL)                │
 Browser (dashboard /admin) ◄──HTTP/WS───► │ Telemetry simulator (1 Hz, in-memory ring)    │
                                           └──────────────────────────────────────────────┘
```

Use **one process** so the bot's tool handlers call the domain layer directly and broadcast to `/ws` in-process. Build our own FastAPI app and wire `SmallWebRTCRequestHandler` into it, mirroring what `pipecat.runner.run` does (`/start`, `/sessions/{id}/api/offer` with POST + PATCH). Don't run the Pipecat dev runner, because we need our own routes, startup and DB in the same app. Match the endpoint shapes the RN transport expects (read pipecat.md §2 and the example's `VoiceClientContext.tsx`).

### Repo layout

```
kbos/
  backend/              uv project, Python 3.12 (not the system 3.14: aiortc/av/onnxruntime wheels)
    kbos/
      app.py            FastAPI app factory, routes, static, /ws, startup (seed if empty, telemetry task)
      config.py         env loading, key pool, provider switches
      db.py, models.py  SQLModel/SQLAlchemy models + session helpers
      domain/           tickets.py, checks.py, shifts.py, people.py, related.py, brief.py (pure logic, unit-tested)
      telemetry.py      simulator + ring buffer + inject/reset
      realtime.py       /ws hub (broadcast typed events)
      voice/
        bot.py          per-session pipeline factory
        tools.py        LLM tool schemas + handlers (call domain/, push RTVI messages)
        prompts.py      system prompt builder + live context block
        gate.py         STT gate + lazy-connect wrapper (§6.5)
        language.py     reply-language → TTS settings processor
        keypool.py      Sarvam key rotation
        textmode.py     run the same LLM+tools loop from text (tests, typed input)
      seed.py           demo seed relative to now
    tests/              pytest: domain, API, tool scenarios (text mode), voice e2e (opt-in, costs credits)
  app/                  Expo SDK 55 app (expo-router, TS strict)
  dashboard/            Vite React shadcn app (build → served at /admin)
  scripts/              start.sh, device.sh (adb helpers), voice_e2e.py, gen_test_audio.py
  docs/                 PLAN.md, adr/, research/, RUNBOOK.md (written at the end)
```

## 4. Domain model

### Entities (SQLite)

- **Person**: `id, name, initials, role (operator|supervisor|maintenance|admin), shift (day|night), preferred_language (en|hi), avatar_hue`
- **Machine**: `code ("4B"), name ("CNC Lathe"), line, target_per_shift, unit ("parts")`
- **Ticket**: `id (int), key ("KB-0142"), title, description, machine_code, severity (critical|high|medium|low), status (open|in_progress|monitoring|closed), reporter_id, symptom, since_text, context, machine_running (bool|null), next_check_at, monitoring_owner_id, telemetry_snapshot (JSON), transcript (JSON: [{who, text, lang, at}]), source_language, created_at, updated_at, closed_at`
- **TicketAssignee**: `ticket_id, person_id`. Multiple assignees are allowed.
- **TicketLink**: `ticket_id, related_ticket_id`. Symmetric; store both directions.
- **Check**: `id, ticket_id, author_id, what_checked, what_found, status_from, status_to, unclear (bool), next_check_at, created_at`
- **Photo**: `id, ticket_id (null while on a Draft), session_id, path, created_at, uploader_id`
- **ShiftSession**: `id, person_id, started_at, ended_at, brief_text, handover_summary`
- **GlossaryTerm**: `term, meaning`
- **Event**: `id, type, payload JSON, at`. This is the activity feed for the dashboard.

A **Draft** lives in per-voice-session memory, not in the DB. Its photos are DB rows with `ticket_id = null`, attached on filing.

### Rules (enforce in `domain/`, not just in prompts)

- A status change without a Check fails with a message KB can relay: "needs a check: ask what was checked and what was found."
- Closing requires the actor's role to be Supervisor or Maintenance. Otherwise the error says "operators can't close, offer monitoring".
- Monitoring requires `next_check_at`, defaulting to now + 2 h, and the owner is the actor. **Overdue** is computed: `status == monitoring and next_check_at < now`.
- `unclear` is set by the tool argument. The domain also forces `unclear=true` if `what_checked` or `what_found` is empty or a bare "checked"/"ok"/"done".
- **Filing:**
  - Requires `machine_code` + `symptom`, with a generated title. Other fields may be "not given".
  - Attaches a telemetry snapshot: the last 30 min downsampled to 60 points, plus current values and output against target.
  - Attaches the Draft's photos and the transcript.
  - Auto-assigns the on-shift Maintenance Technician; for Critical, also the on-shift Supervisor.
  - Links the `related_ticket_id` if given.
- **Related Tickets:**
  - Candidates are non-closed tickets on the same machine, plus tickets closed in the last 7 days on the same machine.
  - They're ranked by keyword overlap of English symptom/title (stem match on "vibration", "leak", "noise", etc.).
  - They come back from `update_draft` as `possible_related`.
- **Shift Brief data**, computed in `domain/brief.py`:
  - non-closed tickets, critical first;
  - overdue Monitoring;
  - Unclear Checks made since the person's last shift;
  - tickets assigned to them;
  - what changed since their last ShiftSession ended (or the last 12 h).

### Shorthand Glossary seed

| Term | Meaning |
|---|---|
| TC | tool change |
| vib | vibration |
| SB | spindle bearing |
| PM | preventive maintenance |
| LC | light curtain |
| hyd | hydraulic |
| jhatka | jerk / shock load |
| awaaz | abnormal noise |
| garam | running hot |
| leakage | fluid leak |
| ok kar diya | fixed (ask how) |

KB gets the glossary in its prompt. The machine codes and glossary terms also go to STT as `keyterms` (saaras:v4) to bias recognition.

## 5. Backend

### 5.1 REST (JSON, all under `/api`)

| Method & path | Purpose |
|---|---|
| `GET /health` | DB, active sessions, key-pool status (per key: ok/exhausted/untested, never the key itself), provider config |
| `GET /people` | People with on-shift-now flag, sorted current shift first; admin excluded unless `?all=1` |
| `POST /shifts/start {person_id}` → `{shift_session}` | Starts a ShiftSession. Closes any open one for that person. Broadcasts. |
| `POST /shifts/{id}/end {summary?}` | Ends it. Normally called by the `end_shift` tool. |
| `GET /tickets?status=&machine=&assignee=&q=&since=` | Lists tickets, including overdue and unclear flags, assignee names, and last Check |
| `GET /tickets/{key}` | Full detail: Checks timeline, photos, links, telemetry snapshot, transcript |
| `PATCH /tickets/{key}` | Dashboard moderation: title, description, severity, assignees, status (a status change needs a Check body) |
| `POST /tickets/{key}/checks` | Adds a Check from the dashboard; the Admin is the author |
| `POST /uploads` (multipart: `file`, `session_id`) → `{photo_id, url}` | Saves under `backend/uploads/` and resizes to max 1600 px |
| `GET /machines` | Machines with live telemetry + output vs target |
| `GET /machines/{code}/telemetry?minutes=30` | Telemetry series |
| `GET/PUT /glossary` | Read and edit the Shorthand Glossary |
| `GET /shifts?limit=` | Handover log |
| `GET /metrics` | Open count, critical count, overdue Monitoring, mean time to close (last 7 days) |
| `POST /demo/inject {machine_code, kind: "vibration"}` | Ramps vibration to about 9.5 mm/s over 20 s, with temperature rising |
| `POST /demo/clear {machine_code}` | Returns the machine to baseline |
| `POST /demo/reset` | Wipes and re-seeds relative to now, resets telemetry, broadcasts `demo.reset` (clients refetch and return to the people grid) |

Static routes: `/uploads/*` and `/admin/*` (dashboard build, with SPA fallback).

### 5.2 Live events on `GET /ws` (server → all clients)

Each event is `{type, at, data}`. The types are:
- `ticket.created`, `ticket.updated`, `check.added`
- `shift.started`, `shift.ended`
- `telemetry` (1 Hz, all machines, compact)
- `glossary.updated`, `demo.reset`

The app uses `/ws` for silent live updates, e.g. a new ticket assigned to you (card + haptic) and refreshing visible lists. The dashboard uses it for everything.

### 5.3 Telemetry simulator

1 Hz per machine, held in an in-memory ring of 2 h. Fields:
- `vibration_mm_s` (ISO 10816 velocity RMS: good < 2.8, warning 2.8–7.1, alarm > 7.1)
- `temperature_c`
- `load_pct`
- `output_count` (cumulative this shift, at a rate that tracks the target)

4B sits at about 4.5 mm/s (warning) since the seeded tool change. Use smooth noise (Ornstein–Uhlenbeck), never white noise. Injection ramps with a smoothstep, and a running machine's output keeps growing.

### 5.4 Key pool

All 8 `SARVAM_API_KEY_n` are loaded. A startup check makes one tiny call per key and records whether it's OK. Assign a key round-robin per voice session and rotate on 401/402/403/429. Each rotation logs only a key index, never a value.

### 5.5 Config (`.env`, already present)

Existing keys:
- `SARVAM_API_KEY_1..8`
- `GNANI_API_KEY`
- `OPENROUTER_API_KEY`

Add non-secret settings with defaults in `config.py`:
- `LLM_PROVIDER=sarvam|openrouter`
- `TTS_PROVIDER=sarvam|gnani`
- `TTS_VOICE` (pick by test; candidates `ritu`, `kavya`, `shruti`, `aditya`)
- `STT_MODEL`, `STT_MODE`, `STT_LANGUAGE`
- `IDLE_TIMEOUT_S=15`
- `PUBLIC_HOST`

Create `.env.example` with the names only.

### 5.6 Seed (relative to now; the demo is at about 08:00, so "previous shift" = Night)

People:
- **Day (08:00–20:00):**
  - Ramesh Yadav, Operator. Preferred language **en**; he switches to Hinglish on stage to show language mirroring.
  - Kavita Sharma, Supervisor, en.
  - Imran Shaikh, Maintenance Technician, hi.
- **Night (20:00–08:00):**
  - Priya Nair, Operator, en.
  - Suresh Patil, Supervisor, hi.
  - Arjun Mehta, Maintenance Technician, en.
- **Admin:** Neha Kulkarni.

Machines:

| Code | Machine | Location | Target per shift |
|---|---|---|---|
| 4B | CNC Lathe | Line 4 | 120 parts |
| 2A | Hydraulic Press | Line 2 | 900 strokes |
| 3C | Belt Conveyor | Line 3 | (none) |
| 1D | Air Compressor | Utilities | (none) |
| 5A | CNC Mill | Line 5 | 80 parts |
| 6B | Surface Grinder | Line 6 | 150 parts |

Use the night/day mapping relative to the wall clock at seed time. If seeding during a Night shift, swap the roles of the two shifts so the "previous shift" story still holds.

The star ticket, a replay of the case study, is **KB-0141 "Unusual vibration on 4B after tool change"**, High:
- Filed by Priya (previous-shift Operator) at **now − 5h40m**. Transcript in English. Context: "right after a tool change". Telemetry snapshot shows about 4.5 mm/s.
- **now − 2h15m**: Suresh (previous-shift Supervisor) adds a Check with `what_checked=""`, `what_found="Checked"`, `unclear=true`, status → **Monitoring**, `next_check_at = now − 15m`, so it is **overdue**.

Background tickets (KB-0119…KB-0140, about 8), so the lists look lived-in:

| Machine | Ticket | Severity | State | Notes |
|---|---|---|---|---|
| 2A | Hydraulic oil leak at the main cylinder seal | **Critical** | Open | Opened now − 3h, assigned Arjun. The brief leads with it. |
| 1D | Compressor pressure dropping to 5.8 bar | High | Monitoring, not overdue | Clear Check: "checked the auto-drain valve, found it stuck partly open, cleaned and closed it; pressure back to 6.9 bar", next check now + 2h. The good contrast to KB-0141. |
| 3C | Belt slipping at drive pulley | Medium | In Progress | Imran |
| 2A | Light curtain intermittent trip | High | Open | Unassigned |
| 5A | Coolant concentration low | Low | Closed | Good Check |
| 6B | Wheel guard bolt loose | High | Closed | |
| 4B | Chuck jaw wear | Medium | Closed 3 days ago | 4B history |
| 5A | Spindle warm-up alarm | Medium | Closed | |

The new ticket in the demo becomes **KB-0142**.

## 6. Voice bot

### 6.1 Per-session pipeline

```
transport.input()
→ STTGate(lazy-connect Sarvam realtime STT)   # §6.5
→ user aggregator (Silero VAD stop_secs≈0.2 + LocalSmartTurnAnalyzerV3 (en/hi supported), user_idle_timeout)
→ LLM (SarvamLLMService sarvam-105b-conversations | OpenRouterLLMService) with tools
→ ReplyLanguage processor (sets TTS language from reply script)   # §6.3
→ TTS (SarvamTTSService bulbul:v3 WS, min_buffer_size≈30, sample_rate matched to transport)
→ transport.output()
→ assistant aggregator
```

Use the 1.x API: `PipelineWorker(..., app_resources=session_state)`, `WorkerRunner`, `LLMContext(tools=...)`, `LLMContextAggregatorPair`, and `worker.rtvi` (auto-added). Settings go via `settings=XService.Settings(...)`, with `stream_type="fast"` explicit. Set `RTVIObserverParams(function_call_report_level={"*": NAME})` so the app can show a subtle "working…" shimmer. Attach `UserBotLatencyObserver` and log a per-turn breakdown. Expose the last 10 turns' latency at `/api/health` and in the app's debug panel.

Session identity: `startBotAndConnect` sends `requestData.body = {person_id, shift_session_id, device_id}`. Load the Person and build the prompt from that.

### 6.2 System prompt (`prompts.py`)

The prompt is built from parts:

1. **Identity.** "You are KB, the voice assistant inside KBOS…" Concise, warm, competent; like a sharp shift lead, not a chatbot.
2. **The user.** Name, role, shift, preferred language, and the current local time (IST).
3. **Spoken style.** One or two short sentences. No lists, no markdown, no emojis. Ticket keys are spoken naturally ("ticket one-four-two"). Mention critical and overdue items first.
4. **Language.** Mirror the language of the user's latest utterance.
   - English → English.
   - Hindi or Hinglish → Hindi in **Devanagari**, keeping technical English words in Latin (e.g. "4B पर vibration वाला ticket अभी Monitoring में है"). Sarvam TTS degrades on romanized Hindi.
   - **Tool arguments are always clear English**; translate.
5. **Filing flow.**
   - Call `update_draft` as soon as you learn anything.
   - Ask only for what is missing, one question at a time, each at most once.
   - Accept "don't know" or "not sure".
   - If `possible_related` comes back, ask whether it's the same problem.
   - Offer a photo once via `request_photo`.
   - Then read back a one-sentence summary and ask to file. File on yes.
6. **Check discipline.**
   - Any "checked", "done" or "ok kar diya" → ask once: what did you check, and what did you find?
   - If they won't say, call `add_check(..., unclear=true)`. Don't argue.
7. **Permissions.** Operators can't close; offer Monitoring.
8. **Shorthand Glossary.**
9. **Live context.** Regenerated every user turn:
   - compact open-ticket lines: `KB-0141 | 4B | high | monitoring OVERDUE (due 07:45) | unclear check by Suresh 05:45 | assignees: Arjun`
   - people on shift
   - the current Draft
   - the focused ticket

Keep the whole prompt **under about 2.5k tokens**. Prompt size is latency.

### 6.3 Language plumbing (decide by measurement in M1)

- **STT config.** Generate test audio with Bulbul: 3 English, 3 Hindi and 3 Hinglish shop-floor sentences, mentioning 4B and KB-0141. Compare `language_code="hi-IN", mode="codemix"` against `language_code="auto"`, both with `saaras:v4` + keyterms. Pick by transcript accuracy, then latency. Record the result in `docs/research/stt-config.md`.
- **TTS language.** `ReplyLanguage` processor: if the outgoing text contains Devanagari, use `hi-IN`, else `en-IN`. Push a settings update **only on change**. If switching causes a WebSocket reconnect or extra delay, run a hi-IN-only check instead: round-trip an English reply through STT to see if it's still intelligible. Keep whichever is faster and sounds right.
- **Voice.** Audition 3–4 Bulbul v3 voices by rendering the same Hindi and English lines. Pick one that sounds calm and clear in both languages. Make it settable via env.

### 6.4 Tools (`tools.py`), all arguments in English

| Tool | Behaviour | Pushes | Needs a 2nd LLM call? |
|---|---|---|---|
| `show_tickets(ticket_keys[], heading)` | UI only. Tickets come from the live context. | `ui.tickets` | Try to make the model speak and call this in one response. Measure; if Sarvam can't, accept the second call. |
| `focus_ticket(ticket_key)` | Shows the detail card. Returns full detail (Checks) for follow-up questions. | `ui.ticket` | yes |
| `update_draft(machine_code?, title?, symptom?, context?, since?, severity?, machine_running?)` | Creates or merges the Draft. Returns `{draft, missing, possible_related}`. | `ui.draft` | yes (next question) |
| `request_photo(reason)` | Opens the camera sheet. **Awaits** client `photo.attached{photo_ids}` or `photo.skipped` (timeout 90 s → skipped). | `ui.camera` | yes |
| `file_ticket(related_ticket_key?)` | Validates and files (§4 rules). Returns `{ticket_key, assignees}`. | `ui.ticket_filed` + `/ws` | yes |
| `discard_draft()` | Drops the Draft. | `ui.draft {null}` | yes |
| `add_check(ticket_key, what_checked, what_found, new_status?, next_check_minutes?, unclear)` | Applies the rules; may return a permission error to relay. | `ui.ticket` + `/ws` | yes |
| `update_ticket(ticket_key, title?, description?, severity?)` | Edits that aren't status changes. | `ui.ticket` + `/ws` | optional |
| `assign_ticket(ticket_key, add_names[], remove_names[])` | Fuzzy-matches names against people. Ambiguity returns a question. | `ui.ticket` + `/ws` | yes |
| `end_shift(summary)` | Handover only: ends the ShiftSession. | `ui.shift_ended` | no; the client returns to the people grid after the summary card |

Client → server RTVI messages:
- `listen.start`, `listen.stop`
- `brief.start`, `handover.start`
- `photo.attached {photo_ids}`, `photo.skipped`
- `draft.file`, `draft.discard` (from the buttons on the Draft card; inject a context note so KB acknowledges in one short line)
- `text.input {text}` (hidden typed input; injected exactly like a final transcription)

Server → client RTVI messages, as `{type, ...}`:
- `ui.tickets`, `ui.ticket`, `ui.draft`, `ui.camera`, `ui.ticket_filed`
- `ui.session_end {reason: idle|stop}`
- `ui.shift_ended {summary}`
- `ui.error {message}`

**Log the first `onServerMessage` payload on device**: pipecat.md flags a docs/source mismatch on its shape.

### 6.5 Session lifecycle, warm connection and the STT gate (snappiness without burning credits)

- **On shift start** (app foreground, logged in), the app calls `startBotAndConnect` right away, with the mic track disabled. The pipeline runs, and the TTS socket may connect. **The STT socket stays closed.**
- **Tap the orb** → the client enables the mic and sends `listen.start`. `STTGate` opens:
  - If the Sarvam STT socket isn't connected, it connects now. The realtime service doesn't auto-reconnect; handle that.
  - Audio frames are **buffered** (up to about 2 s) until the socket is ready, then flushed in order, so the first words aren't lost.
  - Target: listening is visually instant, and the first partial transcript appears within about 600 ms of speech.
- **Gate closed** (stop button, `listen.stop`, or idle) → stop forwarding audio and close or idle the STT socket. **No STT billing while the orb is idle.** Interrupt the bot if it's speaking when stop is pressed.
- **Idle:** while the gate is open, if no user speech arrives for `IDLE_TIMEOUT_S`=15 s and the bot isn't speaking, send `ui.session_end{idle}` and close the gate.
- **Shift Brief:**
  - After `brief.start`, the server computes the brief data and pushes `ui.tickets` with the brief set immediately, so cards animate in while KB starts talking.
  - It then appends an instruction message and runs the LLM to speak about 3 sentences, ending with an offer ("Want details on any of them?").
  - Brief language = the Person's preferred language.
  - The pill opens and listens afterwards for follow-ups, under the same idle rule.
- **Handover:** after `handover.start`, the server finds this person's touched, non-closed tickets in this ShiftSession: reported, assigned or Checked by them. KB walks through each ("4B vibration: what's the situation now?") and records `add_check`, then calls `end_shift(summary)`. If no tickets were touched: one friendly line, then `end_shift`.
- **App backgrounded** → disconnect. **Foreground** → reconnect.

### 6.6 Latency targets (measure, log, tune)

| Measure | Target |
|---|---|
| Voice-to-voice, simple turn | p50 ≤ 1.5 s |
| Voice-to-voice, turn with a tool | p50 ≤ 2.3 s |
| End of speech → UI Draft update | ≤ 1.0 s |
| Tap → listening UI | ≤ 100 ms |
| Tap → first partial transcript | ≤ 600 ms after speech starts |

Levers, roughly in order:
1. A smaller prompt.
2. One LLM call where possible (ADR 0004).
3. `stream_type="fast"`.
4. TTS `min_buffer_size` ≈ 30.
5. Smart Turn on.
6. Keep the TTS socket warm.
7. Avoid blocking the event loop (DB calls are tiny; if any get slow, use `asyncio.to_thread`).

## 7. Mobile app (Expo SDK 55, Android)

### 7.1 Stack

- Expo SDK 55, TypeScript strict, expo-router, Reanimated 4, react-native-gesture-handler, expo-haptics.
- `@shopify/react-native-skia` for the orb and the waveform.
- expo-camera and expo-image-picker (gallery fallback), expo-image, react-native-safe-area-context.
- zustand for state, expo-font.
- **Pipecat:**
  - `@pipecat-ai/client-js@1.13.1` (pinned)
  - `@pipecat-ai/react-native-small-webrtc-transport@1.8.0`
  - `@daily-co/react-native-webrtc@124.0.6-daily.2` and the peers listed in pipecat.md
  - `@daily-co/config-plugin-rn-daily-js@0.0.12` and `expo-build-properties` (`minSdkVersion` 24)
- Android permissions: `RECORD_AUDIO`, `CAMERA`, `MODIFY_AUDIO_SETTINGS`, `INTERNET`. Set `usesCleartextTraffic: true` because the backend is plain http on the LAN.
- **Start from** `pipecat-examples/p2p-webrtc/video-transform/client/react-native` (Expo 55, SmallWebRTC) and its `VoiceClientContext.tsx`. Don't use `@pipecat-ai/client-react` (web-only).

### 7.2 Screens and states

1. **People grid** (nobody logged in):
   - "KBOS" wordmark, then a "Who's on shift?" grid of 6 people. Each card has a soft gradient initial avatar, name, role, and a shift chip. The current shift sorts first and is labelled "On shift now".
   - Tapping a person: press feedback + haptic → `POST /shifts/start` → home → auto-connect → `brief.start`.
2. **Home** (logged in):
   - The top bar has the avatar, name and `Day · Operator` chip on the left, and an **End shift** button on the right.
   - The **orb** sits centred. Above or around it is a content stage where conversation-driven cards appear.
   - When the stage is empty, show a quiet glanceable summary (e.g. `3 open · 1 critical · 1 overdue`) and the hint "Tap and talk to KB".
3. **Listening/speaking:**
   - The orb morphs into the **pill** docked at the bottom: live waveform plus a stop button on the right.
   - A **caption** sits above the pill: the user's partial transcript while they speak, then KB's reply text, fading out after a few seconds.
4. **Cards on the stage**, driven by `ui.*` messages:
   - **Ticket list:** a heading plus cards.
     - Each card shows a severity accent, key, machine chip, title, and status pill. Monitoring is amber "Monitoring · not resolved"; overdue gets a red "Overdue" badge.
     - Badges: amber "Unclear check" where it applies, assignee avatars, and age ("5h ago").
   - **Ticket detail (sheet):**
     - header and fields, the Checks timeline (Unclear entries clearly flagged), photos;
     - a telemetry snapshot sparkline with warning/alarm bands;
     - related-ticket chips;
     - the original transcript, collapsed.
   - **Draft card:**
     - Fields appear and fill as KB learns them: machine, title, symptom, since, context, severity chip, production impact, then auto-assignee on filing, and photo thumbnails.
     - Missing fields show as quiet placeholders.
     - Buttons: **File ticket** and **Discard**.
     - On filing, it collapses into a "Filed · KB-0142 · assigned to Imran" success state with a success haptic.
   - **Camera sheet:** slides up on `ui.camera`. It has a shutter, a gallery button and **Skip**. The photo uploads with a progress ring, then the thumbnail flies into the Draft card, and the client sends `photo.attached`.
5. **Silent live updates (`/ws`):**
   - A ticket newly assigned to me drops a small card in from the top, with a haptic. Tapping it opens the ticket. **No speech.**
   - Visible lists refresh in place.
6. **End shift:** opens the pill and runs `handover.start`. On `ui.shift_ended`, show a "Handover recorded" summary card for about 3 s, then return to the people grid.
7. **Settings** (long-press the wordmark):
   - server URL (persisted; default from build config)
   - connection status, last-turn latency breakdown
   - a "type instead of talk" toggle
8. **Hidden typed input:** long-press the pill to get a text field. It sends `text.input`. This is the testing hook and the noisy-venue fallback.

### 7.3 Motion and design (apply the `emil-design-eng`, `apple-design` and `animate-expo` skills)

- **Orb:**
  - Skia: a soft, slowly drifting multicolor gradient (blue, violet, pink, teal), blurred, with idle breathing (scale 1 → 1.03, about 4 s).
  - It reacts to the **user's mic level while listening** and **KB's output level while speaking**, through shared values on the UI thread, never React state.
- **Morph** (orb → pill):
  - Press-in scale 0.97 + `impactLight`.
  - An interruptible spring (start around damping 18, stiffness 180, then tune by feel) animates size, borderRadius and translateY to the docked pill.
  - The waveform fades in after about 100 ms. Reverse on stop.
  - Tapping during the morph must not break it.
- **Cards:**
  - Enter with opacity + translateY 12 → 0 + scale 0.98 → 1, staggered 40–60 ms, ease-out, ≤ 300 ms.
  - Exit faster (≤ 150 ms).
  - Never animate from scale 0. Use layout transitions for list changes.
- **Draft field fill:** the value slides and fades in with a brief highlight wash behind the field (about 600 ms). The severity chip crossfades its colour.
- **Haptics:**
  - selection: picking a person
  - light: open the pill
  - success: filed or closed
  - warning: a permission refusal
- **Typography and palette:**
  - one clean family (e.g. Inter or Geist), with a large calm title and generous spacing;
  - off-white background (#F7F7F5-ish), white cards with soft shadows, ink text;
  - colour only for meaning: critical red, high orange, monitoring and unclear amber, closed green; KB's identity is the orb gradient.
- Honour reduced motion. Hold 60 fps on the Nothing Phone 2a; profile any jank.

## 8. Dashboard (`/admin`)

Vite + React 19 + TS + Tailwind + shadcn/ui (table, sheet, badge, select, dialog, tabs, chart via recharts), sonner for toasts. It's light, matching the app, and **live via `/ws`**: changed rows flash briefly. Use the `frontend-design`, `dataviz` and `ask-sonner` skills.

- **Tickets** (default):
  - A KPI row: Open, Critical, Overdue monitoring, Avg time to close.
  - A table with key, machine, title, severity, status (overdue/unclear badges), assignees, reporter, age, last Check; filters and search.
  - Clicking a row opens a detail sheet. Everything is editable: status (requires a Check form), severity, assignees, title, description. It also shows the Checks timeline, photos, the telemetry snapshot chart, related links and the transcript.
- **Machines:** a card per machine with live sparklines (vibration with ISO bands, temperature, load), output against target, and **Inject vibration** / **Clear** buttons.
- **Shifts:** the handover log (who, when, summary) and the brief text.
- **Glossary:** an editable table.
- **Demo:** **Reset demo** (with confirm), inject/clear per machine, key-pool health, active voice sessions.
- **Activity feed:** a right rail or tab showing the Event stream live.

## 9. Testing and verification (autonomous, overnight)

1. **Domain and API (pytest):**
   - status changes need a Check;
   - close permissions;
   - Unclear forcing;
   - Monitoring defaults and overdue;
   - related-ticket ranking;
   - auto-assignment;
   - brief contents (seeded case-study ticket comes first after the critical one; overdue and unclear are called out);
   - seed relative-time correctness;
   - `/ws` broadcast on mutations.
2. **Conversation scenarios in text mode** (no STT/TTS spend; real LLM). Run each **3×** and assert tool calls and final DB state:
   - Hinglish filing on 4B → `possible_related` = KB-0141 → "haan same" → linked → photo skipped → filed KB-0142, assigned to the day Maintenance Technician, args in English.
   - English "what's open today?" → shows the right set, speaks critical and overdue first, in English.
   - Maintenance "what's assigned to me?" → close KB-0142 with a specific Check → closed.
   - Bare "0141 checked" → KB asks once → "bas check kiya" → Check `unclear=true`.
   - Operator "close 0141" → refused, Monitoring offered.
   - "Assign the 2A leak to Arjun and Imran" → two assignees.
   - Handover with 2 touched tickets → 2 Checks + `end_shift`.

   Fix the prompts and tools until all pass, every run.
3. **Voice end-to-end (Python, opt-in, small credit spend):**
   - `scripts/gen_test_audio.py` renders user utterances with Bulbul (hi/en/Hinglish, two voices).
   - `scripts/voice_e2e.py` is a headless aiortc SmallWebRTC client. It hits `/start` + offer, streams a WAV at real-time pace, records bot audio and RTVI messages, and asserts transcript, tool calls and latency.
4. **On device (Nothing Phone 2a, already on USB, stay-awake on, volume up):**
   - Install with `adb install -r`. Grant mic and camera with `adb shell pm grant`. Use `adb reverse tcp:8081` for Metro.
   - Drive the UI with `adb shell input tap/swipe` and check with `adb exec-out screencap -p > shot.png` (view the screenshots).
   - Voice: play the generated WAVs through the laptop speakers (`pw-play`, laptop volume about 60%) with the phone next to them.
   - WebRTC needs phone ↔ laptop IP reachability. Measured at planning time: the laptop is on campus Wi-Fi (`AMRITA-BLR-Connect`) behind Cloudflare WARP, with **UDP blocked** (`tailscale netcheck`: `UDP: false`). Tailscale works only via the DERP relay, and the phone was not answering even there. So use, in this order:
     1. **USB tethering from the phone** (the user enables it in Android settings). Then set the laptop's new tether connection to `nmcli connection modify <conn> ipv4.never-default yes ipv6.never-default yes` and re-activate it, so the laptop keeps its internet on Wi-Fi and big downloads don't go over the phone's Jio data. The phone is reachable at the tether gateway IP. Verify with `ping` both ways (`adb shell ping`).
     2. Tailscale (laptop 100.101.115.95, phone 100.67.152.63). Relay-only here, so expect extra latency.
     3. A shared phone hotspot, which is the demo-day setup.
   - **Check this first in M1.** Use `adb reverse tcp:8081 tcp:8081` (Metro) and `adb reverse tcp:7860 tcp:7860` (HTTP) regardless; only WebRTC media needs real IP reachability.
5. **Multi-device:** the phone (one person) plus `voice_e2e.py` or text mode as a second person. Confirm the phone gets the silent live card when a ticket is assigned to its person, and that the dashboard updates live (Playwright screenshots).
6. **Full rehearsal:** script the storyline in §11 end to end, run it twice, fix anything that wobbles.

## 10. Milestones (in order; each has an exit gate)

| # | Window | Work | Exit gate |
|---|---|---|---|
| M0 | first 20 min | `git init`. Start the **Android SDK** install in the background (cmdline-tools → platform-tools, platforms;android-36, build-tools, the NDK and CMake versions RN 0.83 needs; `ANDROID_HOME=~/Android/Sdk`). Create the uv project (Python 3.12) with `pipecat-ai[webrtc,silero,sarvam,openrouter]==1.12.0` + fastapi/uvicorn/sqlmodel. Scaffold the Expo app from the pipecat RN example on SDK 55. Scaffold the dashboard. | Installs are progressing; the skeletons are committed |
| M1 | ~1 h | **De-risk spike:** a minimal bot (Sarvam STT→LLM→TTS, no tools) inside our FastAPI app, and a minimal app (connect button + mic). Build the dev APK and install it on the phone. Establish phone ↔ laptop reachability. Do the STT/TTS config tests in §6.3. | **You hear KB answer a Hindi and an English question on the phone.** Latency is logged. STT config is chosen. |
| M2 | ~1 h | Backend domain, REST, `/ws`, telemetry, seed, demo routes, key pool, pytest | All domain/API tests green; the seed reads correctly in `/api/tickets` |
| M3 | ~1 h | Tools, RTVI contract, prompts, text mode, STT gate + lazy connect, idle, brief, handover | All text-mode scenarios pass 3/3; the gate verifiably sends no audio to STT while idle |
| M4 | ~1.5 h | Full app UX + motion (§7). Can run in parallel with M5. | Every storyline step works on the phone; screenshots reviewed; no jank |
| M5 | ~45 min, parallel | Dashboard (§8). A good task to delegate to a subagent once the M2 API contract is frozen. | Live updates, editing, demo controls work (Playwright-verified) |
| M6 | until 06:30 | Full rehearsal ×2, latency tuning, bug fixing | The storyline runs cleanly twice in a row |
| M7 | 06:30–07:15 | `docs/RUNBOOK.md`, `scripts/start.sh`, final commit, leave the server running and the app installed | Runbook verified by following it from a fresh terminal |

Cut order if time runs short, cutting from the bottom first:
1. glossary editor UI
2. dashboard Shifts tab
3. machines sparklines on the dashboard (keep inject buttons)
4. Handover (keep Brief)
5. gallery fallback

**Never cut:** brief, voice filing with the live Draft, related-ticket detection, the photo step, query/close/assign by voice, the Unclear Check flow, the live dashboard, reset demo.

## 11. Demo storyline (rehearse exactly this)

1. **Dashboard** on the laptop/projector, open on Tickets. **Phone 1:** people grid. **Phone 2:** Imran logged in (Day Maintenance).
2. Phone 1: tap **Ramesh** (Day Operator, preferred English). KB briefs in English:
   - "Morning Ramesh. Four tickets carried over from the night shift. The 2A hydraulic leak is critical and still open. The 4B vibration from 02:20 is in Monitoring but not resolved: Suresh marked it checked at 05:45 without saying what was checked, and the next check is overdue…"
   - The cards animate in with the critical and overdue ones highlighted.
3. Admin clicks **Inject vibration on 4B**. The dashboard machine card goes into alarm.
4. Ramesh taps the orb and speaks Hinglish: "KB, 4B pe phir se bahut vibration aa raha hai, awaaz bhi aa rahi hai, machine abhi chal rahi hai."
   - The Draft fills live. KB, in Hindi: "यह KB-0141 वाला ही problem लगता है, जो Monitoring में है। Same issue है?"
   - "Haan." KB: "कब से हो रहा है?" "Das minute se."
   - KB offers a photo. Take it; the thumbnail flies into the Draft.
   - "Severity?" "Critical, production ruk jayega."
   - KB reads the summary back. "Haan, file kar do." → **Filed KB-0142**, linked to KB-0141, assigned to Imran. Success haptic.
5. **Phone 2** (Imran): the new assignment drops in silently with a haptic. Imran taps the orb: "What's assigned to me?" KB lists them, KB-0142 first.
6. Imran: "Close one-four-two. I replaced the spindle bearing, vibration is back to two millimetres per second." → Closed with a specific Check. Then: "Close one-four-one too, same root cause." → Closed.
7. Show the **Unclear** flow on another ticket. "3C checked." → KB: "What did you check, and what did you find?" → "Bas check kar liya." → The Check is recorded with an amber **Unclear** badge.
8. Ramesh taps **End shift**. KB runs the Handover over his touched tickets → "Handover recorded."
9. On the dashboard, open KB-0141: the whole story is there. Original report, the Unclear "Checked", the related KB-0142 with photo and telemetry spike, the specific closing Check. **The night shift never inherits a mystery again.**

## 12. Gotchas collected from research (read before coding)

- **Expo:**
  - Use **SDK 55**, not 57; the Daily config plugin requires it.
  - The dev build is mandatory. `minSdk` 24, `usesCleartextTraffic`.
  - Pin `@pipecat-ai/client-js@1.13.1` to RTVI protocol 2.1.0.
- **Pipecat 1.12:**
  - `PipelineTask` is deprecated; use `PipelineWorker` + `WorkerRunner`.
  - VAD goes on `LLMUserAggregatorParams`. RTVI is automatic, so don't add a second `RTVIProcessor`.
  - Function-call RTVI events carry only the ID unless the report level is raised.
  - The runner binds localhost by default. Our own app must bind `0.0.0.0`.
  - aiortc uses only the first STUN and first TURN URL.
- **Sarvam:**
  - Settings go in `settings=...Settings(...)`; kwargs raise a `TypeError`. Set `stream_type="fast"` explicitly.
  - The realtime STT socket never auto-reconnects.
  - `SarvamLLMService` routes models other than `sarvam-105b-conversations` to `/v2`, which needs approval.
  - Don't pass `reasoning_effort` to the conversations model.
  - Bulbul accepts only v3 voices (lowercase IDs) and prefers Devanagari Hindi.
  - The TTS socket closes after about 1 min idle, so ping it or reconnect.
  - 402 means credits are exhausted; rotate keys.
- **Benchmark finding:** the LLM sometimes answers English in Hinglish and puts Hindi into tool args. The prompt rules plus the per-turn language mirror plus text-mode tests catch this.
- **Gnani (fallback only):** needs a browser `User-Agent` or Cloudflare returns 403 code 1010. REST TTS returns raw PCM; confirm the sample rate. `pipecat-gnani` is broken on 1.12; write a tiny service if it's ever needed.
- **Machine limits:**
  - 15 GB RAM with about 9 GB already used: cap Gradle (`org.gradle.jvmargs=-Xmx3g`, `--max-workers=4`) and don't run two Gradle builds at once.
  - About 28 GB disk free: no emulator images.
- RTVI messages are capped at 64 KB, so photos go over HTTP.
- The phone's Wi-Fi is off and it's on Jio mobile data. The laptop has UDP blocked on campus Wi-Fi + WARP. Establish reachability in M1 (§9.4). WARP also sits in the path of every Sarvam call: re-measure LLM/STT/TTS latency with WARP connected vs disconnected (`warp-cli disconnect` / `connect`; restore the original state afterwards) and note the result in the runbook so the presenter can decide for the demo.

## 13. Conventions

- **Git:** commit locally after every green gate and at least every 30–45 min. **Never push.** Commit messages are lowercase, terse and human-sloppy ("bot tools + text mode tests", "fix pill morph jank"), with **no Claude/co-author attribution**. `.env` is git-ignored; never print key values in logs, tests or commits.
- Domain words from `CONTEXT.md` everywhere (Ticket, Check, Draft, Monitoring, Shift Brief, Handover, Machine, Unclear Check).
- Python: type hints, small modules, `ruff`. TS: strict, no `any` in app state. No dead code, no TODO placeholders in the demo path.
- Keep `docs/research/` facts current. If you find a doc wrong, fix the doc in the same commit.
