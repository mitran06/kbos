import * as Haptics from 'expo-haptics';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, Text, View } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Avatar } from '../components/Avatar';
import { Orb } from '../components/Orb';
import { api } from '../lib/api';
import type { Person } from '../lib/types';
import { useApp } from '../state/store';
import { C, EASE_OUT, F, shadow } from '../theme';
import { botLevel } from '../voice/session';

function PersonCard({ p, index, onPick, busy }: { p: Person; index: number; onPick: (p: Person) => void; busy: boolean }) {
  return (
    <Animated.View entering={FadeInDown.duration(300).delay(80 + index * 45).easing(EASE_OUT)} style={{ width: '48%', marginBottom: 12 }}>
      <Pressable
        onPress={() => onPick(p)}
        style={({ pressed }) => [
          { backgroundColor: C.card, borderRadius: 22, padding: 16, alignItems: 'flex-start', gap: 12, transform: [{ scale: pressed ? 0.97 : 1 }] },
          shadow,
        ]}
      >
        <View style={{ flexDirection: 'row', width: '100%', alignItems: 'center' }}>
          <Avatar initials={p.initials} hue={p.avatar_hue} size={48} />
          <View style={{ flex: 1 }} />
          {busy && <ActivityIndicator color={C.ink3} />}
        </View>
        <View>
          <Text style={{ fontFamily: F.semibold, fontSize: 16, color: C.ink }}>{p.name}</Text>
          <Text style={{ fontFamily: F.regular, fontSize: 13, color: C.ink2, marginTop: 2 }}>{p.role_label}</Text>
        </View>
        <View style={{ backgroundColor: p.on_shift_now ? '#EAF0FF' : C.chip, borderRadius: 999, paddingHorizontal: 9, paddingVertical: 3 }}>
          <Text style={{ fontFamily: F.medium, fontSize: 12, color: p.on_shift_now ? C.blue : C.ink3 }}>
            {p.shift === 'day' ? 'Day' : 'Night'} shift
          </Text>
        </View>
      </Pressable>
    </Animated.View>
  );
}

export default function PeopleGrid() {
  const insets = useSafeAreaInsets();
  const serverUrl = useApp((s) => s.serverUrl);
  const [people, setPeople] = useState<Person[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  useFocusEffect(
    useCallback(() => {
      let alive = true;
      const load = () =>
        api
          .people()
          .then((p) => alive && (setPeople(p), setError(null)))
          .catch((e) => alive && setError(String(e)));
      load();
      const t = setInterval(load, 15000);
      return () => {
        alive = false;
        clearInterval(t);
      };
    }, [serverUrl]),
  );

  const pick = async (p: Person) => {
    if (busy) return;
    Haptics.selectionAsync();
    setBusy(p.id);
    try {
      const r = await api.startShift(p.id);
      useApp.getState().set({ person: r.person, shift: r.shift_session });
      router.replace('/home');
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  };

  const now = people?.filter((p) => p.on_shift_now) ?? [];
  const other = people?.filter((p) => !p.on_shift_now) ?? [];

  return (
    <ScrollView style={{ flex: 1, backgroundColor: C.bg }} contentContainerStyle={{ paddingTop: insets.top + 28, paddingHorizontal: 18, paddingBottom: insets.bottom + 30 }}>
      <Pressable onLongPress={() => router.push('/settings')} delayLongPress={600} style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
        <View style={{ width: 40, height: 40, marginLeft: -6 }}>
          <Orb size={40} level={botLevel} />
        </View>
        <Text style={{ fontFamily: F.bold, fontSize: 26, color: C.ink, letterSpacing: -0.5 }}>KBOS</Text>
      </Pressable>
      <Text style={{ fontFamily: F.bold, fontSize: 32, color: C.ink, marginTop: 26, letterSpacing: -0.8 }}>Who's on shift?</Text>
      <Text style={{ fontFamily: F.regular, fontSize: 15, color: C.ink2, marginTop: 6, marginBottom: 22 }}>Tap your face to start your shift.</Text>
      {error && (
        <Text style={{ fontFamily: F.regular, color: C.critical, marginBottom: 12 }}>
          Can't reach the server at {serverUrl}. Long-press KBOS to change it.
        </Text>
      )}
      {!people && !error && <ActivityIndicator color={C.ink3} style={{ marginTop: 40 }} />}
      {now.length > 0 && <Text style={{ fontFamily: F.semibold, fontSize: 13, color: C.ink3, letterSpacing: 0.6, marginBottom: 10 }}>ON SHIFT NOW</Text>}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between' }}>
        {now.map((p, i) => (
          <PersonCard key={p.id} p={p} index={i} onPick={pick} busy={busy === p.id} />
        ))}
      </View>
      {other.length > 0 && <Text style={{ fontFamily: F.semibold, fontSize: 13, color: C.ink3, letterSpacing: 0.6, marginTop: 14, marginBottom: 10 }}>OTHER SHIFT</Text>}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between' }}>
        {other.map((p, i) => (
          <PersonCard key={p.id} p={p} index={now.length + i} onPick={pick} busy={busy === p.id} />
        ))}
      </View>
    </ScrollView>
  );
}
