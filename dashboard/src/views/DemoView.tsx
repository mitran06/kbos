import { Activity, KeyRound, Mic, RotateCcw, Server, Zap } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { BAND_FILL, BAND_LABEL, band } from "@/components/charts";
import { MachineChip } from "@/components/kb";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose } from "@/components/ui/dialog";
import { api, errorText } from "@/lib/api";
import { useMachines } from "@/lib/machines";
import { useApp } from "@/lib/store";
import { useTelemetry } from "@/lib/telemetry";
import type { Health, Machine } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useDemoAction } from "./MachinesView";

function Card({ title, icon: Icon, children, className, aside }: { title: string; icon: typeof Server; children: ReactNode; className?: string; aside?: ReactNode }) {
  return (
    <section className={cn("rounded-3xl bg-card p-6 shadow-card", className)}>
      <div className="mb-4 flex items-center gap-2">
        <Icon className="size-4 text-muted" />
        <h3 className="text-[0.78rem] font-semibold uppercase tracking-[0.07em] text-muted">{title}</h3>
        <div className="ml-auto">{aside}</div>
      </div>
      {children}
    </section>
  );
}

function ResetCard() {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  return (
    <section className="flex items-center gap-6 rounded-3xl bg-card p-6 shadow-card">
      <div className="grid size-12 shrink-0 place-items-center rounded-2xl bg-crit-soft text-crit">
        <RotateCcw className="size-5" />
      </div>
      <div className="min-w-0 flex-1">
        <h3 className="text-lg font-semibold tracking-tight">Reset demo</h3>
        <p className="mt-0.5 text-sm text-ink-2">Wipes every Ticket, Check and Shift, re-seeds the night-shift story relative to now, and returns every phone to the people grid.</p>
      </div>
      <Button variant="danger" size="lg" onClick={() => setOpen(true)}>
        <RotateCcw /> Reset demo
      </Button>
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title="Reset the demo?"
        description="All Tickets, Checks, photos and Shifts are wiped and the seed story is rebuilt. Active voice sessions are closed. This can't be undone."
      >
        <div className="flex justify-end gap-2">
          <DialogClose asChild>
            <Button variant="ghost">Keep everything</Button>
          </DialogClose>
          <Button
            variant="danger"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await api.reset();
                toast.success("Demo reset", { description: "Fresh seed loaded on every screen." });
                setOpen(false);
              } catch (e) {
                toast.error("Reset failed", { description: errorText(e) });
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? "Resetting…" : "Reset demo"}
          </Button>
        </div>
      </Dialog>
    </section>
  );
}

function InjectRow({ m }: { m: Machine }) {
  const last = useTelemetry((s) => s.rings[m.code]?.at(-1));
  const injected = useApp((s) => s.injected[m.code]) ?? m.telemetry.injected;
  const { busy, run } = useDemoAction();
  const v = last?.vibration_mm_s ?? m.telemetry.vibration_mm_s;
  const b = band(v);
  return (
    <div className="flex items-center gap-3 border-t border-line py-3 first:border-t-0">
      <MachineChip code={m.code} />
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium">{m.name}</div>
        <div className="flex items-center gap-1.5 text-xs text-muted tnum">
          <span className="size-1.5 rounded-full" style={{ background: BAND_FILL[b] }} />
          {v.toFixed(1)} mm/s · {BAND_LABEL[b]}
        </div>
      </div>
      <Button size="sm" variant={injected ? "dangerSoft" : "outline"} disabled={busy !== null} onClick={() => run("i", () => api.inject(m.code), `Injecting vibration on ${m.code}`)}>
        <Zap /> {injected ? "Injected" : "Inject vibration"}
      </Button>
      <Button size="sm" variant="ghost" disabled={busy !== null} onClick={() => run("c", () => api.clear(m.code), `${m.code} returning to baseline`)}>
        Clear
      </Button>
    </div>
  );
}

const KEY_STYLE: Record<string, string> = {
  ok: "bg-ok-soft text-ok",
  exhausted: "bg-crit-soft text-crit",
  untested: "bg-sunk text-muted",
};

