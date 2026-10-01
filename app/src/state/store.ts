import { create } from 'zustand';
import { DEFAULT_SERVER } from '../lib/config';
import type { Draft, Person, ShiftSession, TicketDetail, TicketSummary } from '../lib/types';

export type VoiceStatus = 'off' | 'connecting' | 'ready' | 'error';

export interface Caption {
  who: 'user' | 'kb';
  text: string;
  final: boolean;
  at: number;
}

interface AppState {
  serverUrl: string;
  person: Person | null;
  shift: ShiftSession | null;

  voice: VoiceStatus;
  voiceError: string | null;
  listening: boolean; // pill open, gate open on the server
  botSpeaking: boolean;
  working: boolean; // a tool call is in flight
  caption: Caption | null;

  list: { heading: string; tickets: TicketSummary[]; brief: boolean } | null;
  draft: Draft | null;
  filed: TicketSummary | null;
  detail: TicketDetail | null;
  camera: { reason: string } | null;
  drop: TicketSummary | null;
  handover: string | null;
  latency: string[];
  typeMode: boolean;

  set: (patch: Partial<AppState>) => void;
  resetSession: () => void;
}

const sessionDefaults = {
  voice: 'off' as VoiceStatus,
  voiceError: null,
  listening: false,
  botSpeaking: false,
  working: false,
  caption: null,
  list: null,
  draft: null,
  filed: null,
  detail: null,
  camera: null,
  drop: null,
  handover: null,
};

export const useApp = create<AppState>((set) => ({
  serverUrl: DEFAULT_SERVER,
  person: null,
  shift: null,
  latency: [],
  typeMode: false,
  ...sessionDefaults,
  set: (patch) => set(patch),
  resetSession: () => set({ ...sessionDefaults, person: null, shift: null }),
}));
