import * as Haptics from 'expo-haptics';
import { Pressable, Text, View } from 'react-native';
import Animated, { FadeInDown, FadeOut, LinearTransition } from 'react-native-reanimated';
import { api } from '../lib/api';
import type { TicketSummary } from '../lib/types';
import { useApp } from '../state/store';
import { ago, C, EASE_OUT, F, severityColor, shadow } from '../theme';
import { Avatar } from './Avatar';
import { MachineChip, OverdueBadge, SeverityPill, StatusPill, UnclearBadge } from './Badges';

export async function openTicket(key: string): Promise<void> {
  try {
    useApp.getState().set({ detail: await api.ticket(key) });
  } catch (e) {
    console.log('[kb] open ticket failed', String(e));
  }
}

export function TicketCard({ t, index = 0 }: { t: TicketSummary; index?: number }) {
  const accent = t.status === 'closed' ? C.green : severityColor(t.severity).fg;
  return (
    <Animated.View
      entering={FadeInDown.duration(280).delay(index * 50).easing(EASE_OUT).withInitialValues({ transform: [{ translateY: 12 }, { scale: 0.98 }] })}
      exiting={FadeOut.duration(140)}
      layout={LinearTransition.duration(220).easing(EASE_OUT)}
    >
      <Pressable
        onPress={() => {
          Haptics.selectionAsync();
          openTicket(t.key);
        }}
        style={({ pressed }) => [
          {
            backgroundColor: C.card,
            borderRadius: 18,
            marginBottom: 10,
            overflow: 'hidden',
            flexDirection: 'row',
            transform: [{ scale: pressed ? 0.98 : 1 }],
          },
          shadow,
        ]}
      >
        <View style={{ width: 4, backgroundColor: accent }} />
        <View style={{ flex: 1, padding: 14, gap: 8 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Text style={{ fontFamily: F.semibold, color: C.ink3, fontSize: 13 }}>{t.key}</Text>
            <MachineChip code={t.machine_code} />
            <View style={{ flex: 1 }} />
            <Text style={{ fontFamily: F.regular, color: C.ink3, fontSize: 12 }}>{ago(t.created_at)}</Text>
          </View>
          <Text style={{ fontFamily: F.semibold, color: C.ink, fontSize: 16, lineHeight: 21 }} numberOfLines={2}>
            {t.title}
          </Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 6 }}>
            <SeverityPill severity={t.severity} />
            <StatusPill status={t.status} />
            {t.overdue && <OverdueBadge />}
            {t.unclear && t.status !== 'closed' && <UnclearBadge />}
            <View style={{ flex: 1 }} />
            <View style={{ flexDirection: 'row' }}>
              {t.assignees.slice(0, 3).map((a, i) => (
                <View key={a.id ?? i} style={{ marginLeft: i === 0 ? 0 : -8 }}>
                  <Avatar initials={a.initials} hue={a.avatar_hue} size={26} ring />
                </View>
              ))}
            </View>
          </View>
        </View>
      </Pressable>
    </Animated.View>
  );
}

export function TicketList({ heading, tickets }: { heading: string; tickets: TicketSummary[] }) {
  return (
    <View>
      <Text style={{ fontFamily: F.semibold, fontSize: 13, color: C.ink3, letterSpacing: 0.6, marginBottom: 10, textTransform: 'uppercase' }}>
        {heading}
      </Text>
      {tickets.map((t, i) => (
        <TicketCard key={t.key} t={t} index={i} />
      ))}
      {tickets.length === 0 && <Text style={{ fontFamily: F.regular, color: C.ink3 }}>Nothing here.</Text>}
    </View>
  );
}