function fmtUptime(s: number) {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m}m ${s % 60}s`;
}

export function DemoView() {
  const machines = useMachines((s) => s.machines);
  const [health, setHealth] = useState<Health | null>(null);
  const [healthErr, setHealthErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const tick = () =>
      api
        .health()
        .then((h) => alive && (setHealth(h), setHealthErr(null)))
        .catch((e: unknown) => alive && setHealthErr(errorText(e)));
    tick();
    const id = setInterval(tick, 3000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  return (
    <div className="grid gap-5">
      <ResetCard />
      <div className="grid grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] gap-5">
        <Card title="Fault injection" icon={Zap}>
          <p className="-mt-1 mb-2 text-sm text-ink-2">Ramps vibration to about 9.5 mm/s over 20 s, with temperature rising. Workers notice and report it; KB does not alert.</p>
          {machines.map((m) => (
            <InjectRow key={m.code} m={m} />
          ))}
        </Card>
        <div className="grid content-start gap-5">
          <Card title="Server" icon={Server} aside={health ? <span className="text-xs text-muted tnum">up {fmtUptime(health.uptime_s)}</span> : null}>
            {healthErr ? <div className="rounded-xl bg-crit-soft px-3 py-2 text-sm text-crit">Health check failed: {healthErr}</div> : null}
            {health ? (
              <div className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
                <div>
                  <div className="text-xs text-muted">LLM</div>
                  <div className="font-medium">{health.providers.llm}</div>
                </div>
                <div>
                  <div className="text-xs text-muted">TTS</div>
                  <div className="font-medium">
                    {health.providers.tts} <span className="font-normal text-muted">· {health.providers.tts_voice}</span>
                  </div>
                </div>
                <div>
                  <div className="text-xs text-muted">STT</div>
                  <div className="font-medium">{health.providers.stt}</div>
                </div>
                <div>
                  <div className="text-xs text-muted">Now</div>
                  <div className="font-medium">
                    {health.shift_now === "day" ? "Day" : "Night"} shift · {health.db.tickets} Tickets · {health.ws_clients} live {health.ws_clients === 1 ? "screen" : "screens"}
                  </div>
                </div>
              </div>
            ) : !healthErr ? (
              <div className="text-sm text-muted">Checking…</div>
            ) : null}
          </Card>
          <Card title="Sarvam key pool" icon={KeyRound} aside={health ? <span className="text-xs text-muted">{health.keys.filter((k) => k.status === "ok").length} of {health.keys.length} ok</span> : null}>
            <div className="flex flex-wrap gap-2">
              {health?.keys.map((k) => (
                <span key={k.key} className={cn("inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-xs font-medium tnum", KEY_STYLE[k.status] ?? "bg-sunk text-ink-2")}>
                  Key {k.key} · {k.status}
                </span>
              ))}
              {health && !health.keys.length ? <span className="text-sm text-muted">No keys loaded</span> : null}
            </div>
          </Card>
          <Card title="Voice sessions" icon={Mic} aside={health ? <span className="text-xs text-muted">{health.sessions.length} active</span> : null}>
            {health?.sessions.length ? (
              <div className="grid gap-2">
                {health.sessions.map((s) => (
                  <div key={s.id} className="flex items-center gap-2.5 text-sm">
                    <span className={cn("size-2 rounded-full", s.listening ? "animate-breathe bg-kb-violet" : "bg-faint")} />
                    <span className="font-medium">{s.person || "Not logged in"}</span>
                    <span className="text-muted">{s.listening ? "listening" : "idle"}</span>
                    <span className="ml-auto font-mono text-xs text-faint">{s.id}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-muted">No phones connected.</div>
            )}
          </Card>
        </div>
      </div>
      <Card title="Recent latency" icon={Activity}>
        {health?.latency.length ? (
          <div className="grid gap-2.5">
            {[...health.latency].reverse().map((l, i) => (
              <div key={`${l.at}-${i}`} className="grid grid-cols-[5rem_8rem_1fr] gap-3 text-[0.8125rem]">
                <span className="font-mono text-muted tnum">{l.at}</span>
                <span className="truncate font-medium">{l.person}</span>
                <span className="font-mono text-ink-2">{l.lines.join("  ·  ")}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-sm text-muted">No voice turns yet. Latency lines appear here after each KB reply.</div>
        )}
      </Card>
    </div>
  );
}
