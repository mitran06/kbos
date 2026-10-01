import { HelpCircle, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Avatar, AvatarStack, MachineChip, SeverityBadge, TicketStatusBadges } from "@/components/kb";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { ago, checkText, firstName, isOverdue, sortTickets } from "@/lib/format";
import { useApp } from "@/lib/store";
import type { Metrics, Status, TicketSummary } from "@/lib/types";
import { useNow } from "@/lib/useNow";
import { cn } from "@/lib/utils";

type StatusFilter = "active" | Status | "all";
const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "active", label: "Active" },
  { value: "open", label: "Open" },
  { value: "in_progress", label: "In Progress" },
  { value: "monitoring", label: "Monitoring" },
  { value: "closed", label: "Closed" },
];

function Kpi({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: "crit" | "amber" }) {
  return (
    <div className="rounded-2xl bg-card px-5 py-4 shadow-card">
      <div className="flex items-center gap-2 text-[0.8125rem] font-medium text-ink-2">
        {tone ? <span className={cn("size-2 rounded-full", tone === "crit" ? "bg-crit" : "bg-amber-dot")} /> : null}
        {label}
      </div>
      <div className={cn("mt-2 text-[2.1rem] font-semibold leading-none tracking-tight tnum", tone === "crit" && value !== "0" && "text-crit", tone === "amber" && value !== "0" && "text-amber")}>{value}</div>
      {sub ? <div className="mt-2 text-xs text-muted">{sub}</div> : null}
    </div>
  );
}

function KpiRow({ m }: { m: Metrics | null }) {
  const mttc = m?.mean_time_to_close_h;
  return (
    <div className="grid grid-cols-4 gap-4">
      <Kpi label="Open" value={m ? String(m.open) : "–"} sub="Tickets not closed" />
      <Kpi label="Critical" value={m ? String(m.critical) : "–"} sub="Production stopped or safety risk" tone="crit" />
      <Kpi label="Overdue monitoring" value={m ? String(m.overdue_monitoring) : "–"} sub="Next check time has passed" tone="amber" />
      <Kpi label="Avg time to close" value={mttc == null ? "–" : mttc < 1 ? `${Math.round(mttc * 60)}m` : `${mttc.toFixed(1)}h`} sub={m ? `${m.closed_7d} closed in the last 7 days` : undefined} />
    </div>
  );
}

