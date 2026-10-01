import { create } from "zustand";
import { toast } from "sonner";
import { api } from "./api";
import { STATUS_LABEL, firstName } from "./format";
import type { FeedEvent, KbosEvent, Metrics, Person, TicketSummary } from "./types";

export type Tab = "tickets" | "machines" | "shifts" | "glossary" | "demo";
export const TABS: Tab[] = ["tickets", "machines", "shifts", "glossary", "demo"];

export type FeedTone = "neutral" | "filed" | "closed" | "unclear" | "status" | "shift" | "demo";
export interface FeedLine {
  id: string;
  at: string;
  text: string;
  ticketKey?: string;
  actor?: { name: string; initials: string; avatar_hue: number } | null;
  tone: FeedTone;
  note?: string;
}

interface AppState {
  tab: Tab;
  tickets: Record<string, TicketSummary>;
  ticketsLoaded: boolean;
  metrics: Metrics | null;
  people: Person[];
  feed: FeedLine[];
  flash: Record<string, number>;
  fresh: Record<string, number>;
  openKey: string | null;
  /** bumped on any change to the open ticket, so the sheet refetches */
  detailVersion: number;
  /** bumped on demo.reset / reconnect so every view refetches */
  epoch: number;
  shiftsVersion: number;
  glossaryVersion: number;
  machinesVersion: number;
  injected: Record<string, boolean>;

  setTab: (t: Tab) => void;
  openTicket: (key: string | null) => void;
  loadAll: () => Promise<void>;
  refreshMetrics: () => void;
  apply: (ev: KbosEvent, opts?: { live: boolean }) => void;
}

const FEED_MAX = 80;
let metricsTimer: ReturnType<typeof setTimeout> | undefined;
let feedSeq = 0;

function personById(people: Person[], id: unknown): Person | undefined {
  return typeof id === "number" ? people.find((p) => p.id === id) : undefined;
}

function recentFor(feed: FeedLine[], key: string, at: string, withinMs = 6000): boolean {
  const t = Date.parse(at);
  return feed.some((l) => l.ticketKey === key && Math.abs(t - Date.parse(l.at)) < withinMs && l.tone !== "neutral");
}

/** The ticket's last Check, if it changed Status within a few seconds of `at`. */
function freshStatusCheck(t: TicketSummary, at: string) {
  const lc = t.last_check;
  if (!lc?.status_to) return null;
  return Math.abs(Date.parse(at) - Date.parse(lc.created_at)) < 8000 ? lc : null;
}

const toastedCloses = new Set<number>();

/** Turns an Event into one human line for the activity feed (or null to skip it). */
function describe(ev: FeedEvent, s: Pick<AppState, "people" | "feed" | "tickets">): FeedLine | null {
  const id = ev.id !== undefined ? `e${ev.id}` : `l${++feedSeq}`;
  const base = { id, at: ev.at };
  switch (ev.type) {
    case "ticket.created": {
      const t = ev.data.ticket;
      const who = personById(s.people, ev.data.by);
      return {
        ...base,
        tone: "filed",
        ticketKey: t.key,
        actor: who ?? t.reporter,
        text: `${firstName(who?.name ?? t.reporter?.name)} filed ${t.key} on ${t.machine_code}`,
        note: t.title,
      };
    }
    case "check.added": {
      const c = ev.data.check;
      const who = firstName(c.author.name);
      const key = ev.data.ticket_key;
      if (c.status_to === "closed") return { ...base, tone: "closed", ticketKey: key, actor: c.author, text: `${who} closed ${key}`, note: c.what_found || c.what_checked };
      if (c.unclear) return { ...base, tone: "unclear", ticketKey: key, actor: c.author, text: `Check on ${key} by ${who}`, note: c.what_found || c.what_checked || "nothing said" };
      if (c.status_to) return { ...base, tone: "status", ticketKey: key, actor: c.author, text: `${who} moved ${key} to ${STATUS_LABEL[c.status_to]}`, note: c.what_found };
      return { ...base, tone: "status", ticketKey: key, actor: c.author, text: `Check on ${key} by ${who}`, note: c.what_found };
    }
    case "ticket.updated": {
      const t = ev.data.ticket;
      if (recentFor(s.feed, t.key, ev.at)) return null;
      // the link written onto the older Ticket when a Related Ticket is filed
      if (t.related_keys.some((k) => s.feed.some((l) => l.tone === "filed" && l.ticketKey === k && Math.abs(Date.parse(l.at) - Date.parse(ev.at)) < 6000))) return null;
      const prev = s.tickets[t.key];
      const who = ev.data.by === "admin" ? "Admin" : firstName(personById(s.people, ev.data.by)?.name);
      const lc = freshStatusCheck(t, ev.at);
      if (lc?.status_to) {
        const actor = firstName(lc.author.name);
        if (lc.status_to === "closed") return { ...base, tone: "closed", ticketKey: t.key, actor: lc.author, text: `${actor} closed ${t.key}`, note: lc.what_found };
        return { ...base, tone: lc.unclear ? "unclear" : "status", ticketKey: t.key, actor: lc.author, text: `${actor} moved ${t.key} to ${STATUS_LABEL[lc.status_to]}`, note: lc.what_found || lc.what_checked };
      }
      if (prev && t.related_keys.length > prev.related_keys.length) {
        const added = t.related_keys.filter((k) => !prev.related_keys.includes(k));
        if (added.every((k) => recentFor(s.feed, k, ev.at))) return null;
        return { ...base, tone: "neutral", ticketKey: t.key, text: `${t.key} linked to ${added.join(", ")}`, note: "Related Ticket" };
      }
      if (ev.data.assigned || (prev && prev.assignees.map((a) => a.id).join() !== t.assignees.map((a) => a.id).join())) {
        const names = t.assignees.map((a) => firstName(a.name)).join(", ") || "nobody";
        return { ...base, tone: "neutral", ticketKey: t.key, text: `${who} reassigned ${t.key}`, note: `Assignees: ${names}` };
      }
      return { ...base, tone: "neutral", ticketKey: t.key, text: `${who} updated ${t.key}` };
    }
    case "shift.started": {
      const name = ev.data.person?.name ?? ev.data.shift_session.person_name;
      const p = ev.data.person;
      return { ...base, tone: "shift", actor: p ?? null, text: `Shift started: ${name ?? "someone"}` };
    }
    case "shift.ended": {
      const ss = ev.data.shift_session;
      const p = personById(s.people, ss.person_id);
      return { ...base, tone: "shift", actor: p ?? null, text: `Shift ended: ${ss.person_name ?? "someone"}`, note: ss.handover_summary ? `Handover: ${ss.handover_summary}` : undefined };
    }
    case "glossary.updated":
      return { ...base, tone: "neutral", text: "Shorthand Glossary updated" };
    case "demo.reset":
      return { ...base, tone: "demo", text: "Demo reset" };
    case "demo.seeded":
      return { ...base, tone: "demo", text: "Demo data seeded" };
    case "demo.injected":
      return { ...base, tone: "demo", text: `Vibration injected on ${ev.data.machine_code}` };
    case "demo.cleared":
      return { ...base, tone: "demo", text: `${ev.data.machine_code} back to baseline` };
  }
}

