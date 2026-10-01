import { useApp } from '../state/store';
import type { Metrics, Person, ShiftSession, TicketDetail, TicketSummary } from './types';

function base(): string {
  return useApp.getState().serverUrl;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${base()}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return (await res.json()) as T;
}

export const api = {
  people: () => req<Person[]>('/api/people'),
  startShift: (person_id: number) =>
    req<{ shift_session: ShiftSession; person: Person }>('/api/shifts/start', {
      method: 'POST',
      body: JSON.stringify({ person_id }),
    }),
  tickets: (q = 'status=active') => req<TicketSummary[]>(`/api/tickets?${q}`),
  ticket: (key: string) => req<TicketDetail>(`/api/tickets/${encodeURIComponent(key)}`),
  metrics: () => req<Metrics>('/api/metrics'),
  health: () => req<{ ok: boolean }>('/api/health'),
  async upload(uri: string, sessionId: string, personId: number): Promise<{ photo_id: number; url: string }> {
    const form = new FormData();
    // React Native FormData accepts {uri, name, type} file parts.
    form.append('file', { uri, name: 'photo.jpg', type: 'image/jpeg' } as unknown as Blob);
    form.append('session_id', sessionId);
    form.append('person_id', String(personId));
    const res = await fetch(`${base()}/api/uploads`, { method: 'POST', body: form });
    if (!res.ok) throw new Error(`upload ${res.status}`);
    return (await res.json()) as { photo_id: number; url: string };
  },
};

export function absUrl(path: string): string {
  return path.startsWith('http') ? path : `${base()}${path}`;
}
