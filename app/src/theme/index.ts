import { Easing } from 'react-native-reanimated';
import type { Severity, Status } from '../lib/types';

export const C = {
  bg: '#F7F7F5',
  card: '#FFFFFF',
  ink: '#16181D',
  ink2: '#4A4F5A',
  ink3: '#8A8F99',
  line: '#ECECE8',
  chip: '#F1F1EE',
  critical: '#E5484D',
  criticalBg: '#FDECEC',
  high: '#F76B15',
  highBg: '#FEF0E6',
  amber: '#C98A00',
  amberBg: '#FFF6DC',
  green: '#2E9E5B',
  greenBg: '#E6F6EC',
  blue: '#3B6FF5',
};

export const F = {
  regular: 'Inter_400Regular',
  medium: 'Inter_500Medium',
  semibold: 'Inter_600SemiBold',
  bold: 'Inter_700Bold',
};

export const ORB = ['#5B8CFF', '#9B6BFF', '#FF6FB5', '#3FD3C6'];

export const EASE_OUT = Easing.bezier(0.23, 1, 0.32, 1);
export const EASE_IN_OUT = Easing.bezier(0.77, 0, 0.175, 1);

export const shadow = {
  shadowColor: '#1B1F2A',
  shadowOpacity: 0.07,
  shadowRadius: 16,
  shadowOffset: { width: 0, height: 6 },
  elevation: 3,
};

export function severityColor(s: Severity): { fg: string; bg: string } {
  if (s === 'critical') return { fg: C.critical, bg: C.criticalBg };
  if (s === 'high') return { fg: C.high, bg: C.highBg };
  return { fg: C.ink2, bg: C.chip };
}

export function statusLabel(s: Status): string {
  return { open: 'Open', in_progress: 'In Progress', monitoring: 'Monitoring · not resolved', closed: 'Closed' }[s];
}

export function statusColor(s: Status): { fg: string; bg: string } {
  if (s === 'monitoring') return { fg: C.amber, bg: C.amberBg };
  if (s === 'closed') return { fg: C.green, bg: C.greenBg };
  if (s === 'in_progress') return { fg: C.blue, bg: '#EAF0FF' };
  return { fg: C.ink2, bg: C.chip };
}

export function ago(iso: string | null): string {
  if (!iso) return '';
  const s = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export function istTime(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(Date.parse(iso) + 5.5 * 3600 * 1000);
  return `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`;
}