export const useApp = create<AppState>((set, get) => ({
  tab: "tickets",
  tickets: {},
  ticketsLoaded: false,
  metrics: null,
  people: [],
  feed: [],
  flash: {},
  fresh: {},
  openKey: null,
  detailVersion: 0,
  epoch: 0,
  shiftsVersion: 0,
  glossaryVersion: 0,
  machinesVersion: 0,
  injected: {},

  setTab: (tab) => set({ tab }),
  openTicket: (openKey) => set({ openKey }),

  loadAll: async () => {
    const [tickets, metrics, people, events] = await Promise.all([api.tickets(), api.metrics(), api.people(), api.events(60)]);
    const byKey: Record<string, TicketSummary> = {};
    for (const t of tickets) byKey[t.key] = t;
    // Build the feed oldest → newest so the dedupe rules see context, then show newest first.
    let feed: FeedLine[] = [];
    const ctx = { people, feed, tickets: {} as Record<string, TicketSummary> };
    for (const ev of [...events].reverse()) {
      const line = describe(ev, { ...ctx, feed });
      if (line) feed = [line, ...feed];
      if (ev.type === "ticket.created" || ev.type === "ticket.updated") ctx.tickets[ev.data.ticket.key] = ev.data.ticket;
    }
    set((s) => ({
      tickets: byKey,
      ticketsLoaded: true,
      metrics,
      people,
      feed: feed.slice(0, FEED_MAX),
      epoch: s.epoch + 1,
      detailVersion: s.detailVersion + 1,
    }));
  },

  refreshMetrics: () => {
    clearTimeout(metricsTimer);
    metricsTimer = setTimeout(() => {
      api.metrics().then((metrics) => set({ metrics })).catch(() => undefined);
    }, 250);
  },

  apply: (ev, opts = { live: true }) => {
    if (ev.type === "telemetry") return;
    const s = get();
    const line = describe(ev, s);
    const patch: Partial<AppState> = {};
    if (line) patch.feed = [line, ...s.feed].slice(0, FEED_MAX);

    switch (ev.type) {
      case "ticket.created":
      case "ticket.updated": {
        const t = ev.data.ticket;
        const prev = s.tickets[t.key];
        patch.tickets = { ...s.tickets, [t.key]: t };
        patch.flash = { ...s.flash, [t.key]: Date.now() };
        if (ev.type === "ticket.created" || !prev) patch.fresh = { ...s.fresh, [t.key]: Date.now() };
        if (s.openKey === t.key || t.related_keys.includes(s.openKey ?? "")) patch.detailVersion = s.detailVersion + 1;
        patch.machinesVersion = s.machinesVersion + 1;
        if (opts.live) {
          if (ev.type === "ticket.created") {
            toast(`${t.key} filed on ${t.machine_code}`, { description: t.title });
          } else {
            const lc = freshStatusCheck(t, ev.at);
            if (lc?.status_to === "closed" && !toastedCloses.has(lc.id)) {
              toastedCloses.add(lc.id);
              toast.success(`${t.key} closed`, { description: `Closed by ${lc.author.name}` });
            }
          }
        }
        get().refreshMetrics();
        break;
      }
      case "check.added":
        if (s.openKey === ev.data.ticket_key) patch.detailVersion = s.detailVersion + 1;
        get().refreshMetrics();
        break;
      case "shift.started":
      case "shift.ended":
        patch.shiftsVersion = s.shiftsVersion + 1;
        break;
      case "glossary.updated":
        patch.glossaryVersion = s.glossaryVersion + 1;
        break;
      case "demo.injected":
        patch.injected = { ...s.injected, [ev.data.machine_code]: true };
        break;
      case "demo.cleared":
        patch.injected = { ...s.injected, [ev.data.machine_code]: false };
        break;
      case "demo.reset":
        patch.openKey = null;
        patch.injected = {};
        set(patch);
        void get().loadAll();
        return;
      default:
        break;
    }
    set(patch);
  },
}));
