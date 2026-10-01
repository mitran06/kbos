"""Telemetry simulator: 1 Hz per Machine, smooth OU noise, 2 h in-memory ring.

Vibration is ISO 10816 velocity RMS in mm/s (good < 2.8, warning 2.8–7.1,
alarm > 7.1). Fault injection ramps vibration (and temperature) with a
smoothstep; clearing ramps back to baseline.
"""

from __future__ import annotations

import asyncio
import math
import random
import time
from collections import deque
from dataclasses import dataclass, field

RING_S = 2 * 3600
VIB_GOOD, VIB_ALARM = 2.8, 7.1

# code -> (vibration baseline, temperature baseline, load baseline, units per second at target)
BASELINES: dict[str, tuple[float, float, float]] = {
    "4B": (4.5, 58.0, 72.0),  # warning since the tool change
    "2A": (2.1, 49.0, 64.0),
    "3C": (1.6, 38.0, 55.0),
    "1D": (2.3, 66.0, 70.0),
    "5A": (1.9, 52.0, 68.0),
    "6B": (1.4, 44.0, 60.0),
}
SHIFT_S = 12 * 3600


def vib_band(v: float) -> str:
    return "good" if v < VIB_GOOD else "warning" if v <= VIB_ALARM else "alarm"


def smoothstep(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


@dataclass
class Ramp:
    start_t: float
    duration: float
    from_vib: float
    to_vib: float
    from_temp: float
    to_temp: float

    def at(self, t: float) -> tuple[float, float]:
        k = smoothstep((t - self.start_t) / self.duration)
        return self.from_vib + (self.to_vib - self.from_vib) * k, self.from_temp + (self.to_temp - self.from_temp) * k


@dataclass
class MachineSim:
    code: str
    target: int | None
    vib_base: float
    temp_base: float
    load_base: float
    shift_start_t: float
    noise: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    ramp: Ramp | None = None
    ring: deque = field(default_factory=lambda: deque(maxlen=RING_S))
    output: float = 0.0

    def levels(self, t: float) -> tuple[float, float]:
        if self.ramp:
            return self.ramp.at(t)
        return self.vib_base, self.temp_base

    def step(self, t: float, dt: float = 1.0) -> dict:
        # Ornstein–Uhlenbeck noise: mean-reverting, smooth
        theta, sigmas = 0.08, (0.12, 0.25, 1.2)
        for i, sg in enumerate(sigmas):
            self.noise[i] += -theta * self.noise[i] * dt + sg * math.sqrt(dt) * random.gauss(0, 1) * 0.35
        vib, temp = self.levels(t)
        vib = max(0.3, vib + self.noise[0])
        temp = temp + self.noise[1]
        load = min(100.0, max(0.0, self.load_base + self.noise[2] + (vib - self.vib_base) * 1.2))
        if self.target:
            self.output += self.target / SHIFT_S * dt * (1 + self.noise[2] / 40)
        sample = {
            "t": t,
            "vibration_mm_s": round(vib, 2),
            "temperature_c": round(temp, 1),
            "load_pct": round(load, 1),
            "output_count": int(self.output),
        }
        self.ring.append(sample)
        return sample


class Telemetry:
    def __init__(self) -> None:
        self.machines: dict[str, MachineSim] = {}
        self._task: asyncio.Task | None = None

    def reset(self, targets: dict[str, int | None], shift_elapsed_s: float, backfill_s: int = 1800) -> None:
        """(Re)build the sims and backfill history so charts aren't empty."""
        now_t = time.time()
        self.machines = {}
        for code, target in targets.items():
            vb, tb, lb = BASELINES.get(code, (2.0, 45.0, 60.0))
            m = MachineSim(code, target, vb, tb, lb, now_t - shift_elapsed_s)
            if target:
                m.output = target * max(0.0, shift_elapsed_s - backfill_s) / SHIFT_S
            for i in range(backfill_s, 0, -1):
                m.step(now_t - i)
            self.machines[code] = m

    def tick(self) -> dict[str, dict]:
        t = time.time()
        return {code: m.step(t) for code, m in self.machines.items()}

    def current(self, code: str) -> dict:
        m = self.machines[code]
        s = dict(m.ring[-1])
        s["vibration_band"] = vib_band(s["vibration_mm_s"])
        s["target_per_shift"] = m.target
        s["target_so_far"] = int(m.target * min(1.0, (time.time() - m.shift_start_t) / SHIFT_S)) if m.target else None
        s["injected"] = m.ramp is not None and m.ramp.to_vib > m.vib_base + 0.5
        return s

    def series(self, code: str, minutes: int = 30, points: int | None = None) -> list[dict]:
        m = self.machines[code]
        cutoff = time.time() - minutes * 60
        data = [s for s in m.ring if s["t"] >= cutoff]
        if points and len(data) > points:
            step = len(data) / points
            data = [data[int(i * step)] for i in range(points)]
        return data

    def snapshot(self, code: str) -> dict:
        """Frozen at filing: last 30 min downsampled to 60 points + current values."""
        cur = self.current(code)
        return {
            "machine_code": code,
            "current": {k: cur[k] for k in ("vibration_mm_s", "temperature_c", "load_pct", "output_count")},
            "vibration_band": cur["vibration_band"],
            "target_per_shift": cur["target_per_shift"],
            "target_so_far": cur["target_so_far"],
            "series": [
                {"t": round(s["t"]), "v": s["vibration_mm_s"], "c": s["temperature_c"]}
                for s in self.series(code, 30, 60)
            ],
        }

    def inject(self, code: str, kind: str = "vibration", seconds: float = 20.0) -> None:
        m = self.machines[code]
        t = time.time()
        vib, temp = m.levels(t)
        m.ramp = Ramp(t, seconds, vib, 9.5, temp, temp + 14.0)

    def clear(self, code: str, seconds: float = 8.0) -> None:
        m = self.machines[code]
        t = time.time()
        vib, temp = m.levels(t)
        m.ramp = Ramp(t, seconds, vib, m.vib_base, temp, m.temp_base)

    def compact(self) -> dict[str, dict]:
        return {
            code: {
                "v": m.ring[-1]["vibration_mm_s"],
                "c": m.ring[-1]["temperature_c"],
                "l": m.ring[-1]["load_pct"],
                "o": m.ring[-1]["output_count"],
                "t": round(m.ring[-1]["t"]),
            }
            for code, m in self.machines.items()
            if m.ring
        }


telemetry = Telemetry()
