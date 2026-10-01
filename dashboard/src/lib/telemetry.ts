import { create } from "zustand";
import type { CompactSample, SeriesSample } from "./types";

/** Client-side ring of the last ~5 min per Machine, seeded from REST and fed by /ws at 1 Hz. */
export const RING_S = 300;

interface TelemetryState {
  rings: Record<string, SeriesSample[]>;
  seed: (code: string, samples: SeriesSample[]) => void;
  push: (data: Record<string, CompactSample>) => void;
  clearAll: () => void;
}

function trim(ring: SeriesSample[]): SeriesSample[] {
  const last = ring.at(-1);
  if (!last) return ring;
  const cutoff = last.t - RING_S;
  let i = 0;
  while (i < ring.length && ring[i].t < cutoff) i++;
  return i ? ring.slice(i) : ring;
}

export const useTelemetry = create<TelemetryState>((set) => ({
  rings: {},
  seed: (code, samples) =>
    set((s) => {
      const existing = s.rings[code] ?? [];
      const lastSeeded = samples.at(-1)?.t ?? 0;
      const merged = [...samples, ...existing.filter((x) => x.t > lastSeeded)];
      return { rings: { ...s.rings, [code]: trim(merged) } };
    }),
  push: (data) =>
    set((s) => {
      const rings = { ...s.rings };
      for (const [code, c] of Object.entries(data)) {
        const prev = rings[code] ?? [];
        if (prev.length && prev[prev.length - 1].t >= c.t) continue;
        rings[code] = trim([...prev, { t: c.t, vibration_mm_s: c.v, temperature_c: c.c, load_pct: c.l, output_count: c.o }]);
      }
      return { rings };
    }),
  clearAll: () => set({ rings: {} }),
}));
