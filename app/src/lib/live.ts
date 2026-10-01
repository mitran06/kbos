import * as Haptics from 'expo-haptics';
import { router } from 'expo-router';
import { useEffect } from 'react';
import type { TicketSummary } from './types';
import { useApp } from '../state/store';
import { voice } from '../voice/session';
import { api } from './api';

interface LiveEvent {
  type: string;
  data: { ticket?: TicketSummary; by?: number };
}

/** /ws: silent live updates for the logged-in person. */
export function useLive(): void {
  const serverUrl = useApp((s) => s.serverUrl);
  const personId = useApp((s) => s.person?.id);

  useEffect(() => {
    if (!personId) return;
    let ws: WebSocket | null = null;
    let closed = false;
    let retry = 500;

    const open = () => {
      ws = new WebSocket(serverUrl.replace(/^http/, 'ws') + '/ws');
      ws.onopen = () => {
        retry = 500;
      };
      ws.onmessage = (e) => {
        const ev = JSON.parse(String(e.data)) as LiveEvent;
        if (ev.type === 'telemetry') return;
        const st = useApp.getState();
        if (ev.type === 'demo.reset') {
          voice.disconnect();
          st.resetSession();
          router.replace('/');
          return;
        }
        const t = ev.data.ticket;
        if (!t) return;
        // refresh visible copies in place
        if (st.list?.tickets.some((x) => x.key === t.key)) {
          st.set({ list: { ...st.list, tickets: st.list.tickets.map((x) => (x.key === t.key ? t : x)) } });
        }
        if (st.detail?.key === t.key) {
          api.ticket(t.key).then((d) => useApp.getState().set({ detail: d })).catch(() => {});
        }
        const mine = t.assignees.some((a) => a.id === personId);
        const byMe = ev.data.by === personId;
        const isNewForMe = ev.type === 'ticket.created' || (ev.type === 'ticket.updated' && 'assigned' in ev.data);
        if (mine && !byMe && isNewForMe && t.status !== 'closed') {
          Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
          st.set({ drop: t });
        }
      };
      ws.onclose = () => {
        if (closed) return;
        setTimeout(open, retry);
        retry = Math.min(retry * 2, 8000);
      };
    };
    open();
    return () => {
      closed = true;
      ws?.close();
    };
  }, [serverUrl, personId]);
}
