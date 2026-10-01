# Pipecat as the real-time voice framework for KBOS: research notes

Researched 2026-10-01. Primary sources: Pipecat source on `main` (pipecat-ai/pipecat, which ships as **v1.12.0**, released 2026-09-26), docs.pipecat.ai (fetched as `.md`), `pipecat-client-react-native-transports`, `pipecat-client-web`, `pipecat-examples`, `smart-turn`, PyPI and the npm registry. The Daily Expo config plugin README, Cloudflare Realtime TURN docs, Tailscale KB and Expo docs fill in the gaps. Claims marked **[inference]** are mine and no source states them. Nothing here was run on a device.

Scope assumptions (settled by the team): Python backend on a Linux laptop (RTX 4060 8 GB). **Android-only** Expo **dev build**, sideloaded as an APK, so no Expo Go and no iOS. Several phones connect at once. The LLM is Groq, a free OpenRouter model, or `sarvam-105b-conversations`. Sarvam and Gnani service details live in [`sarvam.md`](./sarvam.md) and [`gnani.md`](./gnani.md) and aren't repeated here.

## TL;DR

- **Server:** `pipecat-ai==1.12.0`, Python **>= 3.11** (CI tests 3.11–3.14; 3.12+ recommended). Install `uv add "pipecat-ai[runner,webrtc,silero,groq,sarvam]"` (add `openrouter` and/or `google` as needed). Silero VAD and Smart Turn v3.2 ship in the core package.
- **The 1.x API has moved on from older tutorials.** `PipelineTask` is deprecated (since 1.3.0) in favour of `PipelineWorker` + `WorkerRunner` (`pipecat.workers.runner`). Tools are plain async functions passed as `LLMContext(tools=[...])`. Services take `settings=XService.Settings(...)`. **RTVI is on by default:** `PipelineWorker` adds the `RTVIProcessor` and `RTVIObserver` itself, and you reach them through `worker.rtvi`.
- **RN client (exact versions):** `@pipecat-ai/client-js@1.13.1` + `@pipecat-ai/react-native-small-webrtc-transport@1.8.0` + `@pipecat-ai/react-native-daily-media-manager@0.0.2`. Native peers: `@daily-co/react-native-webrtc@124.0.6-daily.2`, `@daily-co/react-native-daily-js@^0.86.0`, `@react-native-async-storage/async-storage@3.1.1`, `react-native-background-timer@^2.4.1`, `react-native-get-random-values@^1.11.0`. Expo config plugin `@daily-co/config-plugin-rn-daily-js@0.0.12` + `expo-build-properties`. **Don't use `@pipecat-ai/client-react`.** Its peers include `react-dom` and it is web-only; the official RN examples use `client-js` directly.
- **Expo is pinned to SDK 55.** The config plugin 0.0.12 declares `peerDependencies: { expo: "^55.0.0" }` and is the newest release. Latest Expo is SDK 57, so **start the app on SDK 55** (all official RN examples use `expo ~55.0.26`, `react-native 0.83.4`, `react 19.2.4`, new architecture on). Expo Go is explicitly not supported; you need a dev build (`npx expo prebuild` + `expo run:android`, or EAS).
- **Recommended transport: SmallWebRTC (P2P) from each phone straight to the laptop.** It needs no account and gives the lowest latency on a LAN. The dev runner already does per-phone sessions. On hostile Wi-Fi (client isolation, UDP blocked), use, in order: **(1)** your own hotspot or travel router as the demo network, **(2)** Tailscale on the phones (the Android app is supported) and point the app at the laptop's `100.x` address, or **(3)** a Cloudflare Tunnel for the HTTP signalling **plus** a TURN server (Cloudflare Realtime TURN, 1,000 GB free) for media. **Daily** is the managed fallback (10,000 free min/month, needs `DAILY_API_KEY`) and goes over the internet twice. **WebSocket** is not an option for RN: no RN WebSocket transport package exists, and Pipecat's docs say not to use WebSocket for client voice.
- **UI live-update channel:** server → client uses `await worker.rtvi.send_server_message({...})` (or push `RTVIServerMessageFrame(data=...)`), and the client receives `callbacks.onServerMessage(data)`. Function calls also surface automatically as `onLLMFunctionCallStarted / InProgress / Stopped`, but the default report level is `NONE` (only `tool_call_id`). Set `RTVIObserverParams(function_call_report_level={"update_ticket": RTVIFunctionCallReportLevel.FULL})` to get the name, args and result. Client → server uses `client.sendClientMessage(type, data)` (fire-and-forget) or `await client.sendClientRequest(type, data)` (awaits `rtvi.send_server_response`). The server handles both in `@worker.rtvi.event_handler("on_client_message")`. Don't send photos over the data channel (the RN transport caps messages at 64 KB). Upload them over HTTP to a custom runner route, then send a client message with the ID.
- **Turn-taking:** the defaults are Silero VAD (`stop_secs=0.2`) plus **Smart Turn v3.2** (`LocalSmartTurnAnalyzerV3`, bundled ONNX, CPU 10–100 ms). Smart Turn supports 23 languages, including **Hindi, Bengali and Marathi**, but **not** Tamil, Telugu, Kannada, Malayalam, Gujarati, Punjabi or Odia. For those, use `SpeechTimeoutUserTurnStopStrategy` or Sarvam's server-side endpointing. Interruptions are on by default. Idle detection is `user_idle_timeout` plus `on_user_turn_idle`. Measure with `UserBotLatencyObserver` (`on_latency_breakdown`).
- **LLM services with first-class tool calling:** `GroqLLMService` (`pipecat-ai[groq]`), `OpenRouterLLMService` (`pipecat-ai[openrouter]`) and `SarvamLLMService` (`pipecat-ai[sarvam]`; `sarvam-105b-conversations` is the one that avoids the whitelisted `/v2`, see sarvam.md). All are OpenAI-compatible subclasses with function-calling examples in the repo.
- **Blockers / gotchas:** (1) Expo SDK 55 pin. (2) Run the runner with `--host 0.0.0.0`; it binds `localhost` by default. (3) An Android release APK pointed at an `http://` backend needs `usesCleartextTraffic: true` (via `expo-build-properties`). (4) Without `--ice-servers`, the bot gathers host candidates only, so off-LAN connections need STUN/TURN on **both** sides. (5) aiortc uses only **one** STUN and **one** TURN URL per connection. (6) The dev runner is a single unauthenticated process, which is fine for a demo and not something to leave on a public URL.

