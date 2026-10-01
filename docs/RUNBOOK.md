# KBOS runbook

## Status (written overnight, 2 Oct 2026)

**What works (each verified on the Nothing Phone 2a and/or the headless WebRTC client):**
- People grid → tap a face → shift starts → KB speaks the **Shift Brief** while the ticket cards animate in (critical first, then the overdue Monitoring with its Unclear Check) → the pill opens for follow-ups.
- Voice in English, Hindi and Hinglish, with replies in the user's language (Hindi in Devanagari for the TTS). Tickets are stored in English.
- **Filing by voice:** the Draft card fills live. KB asks "same problem as KB-0141?", asks only for what's missing, offers the in-app camera (photo or Skip), reads back, and files. The ticket gets the telemetry snapshot, the transcript, the photo and the link, and is auto-assigned to the on-shift Maintenance Technician (plus the Supervisor when Critical).
- **Silent live updates:** a ticket assigned to you drops in as a card with a haptic. No speech.
- Query / close / assign by voice. Operators can't close: KB refuses and offers Monitoring. **Unclear Check:** KB asks once, then records it with the amber Unclear badge.
- **End shift → Handover:** KB walks through your touched open tickets, records Checks, ends the shift, shows "Handover recorded" and returns to the grid.
- **Dashboard** at `http://<laptop>:7860/admin`:
  - live over /ws: Tickets with KPIs, the detail sheet with the full story, editing, and status changes that require a Check;
  - Machines with live telemetry and Inject vibration / Clear;
  - Demo: Reset, key pool, sessions and latency;
  - Shifts, Glossary, and the Activity feed.
- **Tests:**
  - `cd backend && uv run pytest -q`: 112 domain/API tests pass.
  - `uv run pytest -m llm tests/test_scenarios.py`: 7 conversation scenarios × 3 runs, 21/21 pass (real LLM, text mode).

**Measured latency** (laptop on campus Wi-Fi + WARP, headless WebRTC client, end of user audio → first KB audio):

| | target | measured |
|---|---|---|
| simple turn (one LLM call) | p50 ≤ 1.5 s | 1.0–1.8 s (typ. 1.45) |
| turn with a tool (two LLM calls) | p50 ≤ 2.3 s | 1.5–2.2 s (typ. 1.85) |
| end of speech → Draft card update | ≤ 1.0 s | 0.85–1.0 s |
| Sarvam STT, speech_end → final transcript | | 0.16–0.3 s |

The last 10 turn breakdowns are at `GET /api/health` (`latency`) and in the app's Settings.

**WARP finding:** with Cloudflare WARP on, Sarvam LLM time-to-first-token is about 0.23 s; with it off, about 0.16 s. TTS first audio is about 0.25 s on and 0.20 s off, and STT is the same either way. WARP costs about 50–70 ms per turn, which is not worth fighting over. If the venue Wi-Fi is flaky with WARP, turn it off (`warp-cli disconnect`).

**Known issues / caveats:**
- **Half-duplex.** While KB is speaking (plus 0.9 s), the mic is ignored. Otherwise the phone's loudspeaker leaks into its mic and KB interrupts itself. To cut KB off, tap the **Stop** button. Speak after KB finishes.
- In a noisy room, speak close to the phone. Sarvam can hallucinate short words on noise.
- Sarvam's gateway intermittently returns HTTP 404. LLM, TTS and STT connects retry automatically. If a turn ever goes silent, tap Stop, then the orb again.
- KB sometimes fills the Draft's "context" from the related ticket (e.g. "after tool change") instead of asking.
- The app's hidden typed input (long-press the pill) is the noisy-venue fallback. Typing Hinglish in Latin letters works, but KB's spoken reply quality is best with real speech.

## Start (fresh terminal)

```bash
cd ~/projects/team/nimbus_hack/kbos
scripts/start.sh --reset      # backend + dashboard on :7860, resets demo data once it's up
```
- The dashboard is at `http://localhost:7860/admin`. Hard-reload it once after any rebuild.
- `start.sh` prints the server URLs the phones can use.
- **Reset the demo** from the dashboard (Demo → Reset demo) or with `curl -X POST localhost:7860/api/demo/reset`. Reset re-seeds relative to *now*. The crew on shift is whoever's shift is current, and the grid switches crews at **06:00** and **20:00** (two hours early, so the incoming crew can log in). **Reset after 06:00** for the 08:00 demo so Ramesh/Kavita/Imran show as "Day · on shift now".

