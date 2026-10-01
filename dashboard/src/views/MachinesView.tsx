import { AlertTriangle, CircleCheck, Factory, Gauge, RotateCcw, Thermometer, Zap } from "lucide-react";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";
import { BAND_LABEL, Sparkline, VIB_ALARM, band } from "@/components/charts";
import { KeyChip, MachineChip } from "@/components/kb";
import { Button } from "@/components/ui/button";
import { api, errorText } from "@/lib/api";
import { useMachines } from "@/lib/machines";
import { useApp } from "@/lib/store";
import { useTelemetry } from "@/lib/telemetry";
import type { Band, Machine, SeriesSample } from "@/lib/types";
import { useNow } from "@/lib/useNow";
import { cn } from "@/lib/utils";

const SHIFT_S = 12 * 3600;
const EMPTY: SeriesSample[] = [];

const BAND_STYLE: Record<Band, { pill: string; value: string; icon: typeof CircleCheck }> = {
  good: { pill: "bg-ok-soft text-ok", value: "text-ink", icon: CircleCheck },
  warning: { pill: "bg-amber-soft text-amber ring-1 ring-amber-line", value: "text-ink", icon: AlertTriangle },
  alarm: { pill: "bg-crit text-white", value: "text-crit", icon: AlertTriangle },
};

export function useDemoAction() {
  const [busy, setBusy] = useState<string | null>(null);
  const run = async (id: string, fn: () => Promise<unknown>, ok: string) => {
    setBusy(id);
    try {
      await fn();
      toast(ok);
    } catch (e) {
      toast.error("That didn't work", { description: errorText(e) });
    } finally {
      setBusy(null);
    }
  };
  return { busy, run };
}

function Stat({ icon: Icon, label, value, children }: { icon: typeof Gauge; label: string; value: ReactNode; children?: ReactNode }) {
  return (
    <div className="min-w-0 rounded-2xl bg-sunk/60 px-3 py-2.5">
      <div className="flex items-center gap-1.5 truncate text-[0.72rem] text-muted">
        <Icon className="size-3.5 shrink-0" /> {label}
      </div>
      <div className="mt-0.5 truncate text-[0.95rem] font-semibold text-ink tnum">{value}</div>
      <div className="mt-1.5">{children}</div>
    </div>
  );
}

