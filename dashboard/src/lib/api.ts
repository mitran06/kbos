import type {
  GlossaryTerm, Health, Machine, Metrics, Person, SeriesSample, ShiftSession, Status, TicketDetail, TicketSummary, Severity, FeedEvent,
} from "./types";

export class ApiError extends Error {}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
  });
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const body: unknown = await res.json();
      if (body && typeof body === "object" && "detail" in body) {
        const d = (body as { detail: unknown }).detail;
        msg = typeof d === "string" ? d : JSON.stringify(d);
      }
    } catch {
      /* not json */
    }
    throw new ApiError(msg);
  }
  return (await res.json()) as T;
}

const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });

export interface CheckInput {
  what_checked: string;
  what_found: string;
  next_check_minutes?: number;
}

export interface TicketPatch {
  title?: string;
  description?: string;
  severity?: Severity;
  assignee_ids?: number[];
  status?: Status;
  check?: CheckInput;
}

export const api = {
  tickets: () => req<TicketSummary[]>("/api/tickets"),
  ticket: (key: string) => req<TicketDetail>(`/api/tickets/${encodeURIComponent(key)}`),
  patchTicket: (key: string, body: TicketPatch) => req<TicketSummary>(`/api/tickets/${encodeURIComponent(key)}`, json("PATCH", body)),
  addCheck: (key: string, body: CheckInput & { new_status?: Status }) =>
    req<TicketSummary>(`/api/tickets/${encodeURIComponent(key)}/checks`, json("POST", body)),
  metrics: () => req<Metrics>("/api/metrics"),
  people: () => req<Person[]>("/api/people?all=1"),
  machines: () => req<Machine[]>("/api/machines"),
  machineTelemetry: (code: string, minutes = 10) => req<SeriesSample[]>(`/api/machines/${encodeURIComponent(code)}/telemetry?minutes=${minutes}`),
  events: (limit = 50) => req<FeedEvent[]>(`/api/events?limit=${limit}`),
  shifts: (limit = 40) => req<ShiftSession[]>(`/api/shifts?limit=${limit}`),
  glossary: () => req<GlossaryTerm[]>("/api/glossary"),
  putGlossary: (terms: GlossaryTerm[]) => req<GlossaryTerm[]>("/api/glossary", json("PUT", { terms })),
  health: () => req<Health>("/api/health"),
  inject: (machine_code: string) => req<{ ok: boolean }>("/api/demo/inject", json("POST", { machine_code, kind: "vibration" })),
  clear: (machine_code: string) => req<{ ok: boolean }>("/api/demo/clear", json("POST", { machine_code })),
  reset: () => req<{ ok: boolean }>("/api/demo/reset", json("POST", {})),
};

export function errorText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}