function Row({ t, now, onOpen }: { t: TicketSummary; now: number; onOpen: () => void }) {
  const ref = useRef<HTMLTableRowElement>(null);
  const flashAt = useApp((s) => s.flash[t.key]);
  const freshAt = useApp((s) => s.fresh[t.key]);
  const mounted = useRef(false);

  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      // a ticket that just arrived over /ws slides in
      if (freshAt && Date.now() - freshAt < 2000) {
        ref.current?.animate(
          [
            { opacity: 0, transform: "translateY(-12px)" },
            { opacity: 1, transform: "none" },
          ],
          { duration: 420, easing: "cubic-bezier(0.22, 1, 0.36, 1)" },
        );
      } else return;
    }
    if (!flashAt || Date.now() - flashAt > 2000) return;
    ref.current?.animate(
      [{ backgroundColor: "rgba(169, 139, 250, 0.22)" }, { backgroundColor: "rgba(169, 139, 250, 0.14)", offset: 0.25 }, { backgroundColor: "rgba(169, 139, 250, 0)" }],
      { duration: 1600, easing: "ease-out" },
    );
  }, [flashAt, freshAt]);

  const lc = t.last_check;
  const closed = t.status === "closed";
  return (
    <tr
      ref={ref}
      onClick={onOpen}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onOpen())}
      tabIndex={0}
      data-key={t.key}
      className={cn("group cursor-pointer border-t border-line transition-colors hover:bg-[#fbfbf9] focus-visible:bg-[#fbfbf9] outline-none", closed && "text-ink-2")}
    >
      <td className="py-3.5 pl-5 pr-3 align-middle">
        <span className={cn("font-mono text-[0.84rem] font-medium tnum", closed ? "text-muted" : "text-ink")}>{t.key}</span>
      </td>
      <td className="px-3 align-middle">
        <MachineChip code={t.machine_code} />
      </td>
      <td className="max-w-0 px-3 align-middle">
        <div className={cn("line-clamp-2 text-[0.9375rem] font-medium leading-snug", closed && "font-normal")}>{t.title}</div>
        <div className="mt-0.5 truncate text-xs text-muted">
          {t.machine_name}
          {t.related_keys.length ? ` · Related ${t.related_keys.join(", ")}` : ""}
          {t.photo_count ? ` · ${t.photo_count} photo${t.photo_count > 1 ? "s" : ""}` : ""}
        </div>
      </td>
      <td className="px-3 align-middle">
        <SeverityBadge severity={t.severity} />
      </td>
      <td className="px-3 align-middle">
        <TicketStatusBadges t={t} now={now} />
      </td>
      <td className="px-3 align-middle">
        <AvatarStack people={t.assignees} size={28} />
      </td>
      <td className="hidden px-3 align-middle 2xl:table-cell">
        {t.reporter ? (
          <span className="flex items-center gap-2 text-[0.8125rem] text-ink-2">
            <Avatar person={t.reporter} size={22} />
            {firstName(t.reporter.name)}
          </span>
        ) : null}
      </td>
      <td className="whitespace-nowrap px-3 align-middle text-[0.8125rem] text-ink-2 tnum">{ago(t.created_at, now).replace(" ago", "")}</td>
      <td className="max-w-0 py-3 pl-3 pr-5 align-middle">
        {lc ? (
          <div className="min-w-0">
            <div className={cn("flex items-center gap-1.5 truncate text-[0.8125rem]", lc.unclear ? "text-amber" : "text-ink-2")}>
              {lc.unclear ? <HelpCircle className="size-3.5 shrink-0" /> : null}
              <span className="truncate">{lc.unclear ? `“${lc.what_found || lc.what_checked || "nothing said"}”` : checkText(lc)}</span>
            </div>
            <div className="mt-0.5 truncate text-xs text-muted">
              {firstName(lc.author.name)} · {ago(lc.created_at, now)}
            </div>
          </div>
        ) : (
          <span className="text-[0.8125rem] text-faint">No checks yet</span>
        )}
      </td>
    </tr>
  );
}

