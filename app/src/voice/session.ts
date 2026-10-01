import { PipecatClient, type TransportState } from '@pipecat-ai/client-js';
import { RNSmallWebRTCTransport } from '@pipecat-ai/react-native-small-webrtc-transport';
import { DailyMediaManager } from '@pipecat-ai/react-native-daily-media-manager';
import * as Haptics from 'expo-haptics';
import { makeMutable } from 'react-native-reanimated';
import type { ServerMessage } from '../lib/types';
import { useApp } from '../state/store';

/** Live audio levels for the orb and waveform, written from JS and read on the UI thread. */
export const micLevel = makeMutable(0);
export const botLevel = makeMutable(0);

const BRIEF_SETTLE_MS = 1100;

class VoiceSession {
  private client: PipecatClient | null = null;
  private briefPending = false;
  private briefTimer: ReturnType<typeof setTimeout> | null = null;
  private wantBrief = false;
  private connecting = false;
  sessionId = '';

  get connected(): boolean {
    return useApp.getState().voice === 'ready';
  }

  async connect(opts: { brief: boolean }): Promise<void> {
    const { person, shift, serverUrl } = useApp.getState();
    if (!person || this.connecting) return;
    if (this.client) await this.disconnect();
    this.connecting = true;
    this.wantBrief = opts.brief;
    useApp.getState().set({ voice: 'connecting', voiceError: null });

    const client = new PipecatClient({
      transport: new RNSmallWebRTCTransport({ mediaManager: new DailyMediaManager() }),
      enableMic: true,
      enableCam: false,
      callbacks: {
        onTransportStateChanged: (s: TransportState) => {
          if (s === 'disconnected' || s === 'error') {
            useApp.getState().set({ voice: s === 'error' ? 'error' : 'off', listening: false, botSpeaking: false });
          }
        },
        onConnected: () => {
          client.updateMic('SPEAKERPHONE');
          client.enableMic(false);
        },
        onBotReady: () => {
          useApp.getState().set({ voice: 'ready' });
          if (this.wantBrief) {
            this.wantBrief = false;
            this.briefPending = true;
            this.send('brief.start');
          }
        },
        onDisconnected: () => useApp.getState().set({ voice: 'off', listening: false, botSpeaking: false }),
        onError: (e) => {
          const msg = (e as { data?: { error?: string } })?.data?.error ?? 'voice error';
          console.log('[kb] error', msg);
        },
        onLocalAudioLevel: (level: number) => micLevel.set(level),
        onRemoteAudioLevel: (level: number) => botLevel.set(level),
        onUserTranscript: (t) => {
          if (!t.text?.trim()) return;
          useApp.getState().set({ caption: { who: 'user', text: t.text, final: !!t.final, at: Date.now() } });
        },
        onBotTranscript: (d) => {
          const text = d.text?.trim();
          if (!text) return;
          const prev = useApp.getState().caption;
          const joined = prev && prev.who === 'kb' && Date.now() - prev.at < 6000 ? `${prev.text} ${text}` : text;
          useApp.getState().set({ caption: { who: 'kb', text: joined, final: true, at: Date.now() } });
        },
        onBotStartedSpeaking: () => {
          if (this.briefTimer) clearTimeout(this.briefTimer);
          useApp.getState().set({ botSpeaking: true });
        },
        onBotStoppedSpeaking: () => {
          useApp.getState().set({ botSpeaking: false });
          botLevel.set(0);
          if (this.briefPending) {
            if (this.briefTimer) clearTimeout(this.briefTimer);
            this.briefTimer = setTimeout(() => {
              this.briefPending = false;
              this.listen();
            }, BRIEF_SETTLE_MS);
          }
        },
        onLLMFunctionCallStarted: () => useApp.getState().set({ working: true }),
        onLLMFunctionCallStopped: () => useApp.getState().set({ working: false }),
        onServerMessage: (data: unknown) => this.onServerMessage(data as ServerMessage),
      },
    });
    this.client = client;
    try {
      await client.initDevices();
      await client.startBotAndConnect({
        endpoint: `${serverUrl}/start`,
        requestData: {
          transport: 'webrtc',
          enableDefaultIceServers: false,
          body: { person_id: person.id, shift_session_id: shift?.id, device_id: `phone-${person.id}` },
        },
      });
    } catch (e) {
      console.log('[kb] connect failed', String(e));
      useApp.getState().set({ voice: 'error', voiceError: String(e) });
    } finally {
      this.connecting = false;
    }
  }

  async disconnect(): Promise<void> {
    const c = this.client;
    this.client = null;
    this.briefPending = false;
    if (this.briefTimer) clearTimeout(this.briefTimer);
    if (c) {
      try {
        await c.disconnect();
      } catch {
        // already gone
      }
    }
    useApp.getState().set({ voice: 'off', listening: false, botSpeaking: false });
  }

  send(type: string, data: Record<string, unknown> = {}): void {
    try {
      this.client?.sendClientMessage(type, data);
    } catch (e) {
      console.log('[kb] send failed', type, String(e));
    }
  }

  listen(): void {
    if (!this.client) return;
    this.briefPending = false;
    useApp.getState().set({ listening: true });
    try {
      this.client.enableMic(true);
    } catch {
      // mic toggling is best-effort; the server gate is the real switch
    }
    this.send('listen.start');
  }

  stop(): void {
    useApp.getState().set({ listening: false });
    this.send('listen.stop');
    micLevel.set(0);
    try {
      this.client?.enableMic(false);
    } catch {
      // see listen()
    }
  }

  sendText(text: string): void {
    this.send('text.input', { text });
    useApp.getState().set({ caption: { who: 'user', text, final: true, at: Date.now() } });
  }

  private onServerMessage(m: ServerMessage): void {
    const set = useApp.getState().set;
    if (!m || typeof m !== 'object' || !('type' in m)) return;
    switch (m.type) {
      case 'ui.tickets':
        set({ list: { heading: m.heading, tickets: m.tickets, brief: !!m.brief }, filed: null });
        break;
      case 'ui.ticket':
        set({ detail: m.ticket });
        break;
      case 'ui.draft':
        set({ draft: m.draft, filed: m.draft ? null : useApp.getState().filed });
        break;
      case 'ui.camera':
        set({ camera: { reason: m.reason } });
        break;
      case 'ui.ticket_filed':
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        set({ filed: m.ticket, draft: null, camera: null });
        break;
      case 'ui.session_end':
        this.stop();
        break;
      case 'ui.shift_ended':
        set({ handover: m.summary || 'Handover recorded' });
        break;
      case 'ui.notice':
        if (m.kind === 'warning') Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
        break;
      case 'ui.latency':
        set({ latency: m.lines });
        break;
      default:
        break;
    }
  }
}

export const voice = new VoiceSession();
