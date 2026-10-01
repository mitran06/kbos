import type { Severity, Status, TicketSummary } from "./types";

const IST = "Asia/Kolkata";
const timeFmt = new Intl.DateTimeFormat("en-IN", { timeZone: IST, hour: "2-digit", minute: "2-digit", hour12: false });
const dayFmt = new Intl.DateTimeFormat("en-IN", { timeZone: IST, day: "numeric", month: "short" });
const dayKey = new Intl.DateTimeFormat("en-CA", { timeZone: IST, year: "numeric", month: "2-digit", day: "2-digit" });

export const parse = (iso: string | null | undefined): number | null => (iso ? Date.parse(iso) : null);

/** "02:20" in IST; prefixes "Yesterday" / "29 Sep" when not today. */
export function istTime(iso: string | null | undefined, now = Date.now()): string {
  const t = parse(iso);
  if (t === null) return "—";
  const d = new Date(t);
  const today = dayKey.format(new Date(now));
  const that = dayKey.format(d);
  const hm = timeFmt.format(d);
  if (that === today) return hm;
  const yesterday = dayKey.format(new Date(now - 86_400_000));
  if (that === yesterday) return `Yesterday ${hm}`;
  return `${dayFmt.format(d)} ${hm}`;
}

export function istClock(now: number): string {
  return timeFmt.format(new Date(now));
}

export function duration(ms: number): string {
  const m = Math.max(0, Math.round(ms / 60_000));
  if (m < 1) return "<1m";
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  const rm = m % 60;
  if (h < 24) return rm && h < 10 ? `${h}h ${rm}m` : `${h}h`;
  const d = Math.floor(h / 24);
  return `${d}d`;
}

export function ago(iso: string | null | undefined, now = Date.now()): string {
  const t = parse(iso);
  if (t === null) return "—";
  const diff = now - t;
  if (diff < 45_000) return "just now";
  return `${duration(diff)} ago`;
}

export const SEVERITY_LABEL: Record<Severity, string> = { critical: "Critical", high: "High", medium: "Medium", low: "Low" };
export const STATUS_LABEL: Record<Status, string> = { open: "Open", in_progress: "In Progress", monitoring: "Monitoring", closed: "Closed" };

export function isOverdue(t: Pick<TicketSummary, "status" | "next_check_at">, now = Date.now()): boolean {
  const due = parse(t.next_check_at);
  return t.status === "monitoring" && due !== null && due < now;
}

const SEV_ORDER: Record<Severity, number> = { critical: 0, high: 1, medium: 2, low: 3 };

/** Mirrors the backend: Critical first, then overdue Monitoring, then Severity, oldest first. Closed last (newest closed first). */
export function sortTickets(list: TicketSummary[], now = Date.now()): TicketSummary[] {
  return [...list].sort((a, b) => {
    const ac = a.status === "closed", bc = b.status === "closed";
    if (ac !== bc) return ac ? 1 : -1;
    if (ac && bc) return (parse(b.closed_at) ?? 0) - (parse(a.closed_at) ?? 0);
    const acrit = a.severity === "critical", bcrit = b.severity === "critical";
    if (acrit !== bcrit) return acrit ? -1 : 1;
    const ao = isOverdue(a, now), bo = isOverdue(b, now);
    if (ao !== bo) return ao ? -1 : 1;
    if (a.severity !== b.severity) return SEV_ORDER[a.severity] - SEV_ORDER[b.severity];
    return (parse(a.created_at) ?? 0) - (parse(b.created_at) ?? 0);
  });
}

export const firstName = (name: string | null | undefined) => (name ? name.split(" ")[0] : "Someone");

export function checkText(c: { what_checked: string; what_found: string }): string {
  const parts = [c.what_checked, c.what_found].map((s) => s.trim()).filter(Boolean);
  return parts.join(" → ");
}
