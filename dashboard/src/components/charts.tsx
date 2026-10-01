import { Area, AreaChart, CartesianGrid, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { istClock } from "@/lib/format";
import type { Band } from "@/lib/types";
import { useWidth } from "@/lib/useWidth";
import { cn } from "@/lib/utils";

export const VIB_GOOD = 2.8;
export const VIB_ALARM = 7.1;
export const band = (v: number): Band => (v < VIB_GOOD ? "good" : v <= VIB_ALARM ? "warning" : "alarm");

export const BAND_FILL: Record<Band, string> = { good: "#22a554", warning: "#f0a020", alarm: "#d92d20" };
export const BAND_LABEL: Record<Band, string> = { good: "Good", warning: "Warning", alarm: "Alarm" };

interface Pt {
  t: number;
  v: number;
  c?: number;
}

function SnapshotTooltip({ active, payload }: { active?: boolean; payload?: { payload: Pt }[] }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  const b = band(p.v);
  return (
    <div className="rounded-xl bg-card px-3 py-2 text-xs shadow-lift ring-1 ring-line">
      <div className="text-muted tnum">{istClock(p.t * 1000)} IST</div>
      <div className="mt-1 flex items-center gap-1.5 font-medium text-ink tnum">
        <span className="size-2 rounded-full" style={{ background: BAND_FILL[b] }} />
        {p.v.toFixed(1)} mm/s <span className="font-normal text-muted">· {BAND_LABEL[b]}</span>
      </div>
      {p.c !== undefined ? <div className="mt-0.5 text-ink-2 tnum">{p.c.toFixed(1)} °C</div> : null}
    </div>
  );
}

/** Vibration over time with the ISO 10816 bands shaded behind the line. */
export function VibrationChart({ data, height = 200, markerT }: { data: Pt[]; height?: number; markerT?: number }) {
  const max = Math.max(10, ...data.map((d) => d.v + 0.8));
  const top = Math.ceil(max);
  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 56, bottom: 0, left: -18 }}>
          <defs>
            <linearGradient id="vibFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#17181a" stopOpacity={0.1} />
              <stop offset="100%" stopColor="#17181a" stopOpacity={0} />
            </linearGradient>
          </defs>
          <ReferenceArea y1={0} y2={VIB_GOOD} fill={BAND_FILL.good} fillOpacity={0.07} stroke="none" ifOverflow="hidden" />
          <ReferenceArea y1={VIB_GOOD} y2={VIB_ALARM} fill={BAND_FILL.warning} fillOpacity={0.09} stroke="none" ifOverflow="hidden" />
          <ReferenceArea y1={VIB_ALARM} y2={top} fill={BAND_FILL.alarm} fillOpacity={0.07} stroke="none" ifOverflow="hidden" />
          <ReferenceLine y={VIB_GOOD} stroke={BAND_FILL.good} strokeOpacity={0.35} strokeDasharray="3 4" label={{ value: "Good < 2.8", position: "right", fontSize: 10.5, fill: "#16803c" }} />
          <ReferenceLine y={VIB_ALARM} stroke={BAND_FILL.alarm} strokeOpacity={0.35} strokeDasharray="3 4" label={{ value: "Alarm > 7.1", position: "right", fontSize: 10.5, fill: "#d92d20" }} />
          <CartesianGrid vertical={false} stroke="#ebebe6" strokeDasharray="0" strokeOpacity={0.6} />
          <XAxis
            dataKey="t"
            type="number"
            domain={["dataMin", "dataMax"]}
            tickFormatter={(t: number) => istClock(t * 1000)}
            tick={{ fontSize: 11, fill: "#85878c" }}
            tickLine={false}
            axisLine={{ stroke: "#deded8" }}
            minTickGap={48}
          />
          <YAxis domain={[0, top]} tick={{ fontSize: 11, fill: "#85878c" }} tickLine={false} axisLine={false} width={44} ticks={[0, VIB_GOOD, VIB_ALARM, top]} tickFormatter={(v: number) => (v === top ? `${v}` : v.toFixed(1))} />
          {markerT ? <ReferenceLine x={markerT} stroke="#17181a" strokeOpacity={0.5} strokeDasharray="2 3" label={{ value: "Filed", position: "insideTopRight", fontSize: 10.5, fill: "#4b4d52" }} /> : null}
          <Tooltip content={<SnapshotTooltip />} cursor={{ stroke: "#17181a", strokeOpacity: 0.25 }} isAnimationActive={false} />
          <Area type="monotone" dataKey="v" stroke="#17181a" strokeWidth={2} fill="url(#vibFill)" dot={false} activeDot={{ r: 4, stroke: "#fff", strokeWidth: 2, fill: "#17181a" }} isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Lightweight live sparkline (SVG) used on Machine cards at 1 Hz. */
export function Sparkline({
  values,
  domain,
  height = 56,
  bands = false,
  stroke = "#17181a",
  className,
}: {
  values: number[];
  domain: [number, number];
  height?: number;
  bands?: boolean;
  stroke?: string;
  className?: string;
}) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const [lo, hi] = domain;
  const y = (v: number) => height - 3 - ((Math.min(hi, Math.max(lo, v)) - lo) / (hi - lo)) * (height - 6);
  const n = values.length;
  const x = (i: number) => (n <= 1 ? w : (i / (n - 1)) * (w - 5));
  const d = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const last = values.at(-1);
  return (
    <div ref={ref} className={cn("relative w-full", className)} style={{ height }}>
      {w > 0 ? (
        <svg width={w} height={height} className="block overflow-visible">
          {bands ? (
            <>
              <rect x={0} width={w} y={y(VIB_GOOD)} height={height - y(VIB_GOOD)} fill={BAND_FILL.good} opacity={0.08} />
              <rect x={0} width={w} y={y(VIB_ALARM)} height={y(VIB_GOOD) - y(VIB_ALARM)} fill={BAND_FILL.warning} opacity={0.1} />
              <rect x={0} width={w} y={0} height={y(VIB_ALARM)} fill={BAND_FILL.alarm} opacity={0.08} />
              <line x1={0} x2={w} y1={y(VIB_ALARM)} y2={y(VIB_ALARM)} stroke={BAND_FILL.alarm} strokeOpacity={0.35} strokeDasharray="3 4" />
              <line x1={0} x2={w} y1={y(VIB_GOOD)} y2={y(VIB_GOOD)} stroke={BAND_FILL.good} strokeOpacity={0.35} strokeDasharray="3 4" />
            </>
          ) : null}
          {n > 1 ? <path d={d} fill="none" stroke={stroke} strokeWidth={bands ? 2 : 1.5} strokeLinejoin="round" strokeLinecap="round" /> : null}
          {last !== undefined && n > 0 ? <circle cx={x(n - 1)} cy={y(last)} r={3.5} fill={stroke} stroke="#fff" strokeWidth={1.5} /> : null}
        </svg>
      ) : null}
    </div>
  );
}