export function TicketsView() {
  const tickets = useApp((s) => s.tickets);
  const loaded = useApp((s) => s.ticketsLoaded);
  const metrics = useApp((s) => s.metrics);
  const openTicket = useApp((s) => s.openTicket);
  const now = useNow(15_000);
  const [status, setStatus] = useState<StatusFilter>("all");
  const [machine, setMachine] = useState<string>("all");
  const [q, setQ] = useState("");

  const all = useMemo(() => Object.values(tickets), [tickets]);
  const machines = useMemo(() => [...new Set(all.map((t) => t.machine_code))].sort(), [all]);
  const counts = useMemo(() => {
    const c: Record<StatusFilter, number> = { active: 0, open: 0, in_progress: 0, monitoring: 0, closed: 0, all: all.length };
    for (const t of all) {
      c[t.status] += 1;
      if (t.status !== "closed") c.active += 1;
    }
    return c;
  }, [all]);

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return sortTickets(
      all.filter(
        (t) =>
          (status === "all" || (status === "active" ? t.status !== "closed" : t.status === status)) &&
          (machine === "all" || t.machine_code === machine) &&
          (!needle || `${t.key} ${t.title} ${t.machine_code} ${t.machine_name} ${t.assignees.map((a) => a.name).join(" ")} ${t.reporter?.name ?? ""}`.toLowerCase().includes(needle)),
      ),
      now,
    );
  }, [all, status, machine, q, now]);

  const overdue = all.filter((t) => isOverdue(t, now)).length;

  return (
    <div className="flex flex-col gap-6">
      <KpiRow m={metrics ? { ...metrics, overdue_monitoring: overdue } : null} />

      <section className="rounded-3xl bg-card shadow-card">
        <div className="flex flex-wrap items-center gap-3 px-5 pb-4 pt-5">
          <div role="tablist" aria-label="Filter by Status" className="flex items-center gap-1 rounded-full bg-sunk p-1">
            {STATUS_FILTERS.map((f) => (
              <button
                key={f.value}
                role="tab"
                aria-selected={status === f.value}
                onClick={() => setStatus(f.value)}
                className={cn(
                  "h-8 cursor-pointer rounded-full px-3.5 text-[0.8125rem] font-medium transition-[background-color,color,box-shadow] duration-150",
                  status === f.value ? "bg-card text-ink shadow-[0_1px_3px_rgba(0,0,0,.08)]" : "text-ink-2 hover:text-ink",
                )}
              >
                {f.label}
                <span className={cn("ml-1.5 tnum", status === f.value ? "text-muted" : "text-faint")}>{counts[f.value]}</span>
              </button>
            ))}
          </div>
          <Select
            label="Filter by Machine"
            value={machine}
            onChange={setMachine}
            className="w-40"
            options={[{ value: "all", label: "All machines" }, ...machines.map((m) => ({ value: m, label: `Machine ${m}` }))]}
          />
          <div className="relative ml-auto w-72">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search Tickets, Machines, people" className="h-9 rounded-full pl-9 pr-8" aria-label="Search Tickets" />
            {q ? (
              <button onClick={() => setQ("")} aria-label="Clear search" className="absolute right-2.5 top-1/2 -translate-y-1/2 cursor-pointer text-muted hover:text-ink">
                <X className="size-4" />
              </button>
            ) : null}
          </div>
        </div>

        <table className="w-full table-fixed border-collapse text-left">
          <colgroup>
            <col className="w-[7rem]" />
            <col className="w-[5.25rem]" />
            <col />
            <col className="w-[7rem]" />
            <col className="w-[16.5rem]" />
            <col className="w-[6.5rem]" />
            <col className="hidden w-[8rem] 2xl:table-column" />
            <col className="w-[5.25rem]" />
            <col className="w-[14rem] min-[1700px]:w-[17rem]" />
          </colgroup>
          <thead>
            <tr className="text-[0.75rem] font-medium uppercase tracking-[0.06em] text-muted">
              <th className="pb-2.5 pl-5 pr-3 font-medium">Ticket</th>
              <th className="px-3 pb-2.5 font-medium">Machine</th>
              <th className="px-3 pb-2.5 font-medium">Title</th>
              <th className="px-3 pb-2.5 font-medium">Severity</th>
              <th className="px-3 pb-2.5 font-medium">Status</th>
              <th className="px-3 pb-2.5 font-medium">Assignees</th>
              <th className="hidden px-3 pb-2.5 font-medium 2xl:table-cell">Reporter</th>
              <th className="px-3 pb-2.5 font-medium">Age</th>
              <th className="pb-2.5 pl-3 pr-5 font-medium">Last Check</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((t) => (
              <Row key={t.key} t={t} now={now} onOpen={() => openTicket(t.key)} />
            ))}
          </tbody>
        </table>
        {loaded && rows.length === 0 ? (
          <div className="border-t border-line px-5 py-14 text-center text-sm text-muted">
            No Tickets match these filters.{" "}
            <button
              className="cursor-pointer font-medium text-ink underline decoration-line-2 underline-offset-4 hover:decoration-ink"
              onClick={() => {
                setStatus("all");
                setMachine("all");
                setQ("");
              }}
            >
              Show all Tickets
            </button>
          </div>
        ) : null}
        {!loaded ? <div className="border-t border-line px-5 py-14 text-center text-sm text-muted">Loading Tickets…</div> : null}
        <div className="h-2" />
      </section>
    </div>
  );
}
