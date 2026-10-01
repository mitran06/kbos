import { ChevronDown } from "lucide-react";
import { useEffect, useState } from "react";
import { Avatar } from "@/components/kb";
import { api } from "@/lib/api";
import { duration, istTime, parse } from "@/lib/format";
import { useApp } from "@/lib/store";
import type { ShiftSession } from "@/lib/types";
import { useNow } from "@/lib/useNow";
import { cn } from "@/lib/utils";

function ShiftRow({ s, now }: { s: ShiftSession; now: number }) {
  const people = useApp((st) => st.people);
  const p = people.find((x) => x.id === s.person_id);
  const [open, setOpen] = useState(false);
  const start = parse(s.started_at);
  const end = parse(s.ended_at);
  const live = !s.ended_at;
  return (
    <li className="border-t border-line first:border-t-0">
      <div className="grid grid-cols-[16rem_12rem_1fr_auto] items-start gap-6 px-6 py-4">
        <div className="flex items-center gap-3">
          {p ? <Avatar person={p} size={34} /> : null}
          <div className="min-w-0">
            <div className="truncate text-[0.9375rem] font-medium">{s.person_name ?? "Unknown"}</div>
            <div className="text-xs text-muted">{p ? `${p.role_label} · ${p.shift === "day" ? "Day" : "Night"}` : ""}</div>
          </div>
        </div>
        <div className="text-sm tnum">
          <div className="text-ink">
            {istTime(s.started_at, now)} – {live ? "now" : istTime(s.ended_at, now).replace(/^(Yesterday|\d+ \w+) /, "")}
          </div>
          <div className="text-xs text-muted">{start ? duration((end ?? now) - start) : ""}</div>
        </div>
        <div className="min-w-0 text-sm leading-relaxed">
          {live ? (
            <span className="inline-flex items-center gap-1.5 text-ok">
              <span className="size-2 animate-breathe rounded-full bg-ok-dot" /> On shift now
            </span>
          ) : s.handover_summary ? (
            <>
              <span className="mr-1.5 text-xs font-medium text-muted">Handover</span>
              <span className="text-ink">{s.handover_summary}</span>
            </>
          ) : (
            <span className="text-faint">No Handover recorded</span>
          )}
        </div>
        {s.brief_text ? (
          <button onClick={() => setOpen((o) => !o)} className="flex cursor-pointer items-center gap-1 text-xs font-medium text-ink-2 hover:text-ink" aria-expanded={open}>
            Shift Brief <ChevronDown className={cn("size-3.5 transition-transform", open ? "" : "-rotate-90")} />
          </button>
        ) : (
          <span className="text-xs text-faint">No Shift Brief</span>
        )}
      </div>
      {open && s.brief_text ? <div className="mx-6 mb-4 animate-fade-up rounded-2xl bg-sunk/60 px-5 py-4 text-sm leading-relaxed text-ink-2">{s.brief_text}</div> : null}
    </li>
  );
}

export function ShiftsView() {
  const version = useApp((s) => s.shiftsVersion);
  const epoch = useApp((s) => s.epoch);
  const [rows, setRows] = useState<ShiftSession[] | null>(null);
  const now = useNow(30_000);
  useEffect(() => {
    let alive = true;
    api.shifts(40).then((r) => alive && setRows(r)).catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [version, epoch]);
  return (
    <section className="rounded-3xl bg-card shadow-card">
      <div className="flex items-baseline justify-between px-6 pb-3 pt-5">
        <h2 className="text-[0.78rem] font-semibold uppercase tracking-[0.07em] text-muted">Handover log</h2>
        <span className="text-xs text-muted">Newest first · times in IST</span>
      </div>
      <ul className="border-t border-line">
        {rows?.map((s) => <ShiftRow key={s.id} s={s} now={now} />)}
        {rows && !rows.length ? <li className="px-6 py-12 text-center text-sm text-muted">No Shifts yet. A Shift starts when someone taps their face in the app.</li> : null}
        {!rows ? <li className="px-6 py-12 text-center text-sm text-muted">Loading Shifts…</li> : null}
      </ul>
    </section>
  );
}
