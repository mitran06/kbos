import { create } from "zustand";
import { api } from "./api";
import { useTelemetry } from "./telemetry";
import type { Machine } from "./types";

interface MachinesState {
  machines: Machine[];
  fetchedAt: number;
  load: () => Promise<void>;
  seedRings: () => Promise<void>;
}

export const useMachines = create<MachinesState>((set, get) => ({
  machines: [],
  fetchedAt: 0,
  load: async () => {
    const machines = await api.machines();
    set({ machines, fetchedAt: Date.now() });
  },
  seedRings: async () => {
    if (!get().machines.length) await get().load();
    const tel = useTelemetry.getState();
    tel.clearAll();
    await Promise.all(
      get().machines.map(async (m) => {
        const series = await api.machineTelemetry(m.code, 10);
        useTelemetry.getState().seed(m.code, series);
      }),
    );
  },
}));
