import { ArrowRight, Check as CheckIcon, ChevronDown, Link2, Pencil, Plus, Users } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { BAND_FILL, BAND_LABEL, VibrationChart, band } from "@/components/charts";
import { Avatar, AvatarStack, KeyChip, MachineChip, Orb, SeverityBadge, StatusBadge, TicketStatusBadges, UnclearBadge } from "@/components/kb";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Popover } from "@/components/ui/popover";
import { Select } from "@/components/ui/select";
import { Sheet } from "@/components/ui/sheet";
import { api, errorText, type TicketPatch } from "@/lib/api";
import { SEVERITY_LABEL, STATUS_LABEL, ago, duration, firstName, istTime, isOverdue, parse } from "@/lib/format";
import { useApp } from "@/lib/store";
import { SEVERITIES, STATUSES, type Check, type Person, type Severity, type Status, type TicketDetail, type TicketSummary } from "@/lib/types";
import { useNow } from "@/lib/useNow";
import { cn } from "@/lib/utils";

const ROLE: Record<string, string> = { operator: "Operator", supervisor: "Supervisor", maintenance: "Maintenance Technician", admin: "Admin" };

function useDetail(key: string | null): [TicketDetail | null, () => void] {
  const version = useApp((s) => s.detailVersion);
  const [detail, setDetail] = useState<TicketDetail | null>(null);
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    if (!key) return;
    let alive = true;
    api
      .ticket(key)
      .then((d) => alive && setDetail(d))
      .catch((e: unknown) => alive && toast.error(`Couldn't load ${key}`, { description: errorText(e) }));
    return () => {
      alive = false;
    };
  }, [key, version, nonce]);
  return [detail && detail.key === key ? detail : null, () => setNonce((n) => n + 1)];
}

// ---------------------------------------------------------------------------------

function Section({ title, aside, children, className }: { title: string; aside?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cn("rounded-3xl bg-card p-6 shadow-card", className)}>
      <div className="mb-4 flex items-center justify-between gap-3">
        <h3 className="text-[0.78rem] font-semibold uppercase tracking-[0.07em] text-muted">{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  );
}

function Fact({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-0.5 text-sm text-ink">{value}</div>
    </div>
  );
}

const given = (s: string | null | undefined) => (s && s.trim().toLowerCase() !== "not given" ? s : <span className="text-faint">Not given</span>);

// ---- the Check form (required for any Status change) -------------------------------

const NEXT_CHECK = [
  { value: "30", label: "in 30 min" },
  { value: "60", label: "in 1 hour" },
  { value: "120", label: "in 2 hours" },
  { value: "240", label: "in 4 hours" },
] as const;
type NextCheck = (typeof NEXT_CHECK)[number]["value"];

