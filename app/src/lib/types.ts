export type Role = 'operator' | 'supervisor' | 'maintenance' | 'admin';
export type Severity = 'critical' | 'high' | 'medium' | 'low';
export type Status = 'open' | 'in_progress' | 'monitoring' | 'closed';

export interface Person {
  id: number;
  name: string;
  first_name: string;
  initials: string;
  role: Role;
  role_label: string;
  shift: 'day' | 'night';
  preferred_language: 'en' | 'hi';
  avatar_hue: number;
  on_shift_now: boolean;
}

export interface MiniPerson {
  id: number | null;
  name: string;
  initials: string;
  avatar_hue: number;
  role: Role;
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

export interface TelemetryPoint {
  t: number;
  v: number;
  c: number;
}

export interface TicketDetail extends TicketSummary {
  description: string;
  symptom: string;
  since_text: string;
  context: string;
  machine_running: boolean | null;
  telemetry_snapshot: {
    current: { vibration_mm_s: number; temperature_c: number; load_pct: number; output_count: number };
    vibration_band: 'good' | 'warning' | 'alarm';
    target_per_shift: number | null;
    target_so_far: number | null;
    series: TelemetryPoint[];
  } | null;
  transcript: { who: 'user' | 'kb'; text: string; lang: string }[];
  checks: Check[];
  photos: { id: number; url: string }[];
  related: TicketSummary[];
}

export interface Draft {
  machine_code: string | null;
  symptom: string | null;
  since: string | null;
  context: string | null;
  machine_running: boolean | null;
  severity: Severity | null;
  title: string | null;
  related_ticket_key: string | null;
  missing: string[];
  photos: { id: number; url: string }[];
  will_assign: string[];
}

export interface ShiftSession {
  id: number;
  person_id: number;
  started_at: string;
}

export interface Metrics {
  open: number;
  critical: number;
  overdue_monitoring: number;
  unclear_checks: number;
}

/** Server -> app RTVI messages (onServerMessage payloads). */
export type ServerMessage =
  | { type: 'ui.tickets'; heading: string; tickets: TicketSummary[]; brief?: boolean }
  | { type: 'ui.ticket'; ticket: TicketDetail; highlight?: string }
  | { type: 'ui.draft'; draft: Draft | null; possible_related?: { key: string; title: string }[] }
  | { type: 'ui.camera'; reason: string }
  | { type: 'ui.ticket_filed'; ticket: TicketSummary }
  | { type: 'ui.session_end'; reason: 'idle' | 'stop' }
  | { type: 'ui.shift_ended'; summary: string }
  | { type: 'ui.notice'; kind: 'warning' | 'info'; message: string }
  | { type: 'ui.latency'; at: string; person: string; lines: string[] }
  | { type: 'ui.error'; message: string };
