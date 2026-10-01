import { Text, View } from 'react-native';
import type { Severity, Status } from '../lib/types';
import { C, F, severityColor, statusColor, statusLabel } from '../theme';

export function Pill({ label, fg, bg, strong = false }: { label: string; fg: string; bg: string; strong?: boolean }) {
  return (
    <View style={{ backgroundColor: bg, borderRadius: 999, paddingHorizontal: 9, paddingVertical: 3 }}>
      <Text style={{ color: fg, fontFamily: strong ? F.semibold : F.medium, fontSize: 12 }}>{label}</Text>
    </View>
  );
}

export function SeverityPill({ severity }: { severity: Severity }) {
  const c = severityColor(severity);
  return <Pill label={severity[0]!.toUpperCase() + severity.slice(1)} fg={c.fg} bg={c.bg} strong />;
}

export function StatusPill({ status }: { status: Status }) {
  const c = statusColor(status);
  return <Pill label={statusLabel(status)} fg={c.fg} bg={c.bg} />;
}

export const OverdueBadge = () => <Pill label="Overdue" fg="#fff" bg={C.critical} strong />;
export const UnclearBadge = () => <Pill label="Unclear check" fg={C.amber} bg={C.amberBg} strong />;

export function MachineChip({ code }: { code: string }) {
  return (
    <View style={{ backgroundColor: C.ink, borderRadius: 7, paddingHorizontal: 7, paddingVertical: 2 }}>
      <Text style={{ color: '#fff', fontFamily: F.semibold, fontSize: 12, letterSpacing: 0.4 }}>{code}</Text>
    </View>
  );
}