export function MachineCard({ m, fetchedAt }: { m: Machine; fetchedAt: number }) {
  const ring = useTelemetry((s) => s.rings[m.code] ?? EMPTY);
  const injectedEv = useApp((s) => s.injected[m.code]);
  const openTicket = useApp((s) => s.openTicket);
  const now = useNow(5000);
  const { busy, run } = useDemoAction();

  const last = ring.at(-1);
  const v = last?.vibration_mm_s ?? m.telemetry.vibration_mm_s;
  const temp = last?.temperature_c ?? m.telemetry.temperature_c;
  const load = last?.load_pct ?? m.telemetry.load_pct;
  const output = last?.output_count ?? m.telemetry.output_count;
  const b = band(v);
  const st = BAND_STYLE[b];
  const injected = injectedEv ?? m.telemetry.injected;
  const vibs = ring.map((s) => s.vibration_mm_s);
  const temps = ring.map((s) => s.temperature_c);
  const maxV = Math.max(10, ...vibs);
  const target = m.target_per_shift;
  const soFar = target && m.telemetry.target_so_far !== null ? Math.min(target, Math.round(m.telemetry.target_so_far + (target * (now - fetchedAt)) / 1000 / SHIFT_S)) : null;
  const pct = target ? Math.min(1, output / target) : 0;
  const soFarPct = target && soFar ? Math.min(1, soFar / target) : 0;
  const behind = soFar ? output - soFar : 0;

  return (
    <article
      className={cn("flex flex-col rounded-3xl bg-card p-5 shadow-card transition-[background-color] duration-500", b === "alarm" && "animate-alarm bg-[linear-gradient(180deg,#fff4f2,#ffffff_50%)]")}
      aria-label={`Machine ${m.code}`}
      data-band={b}
    >
      <header className="flex items-start gap-3">
        <MachineChip code={m.code} className="h-9 min-w-11 rounded-xl text-[0.95rem]" />
        <div className="min-w-0 flex-1">
          <div className="truncate text-[0.95rem] font-semibold text-ink">{m.name}</div>
          <div className="text-xs text-muted">{m.line}</div>
        </div>
        <span className={cn("inline-flex h-7 items-center gap-1.5 rounded-full px-3 text-[0.8rem] font-semibold transition-colors duration-300", st.pill)}>
          <st.icon className="size-3.5" />
          {BAND_LABEL[b]}
        </span>
      </header>

      <div className="mt-3 flex items-end justify-between gap-3">
        <div>
          <div className="text-xs text-muted">Vibration</div>
          <div className={cn("mt-0.5 text-[2.4rem] font-semibold leading-none tracking-tight tnum transition-colors duration-300", st.value)}>
            {v.toFixed(1)}
            <span className="ml-1 text-sm font-medium text-muted">mm/s</span>
          </div>
        </div>
        <div className="pb-1 text-right text-[0.7rem] leading-tight text-muted">
          ISO 10816
          <br />
          alarm above {VIB_ALARM}
        </div>
      </div>
      <Sparkline values={vibs} domain={[0, maxV]} bands height={64} stroke={b === "alarm" ? "#d92d20" : "#17181a"} className="mt-3" />
      <div className="mt-1 flex justify-between text-[0.7rem] text-faint">
        <span>5 min ago</span>
        <span>now</span>
      </div>

      <div className="mt-3 grid grid-cols-3 gap-2">
        <Stat icon={Thermometer} label="Temperature" value={`${temp.toFixed(1)} °C`}>
          <Sparkline values={temps} domain={[Math.min(...temps, temp) - 2, Math.max(...temps, temp) + 2]} height={22} stroke="#4b4d52" />
        </Stat>
        <Stat icon={Gauge} label="Load" value={`${Math.round(load)}%`}>
          <Sparkline values={ring.map((s) => s.load_pct)} domain={[0, 100]} height={22} stroke="#4b4d52" />
        </Stat>
        <Stat
          icon={Factory}
          label="Output"
          value={
            target ? (
              <>
                {output}
                <span className="font-normal text-muted"> / {soFar ?? "–"}</span>
              </>
            ) : (
              <span className="font-normal text-faint">No target</span>
            )
          }
        >
          {target ? (
            <div title={`${output} of ${target} ${m.unit} per shift; ${soFar ?? "?"} expected by now`}>
              <div className="relative mt-2 h-1.5 overflow-hidden rounded-full bg-line" role="meter" aria-label="Output against Production Target" aria-valuemin={0} aria-valuemax={target} aria-valuenow={output}>
                <div className={cn("absolute inset-y-0 left-0 rounded-full transition-[width] duration-700", behind < -2 ? "bg-high" : "bg-ink/75")} style={{ width: `${pct * 100}%` }} />
                <div className="absolute inset-y-0 w-0.5 bg-ink/50" style={{ left: `calc(${soFarPct * 100}% - 1px)` }} />
              </div>
              <div className="mt-1 truncate text-[0.68rem] text-muted">
                of {target} {m.unit}
              </div>
            </div>
          ) : (
            <div className="h-[22px]" />
          )}
        </Stat>
      </div>

      <div className="mt-3 flex min-h-7 flex-wrap items-center gap-1.5">
        <span className="mr-1 text-xs text-muted">Open Tickets</span>
        {m.open_tickets.length ? m.open_tickets.map((k) => <KeyChip key={k} k={k} onClick={() => openTicket(k)} />) : <span className="text-xs text-faint">None</span>}
      </div>
      <div className="flex-1" />
      <div className="mt-3 flex items-center gap-2 border-t border-line pt-3">
        <Button size="sm" variant={injected ? "dangerSoft" : "outline"} disabled={busy !== null} onClick={() => run("inject", () => api.inject(m.code), `Injecting vibration on ${m.code}`)}>
          <Zap /> {injected ? "Injected" : "Inject vibration"}
        </Button>
        <Button size="sm" variant="ghost" disabled={busy !== null} onClick={() => run("clear", () => api.clear(m.code), `${m.code} returning to baseline`)}>
          <RotateCcw /> Clear
        </Button>
        {injected && b !== "alarm" ? <span className="ml-auto text-xs text-crit">Ramping up…</span> : null}
      </div>
    </article>
  );
}

export function MachinesView() {
  const machines = useMachines((s) => s.machines);
  const fetchedAt = useMachines((s) => s.fetchedAt);
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,24rem),1fr))] gap-5">
      {machines.map((m) => (
        <MachineCard key={m.code} m={m} fetchedAt={fetchedAt} />
      ))}
      {!machines.length ? <div className="col-span-full py-20 text-center text-sm text-muted">Loading Machines…</div> : null}
    </div>
  );
}
