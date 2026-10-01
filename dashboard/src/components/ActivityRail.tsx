import { CircleCheck, FilePlus2, HelpCircle, LogIn, PanelRightClose, Sparkles, Stethoscope, Pencil } from "lucide-react";
import { ago, istTime } from "@/lib/format";
import { useApp, type FeedLine, type FeedTone } from "@/lib/store";
import { useNow } from "@/lib/useNow";
import { cn } from "@/lib/utils";

const TONE: Record<FeedTone, { icon: typeof CircleCheck; cls: string }> = {
  filed: { icon: FilePlus2, cls: "bg-ink text-white" },
  closed: { icon: CircleCheck, cls: "bg-ok-soft text-ok" },
  unclear: { icon: HelpCircle, cls: "bg-amber-soft text-amber" },
  status: { icon: Stethoscope, cls: "bg-sunk text-ink-2" },
  shift: { icon: LogIn, cls: "bg-sunk text-ink-2" },
  demo: { icon: Sparkles, cls: "bg-[linear-gradient(135deg,#e7efff,#f3ecff,#fdeaf5)] text-[#6b5bd6]" },
  neutral: { icon: Pencil, cls: "bg-sunk text-muted" },
};

function Line({ l, now, fresh }: { l: FeedLine; now: number; fresh: boolean }) {
  const openTicket = useApp((s) => s.openTicket);
  const t = TONE[l.tone];
  const body = (
    <>
      <span className={cn("mt-0.5 grid size-7 shrink-0 place-items-center rounded-full", t.cls)}>
        <t.icon className="size-3.5" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-baseline gap-2">
          <span className="min-w-0 flex-1 text-[0.8125rem] font-medium leading-snug text-ink">{l.text}</span>
          <span className="shrink-0 text-[0.7rem] text-muted tnum" title={`${istTime(l.at, now)} IST`}>
            {ago(l.at, now).replace(" ago", "")}
          </span>
        </span>
        {l.tone === "unclear" ? (
          <span className="mt-1 inline-flex items-center gap-1 rounded-full bg-amber-soft px-2 py-0.5 text-[0.7rem] font-medium text-amber ring-1 ring-amber-line">Unclear · “{l.note}”</span>
        ) : l.note ? (
          <span className="mt-0.5 line-clamp-2 block text-xs leading-snug text-muted">{l.note}</span>
        ) : null}
      </span>
    </>
  );
  const cls = cn("flex w-full gap-3 rounded-2xl px-3 py-2.5 text-left", fresh && "animate-fade-up", l.ticketKey && "cursor-pointer transition-colors hover:bg-sunk/70");
  return l.ticketKey ? (
    <button className={cls} onClick={() => openTicket(l.ticketKey ?? null)}>
      {body}
    </button>
  ) : (
    <div className={cls}>{body}</div>
  );
}

export function ActivityRail({ onClose }: { onClose: () => void }) {
  const feed = useApp((s) => s.feed);
  const now = useNow(15_000);
  return (
    <aside className="flex h-full flex-col rounded-3xl bg-card shadow-card" aria-label="Activity">
      <div className="flex items-center gap-2 px-5 pb-2 pt-4">
        <h2 className="text-[0.78rem] font-semibold uppercase tracking-[0.07em] text-muted">Activity</h2>
        <button onClick={onClose} className="ml-auto grid size-8 cursor-pointer place-items-center rounded-full text-muted hover:bg-sunk hover:text-ink" aria-label="Hide activity">
          <PanelRightClose className="size-4" />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-2 pb-3 scroll-thin">
        {feed.map((l) => (
          <Line key={l.id} l={l} now={now} fresh={Date.now() - Date.parse(l.at) < 4000} />
        ))}
        {!feed.length ? <div className="px-3 py-10 text-center text-sm text-muted">Nothing yet. Filings, Checks and Shifts appear here live.</div> : null}
      </div>
    </aside>
  );
}