## Phones

- **App:** `app/android/app/build/outputs/apk/release/app-release.apk`. It's a standalone release build, so it needs no Metro.
  - Install with `adb install -r <apk>` (or `scripts/build_apk.sh --release --install` to rebuild).
  - Grant permissions with `adb shell pm grant com.kbos.app android.permission.RECORD_AUDIO` (and `CAMERA`), or accept the prompts.
- **Point the app at the server:** on the people grid, **long-press "KBOS"** to open Settings. Set Server URL to `http://<laptop-ip>:7860`, then tap **Save & test** ("Connected ✓"). The URL is saved on the phone. (You can also long-press your avatar on the home screen.)
  - Over **USB** (`adb reverse tcp:7860 tcp:7860`), `http://localhost:7860` works for HTTP. Voice media still needs real IP reachability (USB tethering or the same Wi-Fi).
- **Demo hotspot (recommended):** put the laptop and the phones on one phone hotspot. Run `ip -4 addr` on the laptop, or read `start.sh`'s list, then enter `http://<hotspot-ip-of-laptop>:7860` in each phone's Settings.
- **Fallbacks:**
  1. USB tethering from a phone. Set that NM connection to `ipv4.never-default yes` so internet stays on Wi-Fi. Use the laptop's tether IP (it was `10.54.52.211` overnight).
  2. Tailscale: laptop `100.101.115.95`. It's relay-only on campus Wi-Fi, so expect extra latency.

## Fallback switches (`.env`, restart the backend after changing)

| switch | default | fallback |
|---|---|---|
| `LLM_PROVIDER` | `sarvam` (sarvam-105b-conversations, 8-key pool, rotates on 401/402/403/429) | `openrouter` (gpt-oss-120b pinned to Groq → Cerebras; key capped at $1, emergencies only) |
| `TTS_PROVIDER` | `sarvam` (bulbul:v3, per-reply hi-IN/en-IN switch) | `gnani` (Timbre v2.5 over SSE, Hinglish voice "Poorvi", language auto; tested, TTFB ≈ 0.2 s) |
| `TTS_VOICE` | `ritu` | any bulbul:v3 voice (`kavya`, `shruti`, `aditya`, …) |
| `STT_MODEL` / `STT_MODE` / `STT_LANGUAGE` | `saaras:v4` / `codemix` / `hi-IN` | see `docs/research/stt-config.md` |
| `IDLE_TIMEOUT_S` | `15` | seconds of silence before the pill closes |

Key pool health is at `GET /api/health` (per key: ok / exhausted / untested) and on the dashboard's Demo tab.

## Demo storyline cheat sheet (PLAN §11)

1. Dashboard on the projector (Tickets). Phone 1 on the grid. Phone 2: Imran logged in.
2. Phone 1: tap **Ramesh**. KB gives the Shift Brief and the cards animate in.
3. Dashboard → Machines → **Inject vibration** on 4B. The card goes into alarm in about 20 s.
4. Ramesh taps the orb: "KB, 4B pe phir se bahut vibration aa raha hai, awaaz bhi aa rahi hai, machine abhi chal rahi hai."
   - KB asks whether it's the same problem as KB-0141: "Haan."
   - "Das minute se."
   - (context) "Tool change ke baad."
   - "Critical, production ruk jayega."
   - Camera: take a photo.
   - "Haan, file kar do."
   - Result: **Filed KB-0142**, linked to KB-0141, assigned to Imran (and Kavita, because it's Critical).
5. Phone 2: the assignment drops in silently. "What's assigned to me?"
6. "Close one-four-two. I replaced the spindle bearing, vibration is back to two millimetres per second." Then: "Close one-four-one too, same root cause."
7. "3C checked." KB asks what was checked. "Bas check kar liya." The Check is recorded with the amber **Unclear** badge.
8. Ramesh taps **End shift**. KB runs the Handover and shows "Handover recorded".
9. Dashboard: open **KB-0141**. The whole story is there.

Speak *after* KB finishes each sentence (half-duplex). Tap **Stop** to cut KB off.