function CheckForm({
  toStatus,
  onSubmit,
  onCancel,
  submitLabel,
}: {
  toStatus: Status | null;
  onSubmit: (c: { what_checked: string; what_found: string; next_check_minutes?: number }) => Promise<void>;
  onCancel: () => void;
  submitLabel: string;
}) {
  const [checked, setChecked] = useState("");
  const [found, setFound] = useState("");
  const [next, setNext] = useState<NextCheck>("120");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ready = checked.trim().length > 0 && found.trim().length > 0;

  return (
    <form
      className="animate-fade-up rounded-2xl bg-amber-soft/50 p-5 ring-1 ring-amber-line/80"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!ready || busy) return;
        setBusy(true);
        setError(null);
        try {
          await onSubmit({ what_checked: checked.trim(), what_found: found.trim(), next_check_minutes: toStatus === "monitoring" ? Number(next) : undefined });
        } catch (err) {
          setError(errorText(err));
        } finally {
          setBusy(false);
        }
      }}
    >
      <div className="text-sm font-medium text-ink">{toStatus ? <>Changing Status to {STATUS_LABEL[toStatus]} needs a Check</> : <>New Check</>}</div>
      <div className="mt-1 text-xs text-ink-2">Say what was checked and what was found, so the next shift doesn't inherit a mystery.</div>
      <div className="mt-4 grid gap-3">
        <label className="grid gap-1.5">
          <span className="text-xs font-medium text-ink-2">What was checked</span>
          <Input autoFocus value={checked} onChange={(e) => setChecked(e.target.value)} placeholder="e.g. Spindle bearing and tool holder runout" />
        </label>
        <label className="grid gap-1.5">
          <span className="text-xs font-medium text-ink-2">What was found</span>
          <Textarea value={found} onChange={(e) => setFound(e.target.value)} placeholder="e.g. Bearing worn, replaced it; vibration back to 2.1 mm/s" className="min-h-16" />
        </label>
        {toStatus === "monitoring" ? (
          <label className="flex items-center gap-3">
            <span className="text-xs font-medium text-ink-2">Next check</span>
            <Select label="Next check" value={next} onChange={setNext} options={NEXT_CHECK.map((o) => ({ value: o.value, label: o.label }))} className="h-8 w-36" />
          </label>
        ) : null}
      </div>
      {error ? <div className="mt-3 rounded-xl bg-crit-soft px-3 py-2 text-sm text-crit">{error}</div> : null}
      <div className="mt-4 flex items-center justify-end gap-2">
        {!ready ? <span className="mr-auto text-xs text-amber">Both fields are required.</span> : null}
        <Button variant="ghost" size="sm" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" size="sm" disabled={!ready || busy}>
          {busy ? "Saving…" : submitLabel}
        </Button>
      </div>
    </form>
  );
}

// ---- assignees --------------------------------------------------------------------

function AssigneePicker({ t, onSave }: { t: TicketSummary; onSave: (ids: number[]) => Promise<void> }) {
  const people = useApp((s) => s.people);
  const choices = useMemo(() => people.filter((p) => p.role !== "admin"), [people]);
  const [open, setOpen] = useState(false);
  const current = new Set(t.assignees.map((a) => a.id));

  const toggle = async (p: Person) => {
    const next = current.has(p.id) ? [...current].filter((id) => id !== p.id) : [...current, p.id];
    await onSave(next.filter((x): x is number => x !== null));
  };

  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      trigger={
        <button className="flex h-9 w-full cursor-pointer items-center gap-2 rounded-full bg-card pl-2 pr-3 ring-1 ring-line-2 transition-colors hover:bg-sunk" aria-label="Edit Assignees">
          {t.assignees.length ? <AvatarStack people={t.assignees} size={24} max={4} /> : <span className="pl-1.5 text-sm text-muted">Unassigned</span>}
          <span className="ml-1 flex-1 truncate text-left text-sm text-ink-2">{t.assignees.length ? t.assignees.map((a) => firstName(a.name)).join(", ") : ""}</span>
          <ChevronDown className="size-4 shrink-0 text-muted" />
        </button>
      }
    >
      <div className="px-2.5 pb-1.5 pt-1 text-xs font-medium text-muted">Assignees</div>
      <div className="max-h-80 overflow-auto scroll-thin">
        {choices.map((p) => {
          const on = current.has(p.id);
          return (
            <button key={p.id} onClick={() => void toggle(p)} className="flex w-full cursor-pointer items-center gap-2.5 rounded-xl px-2.5 py-2 text-left hover:bg-sunk">
              <Avatar person={p} size={28} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm text-ink">{p.name}</span>
                <span className="block truncate text-xs text-muted">
                  {p.role_label} · {p.shift === "day" ? "Day" : "Night"}
                  {p.on_shift_now ? " · on shift" : ""}
                </span>
              </span>
              <span className={cn("grid size-5 place-items-center rounded-md ring-1 transition-colors", on ? "bg-ink text-white ring-ink" : "ring-line-2")}>{on ? <CheckIcon className="size-3.5" /> : null}</span>
            </button>
          );
        })}
      </div>
    </Popover>
  );
}

// ---- the story ----------------------------------------------------------------------

type StoryItem =
  | { kind: "filed"; at: number }
  | { kind: "check"; at: number; check: Check }
  | { kind: "related"; at: number; ticket: TicketSummary }
  | { kind: "next"; at: number; overdue: boolean };

