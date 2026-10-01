import { PanelRightOpen } from "lucide-react";
import { useEffect, useState } from "react";
import { Toaster } from "sonner";
import { ActivityRail } from "@/components/ActivityRail";
import { Orb } from "@/components/kb";
import { istClock } from "@/lib/format";
import { startLive, useConn } from "@/lib/live";
import { useMachines } from "@/lib/machines";
import { TABS, useApp, type Tab } from "@/lib/store";
import { useNow } from "@/lib/useNow";
import { cn } from "@/lib/utils";
import { DemoView } from "@/views/DemoView";
import { GlossaryView } from "@/views/GlossaryView";
import { MachinesView } from "@/views/MachinesView";
import { ShiftsView } from "@/views/ShiftsView";
import { TicketSheet } from "@/views/TicketSheet";
import { TicketsView } from "@/views/TicketsView";

const TAB_LABEL: Record<Tab, string> = { tickets: "Tickets", machines: "Machines", shifts: "Shifts", glossary: "Glossary", demo: "Demo" };

function tabFromHash(): Tab {
  const h = window.location.hash.replace("#", "");
  return (TABS as string[]).includes(h) ? (h as Tab) : "tickets";
}

function ConnDot() {
  const state = useConn((s) => s.state);
  const label = state === "live" ? "Live" : state === "connecting" ? "Connecting" : "Reconnecting";
  return (
    <span className="flex items-center gap-2 text-[0.8125rem] text-ink-2" title={state === "live" ? "Connected to the live event stream" : "Trying to reach the server"}>
      <span className="relative grid size-2.5 place-items-center">
        {state === "live" ? <span className="absolute inset-0 animate-breathe rounded-full bg-ok-dot/40" /> : null}
        <span className={cn("size-2 rounded-full", state === "live" ? "bg-ok-dot" : state === "connecting" ? "bg-faint" : "bg-amber-dot")} />
      </span>
      {label}
    </span>
  );
}

function Clock() {
  const now = useNow(10_000);
  return <span className="text-[0.8125rem] text-muted tnum">{istClock(now)} IST</span>;
}

export default function App() {
  const tab = useApp((s) => s.tab);
  const setTab = useApp((s) => s.setTab);
  const epoch = useApp((s) => s.epoch);
  const machinesVersion = useApp((s) => s.machinesVersion);
  const [railOpen, setRailOpen] = useState(() => window.innerWidth >= 1600);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    setTab(tabFromHash());
    const onHash = () => setTab(tabFromHash());
    window.addEventListener("hashchange", onHash);
    useApp
      .getState()
      .loadAll()
      .catch((e: unknown) => setLoadError(e instanceof Error ? e.message : String(e)));
    startLive();
    return () => window.removeEventListener("hashchange", onHash);
  }, [setTab]);

  // every reset / reconnect: reseed the telemetry rings and Machines
  useEffect(() => {
    if (epoch === 0) return;
    setLoadError(null);
    void useMachines.getState().load().then(() => useMachines.getState().seedRings()).catch(() => undefined);
  }, [epoch]);

  // ticket changes move open-ticket keys between Machines
  useEffect(() => {
    if (machinesVersion === 0) return;
    const id = setTimeout(() => void useMachines.getState().load().catch(() => undefined), 300);
    return () => clearTimeout(id);
  }, [machinesVersion]);

  return (
    <div className="flex h-dvh flex-col">
      <header className="flex h-16 shrink-0 items-center gap-8 px-8">
        <div className="flex items-center gap-2.5">
          <Orb size={26} />
          <span className="text-[1.15rem] font-semibold tracking-[-0.02em]">KBOS</span>
          <span className="rounded-full bg-sunk px-2 py-0.5 text-[0.7rem] font-medium text-muted">Admin</span>
        </div>
        <nav aria-label="Sections" className="flex items-center gap-1">
          {TABS.map((t) => (
            <a
              key={t}
              href={`#${t}`}
              aria-current={tab === t ? "page" : undefined}
              className={cn(
                "relative rounded-full px-4 py-2 text-sm font-medium transition-colors duration-150",
                tab === t ? "bg-card text-ink shadow-[0_1px_3px_rgba(0,0,0,.07)]" : "text-ink-2 hover:text-ink",
              )}
            >
              {TAB_LABEL[t]}
            </a>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-5">
          <ConnDot />
          <Clock />
          {!railOpen ? (
            <button onClick={() => setRailOpen(true)} className="flex h-9 cursor-pointer items-center gap-2 rounded-full bg-card px-3.5 text-sm font-medium text-ink-2 shadow-[0_1px_3px_rgba(0,0,0,.07)] hover:text-ink" aria-label="Show activity">
              <PanelRightOpen className="size-4" /> Activity
            </button>
          ) : null}
        </div>
      </header>

      <div className="flex min-h-0 flex-1 gap-5 px-8 pb-6">
        <main className="min-w-0 flex-1 overflow-y-auto scroll-thin -mx-3 -mt-2 px-3 pb-3 pt-3">
          {loadError ? (
            <div className="mb-5 rounded-2xl bg-crit-soft px-5 py-3 text-sm text-crit">Can't reach the KBOS server ({loadError}). Retrying when the connection comes back.</div>
          ) : null}
          <div key={tab} className="animate-fade-up">
            {tab === "tickets" ? <TicketsView /> : tab === "machines" ? <MachinesView /> : tab === "shifts" ? <ShiftsView /> : tab === "glossary" ? <GlossaryView /> : <DemoView />}
          </div>
        </main>
        {railOpen ? (
          <div className="w-[22rem] shrink-0 pt-1 pb-1 max-[1500px]:w-[19rem]">
            <ActivityRail onClose={() => setRailOpen(false)} />
          </div>
        ) : null}
      </div>

      <TicketSheet />
      <Toaster
        position="bottom-left"
        offset={24}
        toastOptions={{
          classNames: {
            toast: "!rounded-2xl !border-0 !shadow-[0_2px_6px_rgba(23,24,26,.05),0_18px_48px_-12px_rgba(23,24,26,.22)] !font-sans",
            title: "!text-[0.875rem] !font-semibold",
            description: "!text-[0.8125rem] !text-ink-2",
          },
        }}
      />
    </div>
  );
}
