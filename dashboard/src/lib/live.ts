import { create } from "zustand";
import { useApp } from "./store";
import { useTelemetry } from "./telemetry";
import type { KbosEvent } from "./types";

export type ConnState = "connecting" | "live" | "offline";
export const useConn = create<{ state: ConnState; since: number }>(() => ({ state: "connecting", since: Date.now() }));

let socket: WebSocket | null = null;
let attempt = 0;
let started = false;
let everConnected = false;

function wsUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws`;
}

function isEvent(x: unknown): x is KbosEvent {
  return !!x && typeof x === "object" && "type" in x && "data" in x && typeof (x as { type: unknown }).type === "string";
}

function connect(): void {
  useConn.setState({ state: attempt === 0 ? "connecting" : useConn.getState().state });
  const ws = new WebSocket(wsUrl());
  socket = ws;
  ws.onopen = () => {
    attempt = 0;
    useConn.setState({ state: "live", since: Date.now() });
    // after a drop we may have missed events: refetch everything once
    if (everConnected) void useApp.getState().loadAll();
    everConnected = true;
  };
  ws.onmessage = (msg) => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(typeof msg.data === "string" ? msg.data : "");
    } catch {
      return;
    }
    if (!isEvent(parsed)) return;
    if (parsed.type === "telemetry") useTelemetry.getState().push(parsed.data);
    else useApp.getState().apply(parsed);
  };
  ws.onclose = () => {
    if (socket !== ws) return;
    useConn.setState({ state: "offline", since: Date.now() });
    const delay = Math.min(15_000, 500 * 2 ** attempt) * (0.8 + Math.random() * 0.4);
    attempt += 1;
    setTimeout(connect, delay);
  };
  ws.onerror = () => ws.close();
}

export function startLive(): void {
  if (started) return;
  started = true;
  connect();
}