function Node({ tone, children }: { tone: "kb" | "ink" | "amber" | "ok" | "link" | "crit" | "wait"; children?: ReactNode }) {
  if (tone === "kb") return <Orb size={22} still className="mt-0.5" />;
  const cls = {
    ink: "bg-card ring-2 ring-ink",
    amber: "bg-amber-dot ring-4 ring-amber-soft",
    ok: "bg-ok-dot text-white ring-4 ring-ok-soft",
    link: "bg-card ring-2 ring-kb-violet",
    crit: "bg-crit ring-4 ring-crit-soft",
    wait: "bg-card ring-2 ring-faint",
  }[tone];
  return <span className={cn("mt-1 grid size-[14px] place-items-center rounded-full mx-[4px]", cls)}>{children}</span>;
}

function StoryRow({ node, last, children }: { node: ReactNode; last?: boolean; children: ReactNode }) {
  return (
    <li className="relative grid grid-cols-[22px_1fr] gap-4">
      {!last ? <span className="absolute bottom-[-4px] left-[10.5px] top-7 w-px bg-line-2" aria-hidden /> : null}
      <div className="flex justify-center">{node}</div>
      <div className="min-w-0 pb-7">{children}</div>
    </li>
  );
}

function When({ iso, now }: { iso: string | null; now: number }) {
  return (
    <span className="whitespace-nowrap text-xs text-muted tnum" title={iso ?? ""}>
      {istTime(iso, now)} IST · {ago(iso, now)}
    </span>
  );
}

