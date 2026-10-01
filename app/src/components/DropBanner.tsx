import { useEffect } from 'react';
import { Pressable, Text, View } from 'react-native';
import Animated, { SlideInUp, SlideOutUp } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useApp } from '../state/store';
import { C, F, shadow } from '../theme';
import { MachineChip, SeverityPill } from './Badges';
import { openTicket } from './TicketCard';

/** Silent live update: a ticket newly assigned to me drops in from the top. No speech. */
export function DropBanner() {
  const drop = useApp((s) => s.drop);
  const insets = useSafeAreaInsets();
  useEffect(() => {
    if (!drop) return;
    const t = setTimeout(() => useApp.getState().set({ drop: null }), 9000);
    return () => clearTimeout(t);
  }, [drop]);
  if (!drop) return null;
  return (
    <Animated.View
      key={drop.key}
      entering={SlideInUp.springify().duration(450).dampingRatio(0.8)}
      exiting={SlideOutUp.duration(200)}
      style={{ position: 'absolute', left: 14, right: 14, top: insets.top + 8 }}
    >
      <Pressable
        onPress={() => {
          useApp.getState().set({ drop: null });
          openTicket(drop.key);
        }}
        style={[{ backgroundColor: C.card, borderRadius: 20, padding: 14, flexDirection: 'row', alignItems: 'center', gap: 12 }, shadow]}
      >
        <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: C.blue }} />
        <View style={{ flex: 1 }}>
          <Text style={{ fontFamily: F.semibold, fontSize: 13, color: C.blue }}>Assigned to you · {drop.key}</Text>
          <Text style={{ fontFamily: F.semibold, fontSize: 15, color: C.ink, marginTop: 2 }} numberOfLines={1}>
            {drop.title}
          </Text>
        </View>
        <MachineChip code={drop.machine_code} />
        <SeverityPill severity={drop.severity} />
      </Pressable>
    </Animated.View>
  );
}
