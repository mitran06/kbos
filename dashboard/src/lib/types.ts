export type Severity = "critical" | "high" | "medium" | "low";
export type Status = "open" | "in_progress" | "monitoring" | "closed";
export type Role = "operator" | "supervisor" | "maintenance" | "admin";

export const SEVERITIES: Severity[] = ["critical", "high", "medium", "low"];
export const STATUSES: Status[] = ["open", "in_progress", "monitoring", "closed"];

export interface MiniPerson {
  id: number | null;
  name: string;
  initials: string;
  avatar_hue: number;
  role: Role;
}

export interface Person {
  id: number;
  name: string;
  first_name: string;
  initials: string;
  role: Role;
  role_label: string;
  shift: "day" | "night";
  preferred_language: string;
  avatar_hue: number;
  on_shift_now: boolean;
}

export interface Check {
  id: number;
  author: MiniPerson;
  what_checked: string;
  what_found: string;
  status_from: Status | null;
  status_to: Status | null;
  unclear: boolean;
  next_check_at: string | null;
  created_at: string;
}

export interface TicketSummary {
  id: number;
  key: string;
  title: string;
  machine_code: string;
  machine_name: string;
  severity: Severity;
  status: Status;
  overdue: boolean;
  unclear: boolean;
  assignees: MiniPerson[];
  reporter: MiniPerson | null;
  monitoring_owner: MiniPerson | null;
  next_check_at: string | null;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
  last_check: Check | null;
  related_keys: string[];
  photo_count: number;
}

export interface SnapshotPoint {
  t: number;
  v: number;
  c: number;
}

export interface TelemetrySnapshot {
  machine_code: string;
  current: { vibration_mm_s: number; temperature_c: number; load_pct: number; output_count: number };
  vibration_band: Band;
  target_per_shift: number | null;
  target_so_far: number | null;
  series: SnapshotPoint[];
}

export interface TranscriptLine {
  who: "user" | "kb";
  text: string;
  lang?: string;
  at?: string;
}

export interface TicketDetail extends TicketSummary {
  description: string;
  symptom: string;
  since_text: string;
  context: string;
  machine_running: boolean | null;
  telemetry_snapshot: TelemetrySnapshot | null;
  transcript: TranscriptLine[];
  source_language: string;
  checks: Check[];
  photos: { id: number; url: string }[];
  related: TicketSummary[];
}

export interface Metrics {
  open: number;
  critical: number;
  overdue_monitoring: number;
  unclear_checks: number;
  mean_time_to_close_h: number | null;
  closed_7d: number;
}

export type Band = "good" | "warning" | "alarm";

export interface MachineTelemetry {
  t: number;
  vibration_mm_s: number;
  temperature_c: number;
  load_pct: number;
  output_count: number;
  vibration_band: Band;
  target_per_shift: number | null;
  target_so_far: number | null;
  injected: boolean;
}

export interface Machine {
  code: string;
  name: string;
  line: string;
  unit: string;
  target_per_shift: number | null;
  telemetry: MachineTelemetry;
  open_tickets: string[];
}

export interface SeriesSample {
  t: number;
  vibration_mm_s: number;
  temperature_c: number;
  load_pct: number;
  output_count: number;
}

/** Compact live telemetry from /ws: {code: {v,c,l,o,t}} */
export interface CompactSample {
  v: number;
  c: number;
  l: number;
  o: number;
  t: number;
}

export interface ShiftSession {
  id: number;
  person_id: number;
  person_name: string | null;
  started_at: string | null;
  ended_at: string | null;
  brief_text: string;
  handover_summary: string;
}

export interface GlossaryTerm {
  term: string;
  meaning: string;
}

export interface Health {
  ok: boolean;
  uptime_s: number;
  db: { tickets: number };
  keys: { key: number; status: string }[];
  providers: { llm: string; tts: string; tts_voice: string; stt: string };
  sessions: { id: string; person: string; listening: boolean }[];
  ws_clients: number;
  latency: { at: string; person: string; lines: string[] }[];
  shift_now: "day" | "night";
}

// ---- /ws events ----------------------------------------------------------------

type Ev<T extends string, D> = { id?: number; type: T; at: string; data: D };

export type TicketEvent = Ev<"ticket.created" | "ticket.updated", { ticket: TicketSummary; by?: number | "admin" | null; assigned?: boolean }>;
export type CheckEvent = Ev<"check.added", { ticket_key: string; check: Check }>;
export type ShiftStartedEvent = Ev<"shift.started", { shift_session: ShiftSession; person?: Person }>;
export type ShiftEndedEvent = Ev<"shift.ended", { shift_session: ShiftSession }>;
export type TelemetryEvent = Ev<"telemetry", Record<string, CompactSample>>;
export type GlossaryEvent = Ev<"glossary.updated", { terms: GlossaryTerm[] }>;
export type DemoEvent = Ev<"demo.reset" | "demo.seeded", Record<string, never>>;
export type DemoMachineEvent = Ev<"demo.injected" | "demo.cleared", { machine_code: string; kind?: string }>;

export type KbosEvent =
  | TicketEvent
  | CheckEvent
  | ShiftStartedEvent
  | ShiftEndedEvent
  | TelemetryEvent
  | GlossaryEvent
  | DemoEvent
  | DemoMachineEvent;

export type FeedEvent = Exclude<KbosEvent, TelemetryEvent>;