---

## 1. Server package: version, Python, extras

| Fact | Value | Source |
|---|---|---|
| Latest `pipecat-ai` | **1.12.0**, uploaded 2026-09-26. Cadence is about weekly (1.9.0 on 09-11, 1.10.0 on 09-12, 1.11.0 on 09-18). | [PyPI JSON](https://pypi.org/pypi/pipecat-ai/json) |
| Python | `requires_python >=3.11`; README: "Minimum 3.11, recommended >= 3.12". The compatibility CI matrix is 3.11.15, 3.12.13, 3.13.12, 3.14.3. | [pyproject.toml](https://github.com/pipecat-ai/pipecat/blob/main/pyproject.toml), [README](https://github.com/pipecat-ai/pipecat/blob/main/README.md), [python-compatibility.yaml](https://github.com/pipecat-ai/pipecat/blob/main/.github/workflows/python-compatibility.yaml) |
| Core deps include | `onnxruntime~=1.24.3` ("Required by LocalSmartTurnAnalyzerV3"), `openai`, `numpy`, `websockets`, `pydantic` | pyproject.toml |
| Extras relevant to us | `runner` (uvicorn, fastapi, `pipecat-ai-prebuilt>=1.2.2`), `webrtc` (`aiortc>=1.14.0,<2`, opencv-headless), `webrtc-video`, `websocket`, `daily`, `silero` (empty: Silero is in core), `groq`, `openrouter`, `sarvam` (`sarvamai==0.1.28`), `google`, `anthropic`, `local-smart-turn` (torch/transformers, **not needed** for the default ONNX v3 analyzer) | pyproject.toml; 53 extras in total per PyPI |

Suggested install (**[inference]**, assembled from the extras above):

```bash
uv add "pipecat-ai[runner,webrtc,silero,groq,openrouter,sarvam]==1.12.0" python-dotenv
# Gnani is a community package: uv add pipecat-gnani   (see gnani.md)
```

### API shape in 1.x (it differs from most blog posts)

- `pipecat.pipeline.task.PipelineTask` is a deprecated shim ("Import from `pipecat.pipeline.worker` instead", since 1.3.0). Use `PipelineWorker(pipeline, params=PipelineParams(...))` and `WorkerRunner(handle_sigint=...)` from `pipecat.workers.runner`. Source: [`pipeline/task.py`](https://github.com/pipecat-ai/pipecat/blob/main/src/pipecat/pipeline/task.py), [`examples/getting-started/07-function-calling.py`](https://github.com/pipecat-ai/pipecat/blob/main/examples/getting-started/07-function-calling.py).
- VAD moved off the transport. It now goes on the user aggregator: `LLMContextAggregatorPair(context, user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()))`. Source: [Speech Input & Turn Detection](https://docs.pipecat.ai/pipecat/learn/speech-input.md).
- Tools are direct functions whose docstrings become the schema: `async def f(params: FunctionCallParams, arg: str)`, passed as `LLMContext(tools=[f])`. Per-tool options come from `@tool_options(cancel_on_interruption=..., timeout_secs=...)`. Source: [Function Calling](https://docs.pipecat.ai/pipecat/learn/function-calling.md).
- `FunctionCallParams` carries `pipeline_worker`, `app_resources` (per-session state you pass as `PipelineWorker(..., app_resources=...)`), `llm`, `context`, `result_callback` and `worker_runner`. Source: [`services/llm_service.py`](https://github.com/pipecat-ai/pipecat/blob/main/src/pipecat/services/llm_service.py).

---

## 2. React Native / Expo client

### Packages that exist (npm registry, checked 2026-10-01)

| Package | Latest | Published | Notes |
|---|---|---|---|
| `@pipecat-ai/client-js` | **1.13.1** | 2026-09-04 | Core `PipecatClient`. RTVI protocol `2.1.0` (`RTVI_PROTOCOL_VERSION` in `rtvi/messages.ts`), which matches the server's `PROTOCOL_VERSION = "2.1.0"`. |
| `@pipecat-ai/react-native-small-webrtc-transport` | **1.8.0** | 2026-06-22 | `RNSmallWebRTCTransport`. deps: `client-js ^1.12.0`, `lodash`. peers: `@daily-co/react-native-webrtc ^124.0.6-daily.2`, `react-native *`. |
| `@pipecat-ai/react-native-daily-media-manager` | **0.0.2** | 2026-06-22 | `DailyMediaManager`, the required `mediaManager` for the SmallWebRTC RN transport (device handling, mic, speakerphone). peers: `react-native-daily-js ^0.86.0`, `react-native-webrtc ^124.0.6-daily.2`, `async-storage ^3.1.1`, `react-native-background-timer ^2.4.1`, `react-native-get-random-values ^1.11.0`. |
| `@pipecat-ai/react-native-daily-transport` | **1.8.0** | 2026-06-22 | `RNDailyTransport`. Same native peers as above. |
| `@pipecat-ai/client-react` | 1.8.2 | 2026-08-25 | **Web.** peers `react-dom >=18`, `@pipecat-ai/client-js *`. `PipecatClientAudio`/`PipecatClientVideo` touch the DOM. The RN examples don't use it. **[inference]:** skip it on RN and write a small context or hook around `client-js`, as the examples do. |
| `@pipecat-ai/small-webrtc-transport`, `@pipecat-ai/daily-transport`, `@pipecat-ai/websocket-transport` | 1.10.8 / 1.6.9 / 1.7.2 | 2026-09-15 | **Web-only** transports. They depend on `@daily-co/daily-js` (browser). |
| `@pipecat-ai/react-native-websocket-transport`, `@pipecat-ai/client-react-native` | **do not exist** (404) | | No RN WebSocket transport is published. |

Sources: [npm registry](https://registry.npmjs.org/@pipecat-ai/react-native-small-webrtc-transport); [pipecat-client-react-native-transports](https://github.com/pipecat-ai/pipecat-client-react-native-transports) (README, `transports/*/README.md`, `CHANGELOG.md`); [pipecat-client-web](https://github.com/pipecat-ai/pipecat-client-web).

RN transport 1.8.0 changelog: support for RTVI 2.0 `bot-output` (`will_be_spoken`, `spoken_status`, `spoken_progress`, `segment_id` for word-level karaoke captions) and the `onUnsupportedFeature` callback. 1.6.0 added the `llm-function-call-started/in-progress/stopped` events and set the max message size (`MessageTooLargeError`). The RN SmallWebRTC transport hard-codes `_maxMessageSize = 64 * 1024` because "react-native-webrtc does not expose `sctp.maxMessageSize`" (`transports/smallwebrtc/src/transport.ts`).

Platform minimums (transport README): **Android `minSdkVersion` >= 24**, iOS >= 15.

### Expo requirements (verified)

- Expo Go isn't supported, as the RN transport examples and the Daily plugin README both state: "This project cannot be used with an Expo Go app because it requires custom native code… transition… to a development build." Sources: [`examples/smallwebrtc/README.md`](https://github.com/pipecat-ai/pipecat-client-react-native-transports/blob/main/examples/smallwebrtc/README.md), [rn-daily-js-expo-config-plugin](https://github.com/daily-co/rn-daily-js-expo-config-plugin).
- Config plugin: `@daily-co/config-plugin-rn-daily-js@0.0.12` (latest). Its own `peerDependencies` are `expo ^55.0.0` and its deps are `expo-build-properties ~55.0.11` and `@expo/config-plugins ^55.0.7`. The plugin README's compatibility table lists Expo 55.x with react-native-webrtc `124.0.6-daily.1`, react-native-daily-js `0.84.1` and plugin `0.0.12`. Nothing newer exists. **Latest Expo is 57.0.26** (dist-tags), so **use SDK 55** (`expo@~55.0.31`, the latest `sdk-55` tag). Going above 55 means peer-dep overrides and unknown native breakage **[inference]**.
- `app.json` used by both official RN examples (Android-relevant parts):

```json
{
  "expo": {
    "newArchEnabled": true,
    "android": {
      "package": "com.yourteam.kbos",
      "permissions": [
        "android.permission.ACCESS_NETWORK_STATE", "android.permission.BLUETOOTH",
        "android.permission.INTERNET", "android.permission.MODIFY_AUDIO_SETTINGS",
        "android.permission.RECORD_AUDIO", "android.permission.WAKE_LOCK",
        "android.permission.FOREGROUND_SERVICE", "android.permission.FOREGROUND_SERVICE_MICROPHONE",
        "android.permission.POST_NOTIFICATIONS"
      ]
    },
    "plugins": [
      "@daily-co/config-plugin-rn-daily-js",
      ["expo-build-properties", {
        "android": { "minSdkVersion": 24, "usesCleartextTraffic": true }
      }]
    ]
  }
}
```

  `usesCleartextTraffic` is my addition. Expo's docs say it defaults to `false` on Android 9+, so a **release** APK can't reach `http://192.168.x.x:7860` without it ([expo-build-properties](https://docs.expo.dev/versions/latest/sdk/build-properties/)). The examples also list camera and media-projection permissions, which an audio-only app can drop **[inference]**.
- The example `package.json` adds `"resolutions": { "@daily-co/react-native-webrtc/debug": "^4.0.0" }` and its `index.js` calls `debug.disable('rn-webrtc:*')` and ignores two `NativeEventEmitter` LogBox warnings from `react-native-background-timer`. Copy both.
- Build: `npx expo prebuild` then `npx expo run:android --device`, or EAS. The scripts use `expo start --dev-client`.

### Official examples to copy from

| Example | Transport | What it shows |
|---|---|---|
| [`pipecat-examples/p2p-webrtc/video-transform/client/react-native`](https://github.com/pipecat-ai/pipecat-examples/tree/main/p2p-webrtc/video-transform/client/react-native) + `server/bot.py` | SmallWebRTC | **Closest to our stack.** Expo 55 app with a `VoiceClientContext` provider (`src/context/VoiceClientContext.tsx`), live chat transcript from `onUserTranscript` and `onBotOutput`, `onServerMessage`, mic/cam toggles. The server is Gemini Live on the dev runner. |
| [`pipecat-examples/simple-chatbot/client/react-native`](https://github.com/pipecat-ai/pipecat-examples/tree/main/simple-chatbot/client/react-native) | Daily | Same UI structure on `RNDailyTransport`. |
| [`pipecat-examples/bot-ready-signalling/client/react-native`](https://github.com/pipecat-ai/pipecat-examples/tree/main/bot-ready-signalling/client/react-native) | Daily | Bot-ready handshake. |
| [`pipecat-client-react-native-transports/examples/smallwebrtc`](https://github.com/pipecat-ai/pipecat-client-react-native-transports/tree/main/examples/smallwebrtc) | SmallWebRTC | Minimal single-file `App.tsx` (monorepo-linked, so copy the code, not the metro config). |

### RN client connect flow (snippet b)

The flow follows `VoiceClientContext.tsx` from the example and the `client-js` source. `startBotAndConnect` POSTs to `/start`. The runner returns `{sessionId, iceConfig?}`, and the RN transport then POSTs the SDP offer to `/start` with `/start` rewritten to `/sessions/{sessionId}/api/offer` (`_buildRequestParamsBasedOnStartBotParams` in `transport.ts`), trickling ICE via `PATCH`.

```tsx
import { PipecatClient, RTVIEvent } from '@pipecat-ai/client-js';
import { RNSmallWebRTCTransport } from '@pipecat-ai/react-native-small-webrtc-transport';
import { DailyMediaManager } from '@pipecat-ai/react-native-daily-media-manager';

const BASE_URL = process.env.EXPO_PUBLIC_BASE_URL!; // e.g. http://192.168.43.10:7860 or http://100.101.102.103:7860

export async function connectVoice(deviceId: string, onTicket: (t: any) => void) {
  const client = new PipecatClient({
    transport: new RNSmallWebRTCTransport({
      mediaManager: new DailyMediaManager(),
      // iceServers: [...]   // optional; the runner's /start response can also supply iceConfig
    }),
    enableMic: true,
    enableCam: false,
    callbacks: {
      onConnected: () => client.updateMic('SPEAKERPHONE'),  // route bot audio to loudspeaker (as in the examples)
      onBotReady: () => console.log('bot ready'),
      onUserTranscript: (t) => { if (t.final) console.log('user:', t.text); },
      onBotOutput: (o) => { /* sentence/word captions; see VoiceClientContext.tsx */ },
      // Payload is exactly what the server passed to send_server_message()
      onServerMessage: (data: any) => { if (data?.type === 'ticket_update') onTicket(data.ticket); },
      // Auto-emitted by the server's RTVIObserver; fields depend on function_call_report_level
      onLLMFunctionCallStarted: (d) => console.log('tool started', d.function_name),
      onLLMFunctionCallInProgress: (d) => console.log('tool args', d.function_name, d.arguments),
      onLLMFunctionCallStopped: (d) => console.log('tool result', d.function_name, d.result, d.cancelled),
      onError: (e) => console.warn('pipecat error', e),
    },
  });

  await client.initDevices();
  await client.startBotAndConnect({
    endpoint: `${BASE_URL}/start`,
    requestData: {
      transport: 'webrtc',
      enableDefaultIceServers: false, // true => runner returns Google STUN (only if runner has no --ice-servers)
      body: { deviceId },             // becomes runner_args.body in bot()
    },
  });
  return client;
}

// Mid-conversation, client -> server:
//   client.sendClientMessage('photo_uploaded', { photoId });           // fire-and-forget
//   const t = await client.sendClientRequest('get_ticket', {}, 5000);  // awaits rtvi.send_server_response()
//   await client.sendText('Category is plumbing', { run_immediately: true, audio_response: true });
//   await client.disconnect();
```

Notes:
- `onServerMessage` and `client.on(RTVIEvent.ServerMessage, …)` both receive `ev.data`, the raw payload (`client.ts`, the `SERVER_MESSAGE` case). The docs' RN snippet reads `message.data.msg`, which doesn't match the source. Log the first message to confirm the shape.
- `requestData.body` reaches the bot as `runner_args.body`. The runner stores `request_data["body"]` against the session id, and the `/sessions/{id}/api/offer` proxy forwards it (`runner/run.py`, `proxy_request`). That's the per-phone identity hook.

---

## 3. Transport trade-offs for phones to a laptop on unknown Wi-Fi

### What the docs say (verified)

- [Choosing a Transport](https://docs.pipecat.ai/client/concepts/choosing-a-transport.md) says: "For any client-to-server voice application, **WebRTC is the right choice**." It lists the problems with WebSocket: TCP head-of-line blocking, Opus FEC/PLC built for UDP, no jitter buffer, no AEC, and hard mobile reconnects. "**Do not use it for browser-to-server voice interactions.**" Recommendation: "if you're self-hosting, use SmallWebRTC". Daily is "recommended for production" for users "on degraded networks… or on mobile".
- [Small WebRTC Transport](https://docs.pipecat.ai/api-reference/server/services/transport/small-webrtc.md) ICE table: same LAN needs no STUN and no TURN. Different networks (Linux) need STUN, and TURN "usually not". Strict NAT needs TURN. "Without either [`--ice-servers` or `enableDefaultIceServers`], the bot gathers host candidates only."
- The same page documents `PIPECAT_SCTP_MAX_CHUNK_SIZE` (default **1100**), which keeps data-channel datagrams under the **1280-byte MTU of "Tailscale overlays"** and VPNs. The default already handles Tailscale.
- RN transport README: SmallWebRTC is "the simplest low-latency audio/video transport… recommended for local development and demos". One client per bot process connection; multiple *sessions* are fine (see §7).

### Comparison for our demo

| | SmallWebRTC (P2P) | Daily (cloud SFU) | WebSocket |
|---|---|---|---|
| RN package | `@pipecat-ai/react-native-small-webrtc-transport` 1.8.0 | `@pipecat-ai/react-native-daily-transport` 1.8.0 | **none for RN** |
| Account / key | none | `DAILY_API_KEY`; the runner creates rooms (`pipecat.runner.daily.configure`) | none |
| Free tier | n/a | "10,000 free minutes/month" ([daily.co/pricing](https://www.daily.co/pricing/)) | n/a |
| Media path | phone → laptop directly (LAN or tailnet), UDP | phone → Daily PoP → internet → laptop bot (the bot joins the room from the laptop) | TCP |
| Latency on LAN | lowest, a few ms network **[inference]** | adds two internet hops, India PoP to laptop uplink **[inference]** | worst under loss |
| Restrictive Wi-Fi | fails if AP client-isolation blocks phone ↔ laptop, or UDP is blocked, unless TURN/Tailscale/hotspot | most robust. Daily runs its own global TURN/relay **[inference: not verified in this session]** | would traverse a Cloudflare Tunnel (HTTP upgrade) **[inference]**, but there's no RN client |
| Server extra | `pipecat-ai[webrtc]` (aiortc) | `pipecat-ai[daily]` | `pipecat-ai[websocket]` |

### Network options, in order of preference

1. **Bring your own network (strongly recommended) [inference].** Put the laptop and demo phones on a dedicated hotspot or travel router. Plain SmallWebRTC then works with host candidates only: no STUN, no TURN, no internet path for media. The cloud STT/LLM/TTS calls still go out through the hotspot's uplink.
2. **Tailscale on the phones.** The Android client is supported on "Android 8.0 or later", installed from Google Play ([Tailscale KB 1079](https://tailscale.com/kb/1079/install-android)). The phone app points at `http://<laptop-tailscale-ip-or-MagicDNS>:7860`. aiortc advertises host candidates on all interfaces, including `tailscale0` **[inference]**. When a direct path is impossible, Tailscale falls back to DERP relays, and Tailscale runs DERP servers in **Bengaluru** ([Tailscale KB 1232](https://tailscale.com/kb/1232/derp-servers)). DERP traffic goes over HTTPS/443, which gets through most captive Wi-Fi **[inference: well known, not fetched here]**. Caveats: one tailnet login per phone (or a shared account), and the WireGuard overhead and DERP hop add latency when relayed **[inference]**. **Test the WebRTC-over-Tailscale ICE path on one phone early.** The Android VPN interface plus ICE candidate pairing is the part I couldn't verify.
3. **Cloudflare Tunnel + TURN.** A tunnel (`cloudflared`) only carries HTTP(S) and WebSockets, so it can carry `/start` and `/api/offer` signalling but **not** WebRTC UDP media **[inference]**. Media then needs a TURN relay both ends can reach. Cloudflare Realtime TURN offers `turn:turn.cloudflare.com:3478?transport=udp|tcp`, `:443?transport=udp`, `:80?transport=tcp`, and `turns:turn.cloudflare.com:5349|443?transport=tcp`. Pricing is "$0.05 per GB… free tier of 1,000 GB", and STUN at `stun.cloudflare.com` is free ([CF TURN](https://developers.cloudflare.com/realtime/turn/), [FAQ](https://developers.cloudflare.com/realtime/turn/faq/)). Credentials are short-lived and come from `POST https://rtc.live.cloudflare.com/v1/turn/keys/$TURN_KEY_ID/credentials/generate-ice-servers` with `{"ttl": 86400}` ([Generate credentials](https://developers.cloudflare.com/realtime/turn/generate-credentials/)).
4. **Daily.** Switch to `RNDailyTransport` and `DailyTransport` on the server. The client code otherwise stays the same, since transports are swappable by design (Choosing a Transport, "Swapping transports").

### Configuring ICE servers (SmallWebRTC)

- **Server (dev runner):** `python bot.py -t webrtc --host 0.0.0.0 --ice-servers stun:stun.cloudflare.com:3478 '{"urls": "turn:turn.cloudflare.com:3478?transport=udp", "username": "...", "credential": "..."}'`, or set `PIPECAT_ICE_SERVERS` (comma-separated or a JSON array). The runner uses these servers for the bot's own `SmallWebRTCConnection` **and returns them to the client** as `iceConfig` in the `/start` response, so both peers share the same servers. They take precedence over `enableDefaultIceServers`, which only adds Google STUN ([runner `run.py`](https://github.com/pipecat-ai/pipecat/blob/main/src/pipecat/runner/run.py), `/start` handler).
- **Client:** the RN transport accepts `iceServers` in its constructor or `iceConfig.iceServers` in connect params, and the server's `iceConfig` overrides them (`transport.ts`, `_connect`).
- **aiortc limitation (verified in source):** `connection_kwargs()` keeps **only the first STUN URL and the first TURN URL**. Supported TURN schemes are `turn:` with `transport=udp|tcp` and `turns:` with `transport=tcp`, password credentials only ([aiortc `rtcicetransport.py`](https://github.com/aiortc/aiortc/blob/main/src/aiortc/rtcicetransport.py)). Pass the bot a single sensible TURN URL. The phone (libwebrtc) can take the full list, including `turns:…:443` **[inference]**.
- `enableDefaultIceServers: true` in the RN example's `requestData` returns Google STUN only when the runner has no `--ice-servers`.

---

## 4. RTVI: live UI updates and client messages (1.x API)

RTVI is the JSON protocol on the WebRTC data channel (label `"rtvi-ai"`, protocol **2.1.0** on both ends). `PipelineWorker` turns it on automatically: `enable_rtvi=None` defaults to on, and it prepends an `RTVIProcessor`, attaches `RTVIObserver`, and auto-replies `bot-ready` on `client-ready`. Use `worker.rtvi` to reach the processor, and pass `rtvi_observer_params=` to configure the observer. Don't add your own `RTVIProcessor` as well, or you'll get a warning about duplicates ([`pipeline/worker.py`](https://github.com/pipecat-ai/pipecat/blob/main/src/pipecat/pipeline/worker.py)).

### Server → client

| Mechanism | API | Client side |
|---|---|---|
| Custom push | `await worker.rtvi.send_server_message(data)`, or push `RTVIServerMessageFrame(data=...)` from any processor (the observer converts it) | `onServerMessage(data)` / `RTVIEvent.ServerMessage` |
| Reply to a client request | `await rtvi.send_server_response(msg, data)` / `send_error_response(msg, "...")`, or push `RTVIServerResponseFrame(client_msg=frame, data=...)` | resolves `await client.sendClientRequest(...)` |
| Function-call lifecycle (automatic) | `RTVIObserver` emits `llm-function-call-started`, `-in-progress`, and `-stopped` (with `result`, `cancelled`) from `FunctionCallsStartedFrame`, `FunctionCallInProgressFrame`, `FunctionCallResultFrame` and `FunctionCallCancelFrame` | `onLLMFunctionCallStarted/InProgress/Stopped` (`LLMFunctionCallStoppedData = {function_name?, tool_call_id, cancelled, result?}`) |
| Report-level gate | `RTVIObserverParams(function_call_report_level={"*": NONE, "update_ticket": FULL})`. Levels are `DISABLED, NONE, NAME, ARGUMENTS, FULL`; the **default is `{"*": NONE}`** (only `tool_call_id`) | |
| Transcripts and captions | automatic: `user-transcription`, `bot-output` (sentence and word level, with `spoken_progress`), `user/bot-started/stopped-speaking`, `metrics` (if `enable_metrics`) | `onUserTranscript`, `onBotOutput`, `onMetrics`, … |

Sources: [`processors/frameworks/rtvi/processor.py`](https://github.com/pipecat-ai/pipecat/blob/main/src/pipecat/processors/frameworks/rtvi/processor.py), [`observer.py`](https://github.com/pipecat-ai/pipecat/blob/main/src/pipecat/processors/frameworks/rtvi/observer.py), [Custom Messaging guide](https://docs.pipecat.ai/client/guides/custom-messaging.md), [`client-js/client/client.ts`](https://github.com/pipecat-ai/pipecat-client-web/blob/main/client-js/client/client.ts).

**Ticket-form pattern [inference]:** have the tool handler mutate per-session state (`params.app_resources`) and call `send_server_message({"type": "ticket_update", "ticket": {...}})`. That gives the UI one authoritative state snapshot per change, independent of the report level. Use the function-call events only for "thinking…" spinners.

### Client → server

| Client | Server |
|---|---|
| `client.sendClientMessage(type, data)` | `@worker.rtvi.event_handler("on_client_message") async def h(rtvi, msg)`, where `msg.type`, `msg.data`, `msg.msg_id` (`RTVI.ClientMessage`); or catch `RTVIClientMessageFrame(msg_id, type, data)` in a `FrameProcessor` |
| `await client.sendClientRequest(type, data, timeoutMs?)` | same handler, then `await rtvi.send_server_response(msg, {...})` |
| `await client.sendText(text, {run_immediately, audio_response})` | built-in: appends a user message (`LLMMessagesAppendFrame`), optionally interrupting the bot and running the LLM |
| `requestData.body` on `startBotAndConnect` | `runner_args.body` at session start |

To make the LLM react to a client event (e.g. a photo upload), queue `LLMMessagesAppendFrame([{"role": "developer", "content": "..."}], run_llm=True)` on the worker. That's the same pattern the idle-detection docs use.

**Photos:** data-channel messages are capped at 64 KB on the RN transport, and aiortc chunks SCTP at 1100 B. Add an HTTP route to the runner's FastAPI app (`from pipecat.runner.run import app`; the docs show `@app.get("/healthz")` added before `main()`, see [Running Bots Locally](https://docs.pipecat.ai/pipecat/deployment/running-bots-locally.md)). POST the image there, then `sendClientMessage('photo_uploaded', {photoId})`. The `/upload` route below is my addition, not a Pipecat API.

### Snippet (a): server bot with function calling + RTVI server messages + client messages

Every import path below was checked against `main` (1.12.0). Service choices follow the team's settled options. Constructor details for Sarvam are in sarvam.md.

```python
# bot.py  — run: uv run bot.py -t webrtc --host 0.0.0.0
import os
import uuid

from dotenv import load_dotenv
from fastapi import UploadFile
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMMessagesAppendFrame, LLMRunFrame
from pipecat.observers.user_bot_latency_observer import UserBotLatencyObserver
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frameworks.rtvi import RTVIFunctionCallReportLevel, RTVIObserverParams
from pipecat.runner.run import app  # the dev runner's FastAPI app; add routes before main()
from pipecat.runner.types import RunnerArguments
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.sarvam.stt import SarvamSTTService
from pipecat.services.sarvam.tts import SarvamTTSService
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.workers.runner import WorkerRunner

load_dotenv(override=True)
UPLOADS: dict[str, bytes] = {}


@app.post("/upload")  # custom route (not a Pipecat API) — photos go over HTTP, not the data channel
async def upload(file: UploadFile):
    photo_id = uuid.uuid4().hex
    UPLOADS[photo_id] = await file.read()
    return {"photoId": photo_id}


async def update_ticket(params: FunctionCallParams, field: str, value: str):
    """Record one field of the user's complaint ticket as soon as you learn it.

    Args:
        field: One of "category", "location", "description", "urgency", "contact".
        value: The value the user gave, normalised to English.
    """
    ticket = params.app_resources["ticket"]  # per-session dict passed via PipelineWorker(app_resources=...)
    ticket[field] = value
    # Push authoritative state to the phone UI (arrives in onServerMessage)
    await params.pipeline_worker.rtvi.send_server_message({"type": "ticket_update", "ticket": ticket})
    await params.result_callback({"ok": True, "ticket": ticket})


async def bot(runner_args: RunnerArguments):
    transport = SmallWebRTCTransport(
        webrtc_connection=runner_args.webrtc_connection,
        params=TransportParams(audio_in_enabled=True, audio_out_enabled=True, audio_out_10ms_chunks=2),
    )
    device_id = (runner_args.body or {}).get("deviceId", "unknown")
    state = {"ticket": {}, "device_id": device_id}

    stt = SarvamSTTService(
        api_key=os.environ["SARVAM_API_KEY"],
        settings=SarvamSTTService.Settings(model="saaras:v4", language=Language.HI_IN),
    )
    llm = GroqLLMService(
        api_key=os.environ["GROQ_API_KEY"],
        settings=GroqLLMService.Settings(
            model="openai/gpt-oss-120b",  # model used in Pipecat's Groq docs; pick per latency tests
            system_instruction="You are a concise voice assistant filing a civic complaint ticket. "
            "Call update_ticket every time you learn a field. Speak briefly, no markdown.",
        ),
    )
    tts = SarvamTTSService(
        api_key=os.environ["SARVAM_API_KEY"],
        settings=SarvamTTSService.Settings(model="bulbul:v3", voice="shubh", language=Language.HI_IN),
    )

    context = LLMContext(tools=[update_ticket])
    user_agg, assistant_agg = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),  # default stop_secs=0.2; Smart Turn v3 is the default stop strategy
            user_idle_timeout=8.0,
        ),
    )

    pipeline = Pipeline([transport.input(), stt, user_agg, llm, tts, transport.output(), assistant_agg])

    latency = UserBotLatencyObserver()

    @latency.event_handler("on_latency_breakdown")
    async def on_breakdown(observer, breakdown):
        for line in breakdown.turn_contribution_lines():
            logger.info(f"[{device_id}] {line}")

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        observers=[latency],
        app_resources=state,
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        rtvi_observer_params=RTVIObserverParams(
            function_call_report_level={"*": RTVIFunctionCallReportLevel.NAME,
                                        "update_ticket": RTVIFunctionCallReportLevel.FULL},
        ),
    )
    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)

    @worker.rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        context.add_message({"role": "developer", "content": "Greet the user and ask what the problem is."})
        await worker.queue_frames([LLMRunFrame()])

    @worker.rtvi.event_handler("on_client_message")
    async def on_client_message(rtvi, msg):
        if msg.type == "photo_uploaded":
            state["ticket"]["photo_id"] = msg.data["photoId"]
            await rtvi.send_server_message({"type": "ticket_update", "ticket": state["ticket"]})
            await worker.queue_frames([LLMMessagesAppendFrame(
                [{"role": "developer", "content": "The user attached a photo. Acknowledge it briefly."}],
                run_llm=True)])
        elif msg.type == "get_ticket":  # client used sendClientRequest
            await rtvi.send_server_response(msg, state["ticket"])
        else:
            await rtvi.send_error_response(msg, f"unknown message {msg.type}")

    @user_agg.event_handler("on_user_turn_idle")
    async def on_idle(aggregator):
        await aggregator.push_frame(LLMMessagesAppendFrame(
            [{"role": "developer", "content": "The user is quiet; ask if they are still there."}], run_llm=True))

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        await runner.cancel()

    await runner.run()


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
```

The `bot()` entry point, the `WorkerRunner` pattern, `worker.rtvi.event_handler("on_client_ready")`, the `on_client_disconnected → runner.cancel()` handler and `audio_out_10ms_chunks=2` all mirror the official `p2p-webrtc/video-transform/server/bot.py` and `getting-started/07-function-calling.py`. These pieces are **[inference]**: the `app_resources` usage (verified as a constructor arg and `FunctionCallParams` field, but not seen in an example), the tool body, and calling `send_server_message` from inside a tool.

---

## 5. Latency features

| Feature | Facts | Source |
|---|---|---|
| Silero VAD | `SileroVADAnalyzer(params=VADParams(confidence=0.7, start_secs=0.2, stop_secs=0.2, min_volume=0.6))` (defaults). Processes a 30 ms chunk in < 1 ms on one CPU thread. Configured on `LLMUserAggregatorParams(vad_analyzer=...)`. Keep `stop_secs=0.2`, because the STT P99 latencies are measured at that value. | [Speech input](https://docs.pipecat.ai/pipecat/learn/speech-input.md) |
| Smart Turn | **v3.2** model bundled as `smart-turn-v3.2-cpu.onnx` (int8). `TurnAnalyzerUserTurnStopStrategy(turn_analyzer=LocalSmartTurnAnalyzerV3())` is the **default** stop strategy since 0.0.102. Whisper-Tiny base, about 8M params, "10ms on some CPUs, under 100ms on most cloud instances". `SmartTurnParams(stop_secs=3.0, pre_speech_ms=500, max_duration_secs=8)` (in `pipecat.audio.turn.smart_turn.base_smart_turn`); `stop_secs` is the silence fallback that forces end-of-turn. A GPU fp32 variant exists and is about 1% more accurate. | [Smart Turn overview](https://docs.pipecat.ai/api-reference/server/utilities/turn-detection/smart-turn-overview.md), [smart-turn README](https://github.com/pipecat-ai/smart-turn), source tree |
| Smart Turn languages | **23:** Arabic, **Bengali**, Chinese, Danish, Dutch, German, English, Finnish, French, **Hindi**, Indonesian, Italian, Japanese, Korean, **Marathi**, Norwegian, Polish, Portuguese, Russian, Spanish, Turkish, Ukrainian, Vietnamese. **Tamil, Telugu, Kannada, Malayalam, Gujarati, Punjabi and Odia are not listed.** Hinglish code-mix isn't mentioned either. | [smart-turn README](https://github.com/pipecat-ai/smart-turn) |
| Alternatives for other Indic languages | `SpeechTimeoutUserTurnStopStrategy(user_speech_timeout=0.6)` (waits for silence plus a transcript). Or let Sarvam endpoint: `SarvamRealtimeSTTService` with `endpointing="vad"` asks the aggregator for external turn strategies (see sarvam.md). | [Speech input](https://docs.pipecat.ai/pipecat/learn/speech-input.md), [Sarvam STT](https://docs.pipecat.ai/api-reference/server/services/stt/sarvam.md) |
| Interruptions | On by default (`enable_interruptions=True` on start strategies). An `InterruptionFrame` cancels the LLM, clears TTS and flushes unplayed audio. The context keeps only the words actually spoken. Tools run with `cancel_on_interruption=True` by default; use `@tool_options(cancel_on_interruption=False)` for tools that must finish, such as writing the ticket. | [Interruptions](https://docs.pipecat.ai/pipecat/fundamentals/interruptions.md), [Function calling](https://docs.pipecat.ai/pipecat/learn/function-calling.md) |
| User idle | `LLMUserAggregatorParams(user_idle_timeout=5.0)` + `@user_aggregator.event_handler("on_user_turn_idle")`. Change at runtime with `UserIdleTimeoutUpdateFrame(timeout=...)`. | [Detecting idle users](https://docs.pipecat.ai/pipecat/fundamentals/detecting-user-idle.md) |
| Metrics | `PipelineParams(enable_metrics=True)` logs TTFB, TTFA (TTS) and TTFAT (LLM), processing time and text aggregation. RTVI forwards them to the client (`onMetrics`). | [Metrics](https://docs.pipecat.ai/pipecat/fundamentals/metrics.md) |
| End-to-end measurement | `UserBotLatencyObserver` fires `on_latency_measured(latency_s)` and `on_latency_breakdown(breakdown)`, where `breakdown.turn_contribution_lines()` gives e.g. "0.200s endpointing wait / 0.125s transcription / 0.336s LLM / 0.359s TTS / 1.020s TOTAL". It also has `on_first_bot_speech_latency`. | [User-Bot Latency Observer](https://docs.pipecat.ai/api-reference/server/utilities/observers/user-bot-latency-observer.md) |

**Getting voice-to-voice under about 1 s [inference]:**
- The docs' own example breakdown (Deepgram + OpenAI + Cartesia) totals **1.02 s**, so sub-1 s is the edge of what a cascade does.
- Use SmallWebRTC on the LAN (negligible network time) and streaming WebSocket STT/TTS rather than HTTP variants.
- Use a fast, non-reasoning LLM setting: Groq with low `reasoning_effort`, or a non-thinking model. Pipecat's Gemini Flash defaults already pick the lowest thinking level.
- Keep the system prompt short and replies to one or two sentences.
- Leave VAD `stop_secs=0.2`; Smart Turn runs on CPU in tens of ms.
- `audio_out_10ms_chunks=2` halves the output buffer versus the default of 4.
- Speech-to-speech (Gemini Live, OpenAI Realtime) skips the STT and TTS hops and is the usual way under 1 s. Gemini Live's language list includes Hindi, Bengali, Tamil, Telugu, Marathi, Gujarati, Kannada, Malayalam and Punjabi, and native-audio models "can switch between languages naturally" ([Live API guide](https://ai.google.dev/gemini-api/docs/live-guide)). Pipecat's `GeminiLiveLLMService` supports tools. Indic voice *quality* versus Sarvam's Bulbul wasn't evaluated here.

---

## 6. LLM services for the team's shortlist

| Option | Pipecat service | Extra | Tool calling | Notes |
|---|---|---|---|---|
| Groq | `GroqLLMService` (`pipecat.services.groq.llm`) | `groq` | yes (inherits `OpenAILLMService`); [`function-calling-groq.py`](https://github.com/pipecat-ai/pipecat/blob/main/examples/function-calling/function-calling-groq.py) | Docs example model `openai/gpt-oss-120b`; `reasoning_effort` low/medium/high on GPT-OSS. Groq also has `GroqSTTService` (Whisper) and `GroqTTSService`. |
| OpenRouter (free models) | `OpenRouterLLMService` (`pipecat.services.openrouter.llm`) | `openrouter` | yes (inherits `OpenAILLMService`); [`function-calling-openrouter.py`](https://github.com/pipecat-ai/pipecat/blob/main/examples/function-calling/function-calling-openrouter.py) | Whether a given *free* model supports tools depends on the upstream provider. Check per model **[inference]**. |
| Sarvam | `SarvamLLMService` (`pipecat.services.sarvam.llm`) | `sarvam` | yes; [`function-calling-sarvam.py`](https://github.com/pipecat-ai/pipecat/blob/main/examples/function-calling/function-calling-sarvam.py) | `sarvam-105b-conversations` resolves to `/v1`; other models go to `/v2`. Details in sarvam.md. |
| Also available | `GoogleLLMService` (default `gemini-3.6-flash`), `OpenAILLMService`, `AnthropicLLMService`, `GeminiLiveLLMService` / `OpenAIRealtimeLLMService` (speech-to-speech) | `google`, `anthropic` | yes | |

Indian STT/TTS in Pipecat: Sarvam (core `sarvam` extra) and Gnani (community `pipecat-gnani` 0.5.12, imports `from pipecat_gnani import GnaniSTTService, GnaniTTSService`). There are also Maya, Vakyam, Smallest and others. See the sibling notes.

---

## 7. Multiple phones: one session per user on one server

- **The dev runner already does one bot per connection.** `POST /start` (transport `webrtc`) registers a `sessionId` and stores `body`. `POST /sessions/{id}/api/offer` creates a **new** `SmallWebRTCConnection` and schedules `bot(runner_args)` as a background task with `SmallWebRTCRunnerArguments(webrtc_connection, body, session_id)`. `SmallWebRTCRequestHandler` defaults to `ConnectionMode.MULTIPLE` and keys peers by `pc_id`. `PATCH` carries trickle ICE. All of this lives in [`runner/run.py`](https://github.com/pipecat-ai/pipecat/blob/main/src/pipecat/runner/run.py) (`_setup_webrtc_routes`, `_setup_unified_start_route`) and [`transports/smallwebrtc/request_handler.py`](https://github.com/pipecat-ai/pipecat/blob/main/src/pipecat/transports/smallwebrtc/request_handler.py).
- **Everything runs in one Python process and one asyncio loop.** The docs say so: "a single process with no lifecycle management… prototyping-only", and recommend a reverse proxy with auth before exposing it publicly ([Running Bots in Production](https://docs.pipecat.ai/pipecat/deployment/running-bots-in-production.md)). Per-session CPU is Silero (< 1 ms per 30 ms chunk), Smart Turn (tens of ms per end-of-turn) and aiortc Opus encode/decode. **[inference]:** 3–6 concurrent phones on a laptop CPU should be fine, because STT/LLM/TTS are remote. Watch for event-loop stalls in the logs, and fall back to one process per phone on different ports if needed.
- **Session state:** keep it per call to `bot()`, not in globals. Use `runner_args.session_id`, `runner_args.body` (e.g. `deviceId`) and `PipelineWorker(app_resources=...)`. For a shared "operator dashboard" view across phones, keep a module-level dict keyed by session id and expose it via a custom route on `pipecat.runner.run.app` **[inference]**.
- **Runner CLI facts:** default `--host localhost`, `--port 7860`, so **pass `--host 0.0.0.0`** for LAN/tailnet. Also `-t webrtc` (restrict transports), `--ice-servers` / `PIPECAT_ICE_SERVERS`, `--allowed-origins` / `PIPECAT_ALLOWED_ORIGINS`, `GET /status`, and a prebuilt web UI at `/client` (handy for testing from a laptop browser). For `transport: "websocket"` the runner returns `wsUrl` built from `--host`, and uses `wss` whenever host isn't `localhost`, which is a trap behind LAN IPs and tunnels. Not relevant if you use WebRTC.
- **Production patterns,** for later: "warm pool with subprocess workers" and "VM per session" ([deployment patterns](https://docs.pipecat.ai/pipecat/deployment/running-bots-in-production.md)).

---

## 8. Risks and open questions

1. **Expo SDK 55 lock-in** (verified peer dep). If the team scaffolds SDK 57, the Daily config plugin and `react-native-webrtc` fork become the unknowns. Scaffold with `npx create-expo-app@latest --template` on SDK 55, or copy the official example's `package.json`.
2. **WebRTC over Tailscale on Android** is unverified. Do a 10-minute spike on one phone before relying on it.
3. **Hackathon Wi-Fi client isolation** blocks LAN P2P entirely. A personal hotspot is the cheapest insurance.
4. **Smart Turn doesn't cover most South Indian languages.** Choose the turn-stop strategy by the demo language.
5. **Docs/source mismatch:** the `onServerMessage` payload shape. The source passes the raw payload.
6. The RN transports were last released **2026-06-22** (1.8.0, on client-js 1.12). Server 1.12.0 speaks RTVI 2.1.0 and client-js 1.13.1 also speaks 2.1.0. Pin `@pipecat-ai/client-js@1.13.1` explicitly so the transport's `^1.12.0` range doesn't float.