function Transcript({ d }: { d: TicketDetail }) {
  const [open, setOpen] = useState(false);
  if (!d.transcript?.length) return null;
  return (
    <div className="mt-4">
      <button onClick={() => setOpen((o) => !o)} className="flex cursor-pointer items-center gap-1.5 text-[0.8125rem] font-medium text-ink-2 hover:text-ink" aria-expanded={open}>
        <ChevronDown className={cn("size-4 transition-transform duration-200", open ? "rotate-0" : "-rotate-90")} />
        {open ? "Hide" : "Show"} the original conversation with KB
        <span className="font-normal text-muted">· {d.transcript.length} lines</span>
      </button>
      {open ? (
        <div className="mt-3 grid animate-fade-up gap-2.5 rounded-2xl bg-sunk/60 p-4">
          {d.transcript.map((l, i) => (
            <div key={i} className={cn("flex items-start gap-2.5", l.who === "user" ? "" : "")}>
              {l.who === "kb" ? <Orb size={22} still /> : d.reporter ? <Avatar person={d.reporter} size={22} /> : <span className="size-[22px]" />}
              <div className={cn("max-w-[85%] rounded-2xl px-3.5 py-2 text-sm leading-relaxed", l.who === "kb" ? "bg-card text-ink-2 ring-1 ring-line" : "bg-card text-ink shadow-[0_1px_2px_rgba(0,0,0,.05)]")}>
                <span className="mr-1.5 text-xs font-medium text-muted">{l.who === "kb" ? "KB" : firstName(d.reporter?.name)}</span>
                {l.text}
                {l.lang && l.lang !== "en" ? <span className="ml-1.5 text-[0.7rem] uppercase text-faint">{l.lang}</span> : null}
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function Photos({ photos, compact = false }: { photos: { id: number; url: string }[]; compact?: boolean }) {
  const [view, setView] = useState<string | null>(null);
  if (!photos.length) return null;
  return (
    <div className={cn("flex flex-wrap gap-2.5", !compact && "mt-4")}>
      {photos.map((p) => (
        <button key={p.id} onClick={() => setView(p.url)} className={cn("group relative cursor-zoom-in", compact ? "h-20 w-28" : "size-24")} aria-label="Open photo">
          <span className="block size-full overflow-hidden rounded-2xl ring-1 ring-line">
            <img src={p.url} alt="Photo attached to the Ticket" className="size-full object-cover transition-transform duration-300 group-hover:scale-105" />
          </span>
        </button>
      ))}
      <Dialog open={view !== null} onOpenChange={(o) => !o && setView(null)} title="Photo">
        {view ? <img src={view} alt="Photo attached to the Ticket" className="max-h-[70vh] w-full rounded-2xl object-contain" /> : null}
      </Dialog>
    </div>
  );
}

/** Seeded snapshots are generated at seed time; pin the series so it ends when the Ticket was filed. */
function pinnedSeries(d: TicketDetail) {
  const s = d.telemetry_snapshot;
  if (!s) return [];
  const filedT = parse(d.created_at);
  const rawLast = s.series.at(-1)?.t;
  const shift = filedT && rawLast && Math.abs(filedT / 1000 - rawLast) > 600 ? filedT / 1000 - rawLast : 0;
  const series = shift ? s.series.map((p) => ({ ...p, t: p.t + shift })) : [...s.series];
  // the downsampled series can miss the last seconds; end it on the value frozen at filing
  const last = series.at(-1);
  if (filedT && last && filedT / 1000 - last.t > 1) series.push({ t: Math.round(filedT / 1000), v: s.current.vibration_mm_s, c: s.current.temperature_c });
  return series;
}

function Snapshot({ d }: { d: TicketDetail }) {
  const s = d.telemetry_snapshot;
  if (!s) return null;
  const cur = s.current;
  const b = s.vibration_band ?? band(cur.vibration_mm_s);
  const filedT = parse(d.created_at);
  const series = pinnedSeries(d);
  const last = series.at(-1)?.t;
  return (
    <div className="mt-4 rounded-2xl bg-card p-4 ring-1 ring-line">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
        <div className="text-xs font-medium text-ink-2">Telemetry Snapshot · {s.machine_code} · 30 min before filing</div>
        <div className="flex items-center gap-1.5 text-xs font-medium" style={{ color: b === "good" ? "#16803c" : b === "warning" ? "#a86400" : "#d92d20" }}>
          <span className="size-2 rounded-full" style={{ background: BAND_FILL[b] }} />
          {BAND_LABEL[b]} band
        </div>
      </div>
      <div className="mt-3 grid grid-cols-4 gap-3">
        <Fact label="Vibration" value={<span className="font-semibold tnum">{cur.vibration_mm_s.toFixed(1)} mm/s</span>} />
        <Fact label="Temperature" value={<span className="tnum">{cur.temperature_c.toFixed(1)} °C</span>} />
        <Fact label="Load" value={<span className="tnum">{Math.round(cur.load_pct)}%</span>} />
        <Fact label="Output vs target" value={s.target_so_far ? <span className="tnum">{cur.output_count} / {s.target_so_far}</span> : <span className="text-faint">No target</span>} />
      </div>
      {series.length > 1 ? (
        <div className="mt-3">
          <VibrationChart data={series} height={180} markerT={filedT && last && Math.abs(filedT / 1000 - last) < 120 ? last : undefined} />
          <div className="mt-1 text-[0.7rem] text-muted">Vibration velocity RMS (mm/s), ISO 10816 bands shaded</div>
        </div>
      ) : null}
    </div>
  );
}

/** A Related Ticket inside the story: its photos, its telemetry spike and how it was closed. */
function RelatedCard({ r, now, onOpen }: { r: TicketSummary; now: number; onOpen: (k: string) => void }) {
  const version = useApp((s) => s.detailVersion);
  const [rd, setRd] = useState<TicketDetail | null>(null);
  useEffect(() => {
    let alive = true;
    api.ticket(r.key).then((x) => alive && setRd(x)).catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [r.key, version]);
  const snap = rd?.telemetry_snapshot;
  // the last 12 minutes before filing, so a fresh spike reads clearly
  const all = rd ? pinnedSeries(rd) : [];
  const end = all.at(-1)?.t ?? 0;
  const recent = all.filter((p) => p.t >= end - 12 * 60);
  const peak = snap ? Math.max(...recent.map((p) => p.v), snap.current.vibration_mm_s) : null;
  const closing = rd?.checks.filter((c) => c.status_to === "closed").at(-1);
  return (
    <div className="mt-2.5 overflow-hidden rounded-2xl bg-card ring-1 ring-line-2">
      <button onClick={() => onOpen(r.key)} className="flex w-full cursor-pointer items-center gap-3 p-3.5 text-left transition-colors hover:bg-[#fbfbf9]">
        <span className="font-mono text-sm font-medium tnum">{r.key}</span>
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink">{r.title}</span>
        <SeverityBadge severity={r.severity} />
        <StatusBadge status={r.status} />
        <ArrowRight className="size-4 text-muted" />
      </button>
      {rd ? (
        <div className="grid gap-3 border-t border-line px-3.5 pb-3.5 pt-3">
          {rd.symptom ? <div className="text-sm leading-relaxed text-ink-2">“{rd.symptom}”</div> : null}
          {snap && recent.length > 1 ? (
            <div>
              <div className="flex items-baseline justify-between text-xs">
                <span className="text-muted">Vibration on {snap.machine_code}, 12 min before it was filed</span>
                {peak !== null ? (
                  <span className="flex items-center gap-1.5 font-medium" style={{ color: band(peak) === "alarm" ? "#d92d20" : band(peak) === "warning" ? "#a86400" : "#16803c" }}>
                    <span className="size-2 rounded-full" style={{ background: BAND_FILL[band(peak)] }} />
                    peak {peak.toFixed(1)} mm/s · {BAND_LABEL[band(peak)]}
                  </span>
                ) : null}
              </div>
              <VibrationChart data={recent} height={120} />
            </div>
          ) : null}
          {rd.photos.length ? <Photos photos={rd.photos} compact /> : null}
          {closing ? (
            <div className="flex items-start gap-2 rounded-xl bg-ok-soft/70 px-3 py-2 text-sm">
              <CheckIcon className="mt-0.5 size-4 shrink-0 text-ok" />
              <span className="text-ink">
                <span className="font-medium">Closed by {closing.author.name}</span>
                <span className="text-ink-2">
                  {" "}
                  · {istTime(closing.created_at, now)} IST: {closing.what_found || closing.what_checked}
                </span>
              </span>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function CheckEntry({ c, now, showNext }: { c: Check; now: number; showNext: boolean }) {
  const who = c.author.name;
  return (
    <div>
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
        <Avatar person={c.author} size={22} />
        <span className="text-sm font-medium text-ink">{who}</span>
        <span className="text-xs text-muted">{ROLE[c.author.role] ?? ""}</span>
        <span className="ml-auto">
          <When iso={c.created_at} now={now} />
        </span>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <span className="text-[0.8125rem] font-medium text-ink-2">{c.status_to === "closed" ? "Closed it with a Check" : "Check"}</span>
        {c.status_from && c.status_to ? (
          <span className="flex items-center gap-1.5">
            <StatusBadge status={c.status_from} className="h-5 px-2 text-[0.7rem]" />
            <ArrowRight className="size-3.5 text-muted" />
            <StatusBadge status={c.status_to} className="h-5 px-2 text-[0.7rem]" />
          </span>
        ) : null}
        {c.unclear ? <UnclearBadge className="h-5 px-2 text-[0.7rem]" label="Unclear Check" /> : null}
      </div>
      {c.unclear ? (
        <div className="mt-3 rounded-2xl bg-amber-soft p-4 ring-1 ring-amber-line">
          <div className="text-[0.9375rem] leading-relaxed text-ink">
            {firstName(who)} said <span className="font-semibold">“{c.what_found || c.what_checked || "…"}”</span> — without saying what was checked or what was found.
          </div>
          <div className="mt-1.5 text-xs text-amber">Recorded as given and flagged forever, so no later shift mistakes it for a fix.</div>
        </div>
      ) : (
        <div className={cn("mt-3 grid grid-cols-2 gap-4 rounded-2xl p-4", c.status_to === "closed" ? "bg-ok-soft/70 ring-1 ring-ok/15" : "bg-sunk/60")}>
          <Fact label="What was checked" value={<span className="leading-relaxed">{c.what_checked}</span>} />
          <Fact label="What was found" value={<span className="leading-relaxed">{c.what_found}</span>} />
        </div>
      )}
      {showNext && c.next_check_at && c.status_to === "monitoring" ? <div className="mt-2 text-xs text-muted">Next check set for {istTime(c.next_check_at, now)} IST</div> : null}
    </div>
  );
}

function Story({ d, now, onOpen }: { d: TicketDetail; now: number; onOpen: (k: string) => void }) {
  const items = useMemo<StoryItem[]>(() => {
    const list: StoryItem[] = [{ kind: "filed", at: parse(d.created_at) ?? 0 }];
    for (const c of d.checks) list.push({ kind: "check", at: parse(c.created_at) ?? 0, check: c });
    for (const r of d.related) list.push({ kind: "related", at: parse(r.created_at) ?? 0, ticket: r });
    list.sort((a, b) => a.at - b.at);
    if (d.status === "monitoring" && d.next_check_at) list.push({ kind: "next", at: parse(d.next_check_at) ?? 0, overdue: isOverdue(d, now) });
    return list;
  }, [d, now]);

  const filedByVoice = d.transcript?.length > 0;
  return (
    <ol>
      {items.map((it, i) => {
        const last = i === items.length - 1;
        switch (it.kind) {
          case "filed":
            return (
              <StoryRow key="filed" last={last} node={filedByVoice ? <Node tone="kb" /> : <Node tone="ink" />}>
                <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                  {d.reporter ? <Avatar person={d.reporter} size={22} /> : null}
                  <span className="text-sm font-medium text-ink">{d.reporter?.name ?? "Someone"}</span>
                  <span className="text-xs text-muted">{d.reporter ? ROLE[d.reporter.role] : ""}</span>
                  <span className="ml-auto">
                    <When iso={d.created_at} now={now} />
                  </span>
                </div>
                <div className="mt-2 text-[0.8125rem] font-medium text-ink-2">{filedByVoice ? "Reported it to KB" : "Filed the Ticket"}</div>
                <blockquote className="mt-2 text-[1.0625rem] leading-relaxed text-ink">“{d.symptom || d.title}”</blockquote>
                <div className="mt-4 grid grid-cols-3 gap-4">
                  <Fact label="Since" value={given(d.since_text)} />
                  <Fact label="Context" value={given(d.context)} />
                  <Fact label="Machine running" value={d.machine_running === null ? <span className="text-faint">Not given</span> : d.machine_running ? "Yes, still running" : "No, stopped"} />
                </div>
                <Photos photos={d.photos} />
                <Snapshot d={d} />
                <Transcript d={d} />
              </StoryRow>
            );
          case "check": {
            const c = it.check;
            const tone = c.unclear ? "amber" : c.status_to === "closed" ? "ok" : "ink";
            return (
              <StoryRow key={`c${c.id}`} last={last} node={<Node tone={tone}>{tone === "ok" ? <CheckIcon className="size-2.5" strokeWidth={3.5} /> : null}</Node>}>
                <CheckEntry c={c} now={now} showNext={c.next_check_at !== d.next_check_at || d.status !== "monitoring"} />
              </StoryRow>
            );
          }
          case "related": {
            const r = it.ticket;
            return (
              <StoryRow key={`r${r.key}`} last={last} node={<Node tone="link" />}>
                <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                  <Link2 className="size-4 text-kb-violet" />
                  <span className="text-sm font-medium text-ink">Related Ticket {r.reporter ? `filed by ${r.reporter.name}` : "filed"}</span>
                  <span className="ml-auto">
                    <When iso={r.created_at} now={now} />
                  </span>
                </div>
                <RelatedCard r={r} now={now} onOpen={onOpen} />
              </StoryRow>
            );
          }
          case "next":
            return (
              <StoryRow key="next" last node={<Node tone={it.overdue ? "crit" : "wait"} />}>
                {it.overdue ? (
                  <div className="text-sm">
                    <span className="font-semibold text-crit">Next check overdue by {duration(now - it.at)}</span>
                    <span className="text-ink-2">
                      {" "}
                      · was due {istTime(d.next_check_at, now)} IST{d.monitoring_owner ? `, owner ${d.monitoring_owner.name}` : ""}
                    </span>
                    <div className="mt-1 text-xs text-muted">Monitoring is not resolved. Someone needs to look again.</div>
                  </div>
                ) : (
                  <div className="text-sm text-ink-2">
                    Next check due {istTime(d.next_check_at, now)} IST{d.monitoring_owner ? ` · owner ${d.monitoring_owner.name}` : ""}
                  </div>
                )}
              </StoryRow>
            );
        }
      })}
    </ol>
  );
}

// ---- the sheet ----------------------------------------------------------------------

function TitleEditor({ value, onSave }: { value: string; onSave: (v: string) => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  if (!editing)
    return (
      <button onClick={() => setEditing(true)} className="group -mx-2 flex cursor-text items-start gap-2 rounded-xl px-2 py-1 text-left hover:bg-sunk/70" aria-label="Edit title">
        <h2 className="text-[1.75rem] font-semibold leading-tight tracking-[-0.02em] text-ink">{value}</h2>
        <Pencil className="mt-2.5 size-4 shrink-0 text-faint opacity-0 transition-opacity group-hover:opacity-100" />
      </button>
    );
  return (
    <form
      className="flex items-center gap-2"
      onSubmit={async (e) => {
        e.preventDefault();
        if (draft.trim() && draft.trim() !== value) await onSave(draft.trim());
        setEditing(false);
      }}
    >
      <Input autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} className="h-12 text-xl font-semibold" onKeyDown={(e) => e.key === "Escape" && (setDraft(value), setEditing(false))} />
      <Button type="submit" size="sm">
        Save
      </Button>
      <Button size="sm" variant="ghost" onClick={() => (setDraft(value), setEditing(false))}>
        Cancel
      </Button>
    </form>
  );
}

function Description({ value, onSave }: { value: string; onSave: (v: string) => Promise<void> }) {
  const [draft, setDraft] = useState(value);
  const [busy, setBusy] = useState(false);
  useEffect(() => setDraft(value), [value]);
  const dirty = draft !== value;
  return (
    <div>
      <Textarea value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Add a description for the next shift…" className="min-h-20 bg-sunk/40" aria-label="Description" />
      {dirty ? (
        <div className="mt-2 flex justify-end gap-2">
          <Button size="sm" variant="ghost" onClick={() => setDraft(value)}>
            Discard
          </Button>
          <Button
            size="sm"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await onSave(draft);
              } finally {
                setBusy(false);
              }
            }}
          >
            Save description
          </Button>
        </div>
      ) : null}
    </div>
  );
}

export function TicketSheet() {
  const openKey = useApp((s) => s.openKey);
  const openTicket = useApp((s) => s.openTicket);
  const [d, refetch] = useDetail(openKey);
  const now = useNow(15_000);
  const [pendingStatus, setPendingStatus] = useState<Status | null>(null);
  const [addingCheck, setAddingCheck] = useState(false);

  useEffect(() => {
    setPendingStatus(null);
    setAddingCheck(false);
  }, [openKey]);

  const patch = async (body: TicketPatch, ok: string) => {
    if (!d) return;
    try {
      // the table row, feed and metrics update from the /ws ticket.updated event
      await api.patchTicket(d.key, body);
      refetch();
      toast.success(ok);
    } catch (e) {
      toast.error(`Couldn't update ${d.key}`, { description: errorText(e) });
      throw e;
    }
  };

  return (
    <Sheet open={openKey !== null} onOpenChange={(o) => !o && openTicket(null)} title={openKey ?? "Ticket"}>
      {!d ? (
        <div className="grid flex-1 place-items-center text-sm text-muted">Loading {openKey}…</div>
      ) : (
        <div className="flex-1 overflow-y-auto scroll-thin [scrollbar-gutter:stable]">
          {/* header */}
          <header className="px-8 pb-6 pt-7">
            <div className="flex flex-wrap items-center gap-2.5 pr-12">
              <span className="font-mono text-[0.95rem] font-medium text-ink-2 tnum">{d.key}</span>
              <MachineChip code={d.machine_code} />
              <span className="text-sm text-muted">{d.machine_name}</span>
              <span className="mx-1 h-4 w-px bg-line-2" />
              <SeverityBadge severity={d.severity} />
              <TicketStatusBadges t={d} now={now} />
            </div>
            <div className="mt-3">
              <TitleEditor value={d.title} onSave={(title) => patch({ title }, "Title saved")} />
            </div>
            <div className="mt-2 text-sm text-ink-2">
              Reported by {d.reporter?.name ?? "someone"} · {istTime(d.created_at, now)} IST ·{" "}
              {d.closed_at ? `closed ${istTime(d.closed_at, now)} IST, after ${duration(parse(d.closed_at)! - parse(d.created_at)!)}` : `open for ${duration(now - parse(d.created_at)!)}`}
            </div>
            {d.related.length ? (
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <span className="flex items-center gap-1 text-xs text-muted">
                  <Link2 className="size-3.5" /> Related
                </span>
                {d.related.map((r) => (
                  <KeyChip key={r.key} k={r.key} onClick={() => openTicket(r.key)} />
                ))}
              </div>
            ) : null}
            <div className="mt-5 grid grid-cols-[1fr_1fr_1.5fr] gap-3">
              <label className="grid gap-1.5">
                <span className="text-xs font-medium text-muted">Status</span>
                <Select
                  label="Status"
                  value={pendingStatus ?? d.status}
                  onChange={(v) => setPendingStatus(v === d.status ? null : v)}
                  options={STATUSES.map((s) => ({ value: s, label: STATUS_LABEL[s] }))}
                  className="w-full"
                />
              </label>
              <label className="grid gap-1.5">
                <span className="text-xs font-medium text-muted">Severity</span>
                <Select<Severity>
                  label="Severity"
                  value={d.severity}
                  onChange={(severity) => void patch({ severity }, `Severity set to ${SEVERITY_LABEL[severity]}`).catch(() => undefined)}
                  options={SEVERITIES.map((s) => ({ value: s, label: SEVERITY_LABEL[s] }))}
                  className="w-full"
                />
              </label>
              <div className="grid gap-1.5">
                <span className="flex items-center gap-1 text-xs font-medium text-muted">
                  <Users className="size-3.5" /> Assignees
                </span>
                <AssigneePicker t={d} onSave={(ids) => patch({ assignee_ids: ids }, "Assignees updated").catch(() => undefined)} />
              </div>
            </div>
            {pendingStatus ? (
              <div className="mt-4">
                <CheckForm
                  key={pendingStatus}
                  toStatus={pendingStatus}
                  submitLabel={`Change to ${STATUS_LABEL[pendingStatus]}`}
                  onCancel={() => setPendingStatus(null)}
                  onSubmit={async (check) => {
                    await patch({ status: pendingStatus, check }, `${d.key} moved to ${STATUS_LABEL[pendingStatus]}`);
                    setPendingStatus(null);
                  }}
                />
              </div>
            ) : null}
          </header>

          <div className="grid gap-5 px-8 pb-10">
            {/* the story */}
            <Section
              title="What happened"
              aside={
                !addingCheck ? (
                  <Button size="sm" variant="outline" onClick={() => setAddingCheck(true)}>
                    <Plus /> Add Check
                  </Button>
                ) : null
              }
            >
              {addingCheck ? (
                <div className="mb-6">
                  <CheckForm
                    toStatus={null}
                    submitLabel="Add Check"
                    onCancel={() => setAddingCheck(false)}
                    onSubmit={async (check) => {
                      await api.addCheck(d.key, check);
                      refetch();
                      setAddingCheck(false);
                      toast.success(`Check added to ${d.key}`);
                    }}
                  />
                </div>
              ) : null}
              <Story d={d} now={now} onOpen={openTicket} />
            </Section>

            <Section title="Description">
              <Description value={d.description} onSave={(description) => patch({ description }, "Description saved")} />
            </Section>
          </div>
        </div>
      )}
    </Sheet>
  );
}
