You're building **KBOS** tonight, autonomously, end to end, for a hackathon presentation at about **08:00 today (Fri 2 Oct 2026)**. It is about 01:00 now and the user is asleep, so don't wait on them. The bar is a polished, bug-free prototype that you have personally seen working on a real phone. Move fast, but never at the expense of correctness in the demo path.

## Read first, in this order
1. `docs/PLAN.md`: the spec. §2 decisions are settled, so don't relitigate them. Follow the milestones in §10 and rehearse the storyline in §11.
2. `CONTEXT.md`: the glossary. Use these exact words in code, UI copy and prompts.
3. `docs/adr/0001…0004`: why the architecture is shaped this way.
4. `docs/research/pipecat.md`, `sarvam.md`, `llm-benchmark.md`. These hold verified API facts for Pipecat 1.12, the Expo client, Sarvam and latency. Read `gnani.md` only if you need the TTS fallback; ignore `laya.md` (rejected).

## Environment (verified at planning time)

**Repo:** `/home/mitran/projects/team/nimbus_hack/kbos`. It holds only docs, `.env` and `.gitignore`, and is not a git repo yet; `git init` it.

**`.env` (never print, log or commit values):**
- `SARVAM_API_KEY_1..8`: all 8 verified working, ₹100 credit each.
- `GNANI_API_KEY`: requires a browser-like `User-Agent` header, or Cloudflare returns 403/1010.
- `OPENROUTER_API_KEY`: works, but has a **$1 cap**, so fallback only.

**Laptop:**
- Fedora with zsh. Your shell prints a harmless zoxide warning; ignore it. `ls` is aliased, so use `command ls`.
- 15 GB RAM with about 9 GB in use, so cap Gradle at `-Xmx3g`.
- About 28 GB disk free. Don't install emulators.
- Node 22, pnpm, uv, JDK 21, Docker.
- **No Android SDK yet**: install cmdline-tools into `~/Android/Sdk` in the background as your very first action.
- Network: campus Wi-Fi + Cloudflare WARP with **UDP blocked**. Tailscale is relay-only.

**Phone:**
- Nothing Phone 2a, Android 16, arm64. On USB as adb serial `00058346R001317`, with stay-awake on and volume up.
- It's on Jio mobile data.
- The user may have enabled **USB tethering**. Check with `ip addr` for a new usb/ncm interface.
  - If tethering is on, set that NetworkManager connection to `ipv4.never-default yes` so the laptop's internet stays on Wi-Fi, and use the tether subnet for WebRTC.
  - If it's off, use Tailscale (phone `100.67.152.63`, laptop `100.101.115.95`). It's relay-only and slower, so mention it in the runbook.
  - Always `adb reverse` ports 8081 and 7860.

## Skills to load when you reach that part
- `expo:expo-overview` **before any Expo work**. It routes you to `expo-router`, `expo-project-structure`, `expo-dev-client` and the rest. Build locally with Gradle; **don't use EAS**.
- `animate-expo` / `expo:expo-animation`, `emil-design-eng` and `apple-design` for the app's motion and polish. The look is light and calm, Siri/ChatGPT-voice style (PLAN §7.3).
- `frontend-design:frontend-design`, `dataviz` and `ask-sonner` for the dashboard.
- `code-review` at medium effort on the demo path before feature-freeze. Fix what it finds.

## How to work
- **The M1 gate comes first.** Hear KB answer a Hindi and an English question **on the phone** over WebRTC to the laptop before building any UI polish. This is the riskiest integration (Expo SDK 55 + RN SmallWebRTC transport + our own FastAPI app hosting the Pipecat offer endpoints + phone↔laptop reachability).
- **Parallelize** independent work with subagents. The dashboard is a good candidate once the M2 API contract is frozen, and so are backend tests and test-audio generation. Keep integration, the voice bot and the app's core flows in your own hands.
- **Verify everything yourself. Never report something as working without seeing it work:**
  - pytest for the domain and API;
  - text-mode conversation scenarios, each run 3× (PLAN §9.2);
  - the headless voice e2e client;
  - on device: install with `adb install -r`, drive with `adb shell input`, check with `adb exec-out screencap -p` screenshots that you look at, and feed voice by playing generated WAVs through the laptop speakers next to the phone;
  - Playwright for the dashboard.
- **Latency is a feature.** Log the per-turn breakdown (`UserBotLatencyObserver`) and hit the PLAN §6.6 targets. Measure before and after each tuning change.
- **Spend credits sensibly.**
  - Use text mode for conversation logic.
  - Use real voice sparingly.
  - The STT gate must stop Sarvam STT billing while the orb is idle.
  - The key pool rotates on 401/402/403/429.
- **Git:** commit locally at every green gate and at least every 30–45 min. **Never push.** Messages are lowercase, terse and human-sloppy (e.g. `bot tools + text mode tests`), with **no Claude/co-author attribution**.
- **If you hit something only the user can do**, work around it (USB tether → Tailscale → adb reverse → text mode) and record it in the runbook. Don't stop.
- **Feature-freeze at 06:30.** Then rehearse the PLAN §11 storyline twice on the phone + dashboard (plus a second simulated user), fix anything that wobbles, and write `docs/RUNBOOK.md` + `scripts/start.sh` (M7).
- **End state:**
  - backend running and serving `/admin`;
  - APK installed, app on the people grid;
  - demo freshly reset;
  - everything committed.
  - At the top of `docs/RUNBOOK.md`, a short status: what works, known issues, measured latencies, which env switches flip to the fallbacks (LLM → OpenRouter, TTS → Gnani), how to point the app at a new server IP on the demo hotspot, and the WARP on/off latency finding.
