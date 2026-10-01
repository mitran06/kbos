import * as Haptics from 'expo-haptics';
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { AppState, Pressable, ScrollView, Text, useWindowDimensions, View } from 'react-native';
import Animated, { FadeIn, FadeInDown, FadeOut } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Avatar } from '../components/Avatar';
import { BottomFade } from '../components/BottomFade';
import { CameraSheet } from '../components/CameraSheet';
import { CaptionLine } from '../components/Caption';
import { DetailSheet } from '../components/DetailSheet';
import { Dock } from '../components/Dock';
import { DraftCard, FiledCard } from '../components/DraftCard';
import { DropBanner } from '../components/DropBanner';
import { TicketList } from '../components/TicketCard';
import { api } from '../lib/api';
import { useLive } from '../lib/live';
import type { Metrics } from '../lib/types';
import { useApp } from '../state/store';
import { C, EASE_OUT, F, shadow } from '../theme';
import { voice } from '../voice/session';

function TopBar() {
  const person = useApp((s) => s.person);
  const voiceStatus = useApp((s) => s.voice);
  const handover = useApp((s) => s.handover);
  const insets = useSafeAreaInsets();
  if (!person) return null;
  const endShift = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    if (voiceStatus !== 'ready') {
      useApp.getState().resetSession();
      router.replace('/');
      return;
    }
    useApp.getState().set({ list: null, draft: null, filed: null, detail: null });
    voice.listen();
    voice.send('handover.start');
  };
  return (
    <View style={{ paddingTop: insets.top + 10, paddingHorizontal: 18, paddingBottom: 10, flexDirection: 'row', alignItems: 'center', gap: 12 }}>
      <Pressable onLongPress={() => router.push('/settings')} delayLongPress={600}>
        <Avatar initials={person.initials} hue={person.avatar_hue} size={44} />
      </Pressable>
      <View style={{ flex: 1 }}>
        <Text style={{ fontFamily: F.semibold, fontSize: 17, color: C.ink }}>{person.name}</Text>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 3 }}>
          <View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: voiceStatus === 'ready' ? C.green : voiceStatus === 'connecting' ? C.amber : C.ink3 }} />
          <Text style={{ fontFamily: F.medium, fontSize: 13, color: C.ink2 }}>
            {person.shift === 'day' ? 'Day' : 'Night'} · {person.role_label}
          </Text>
        </View>
      </View>
      <Pressable
        onPress={endShift}
        disabled={!!handover}
        style={({ pressed }) => ({ paddingHorizontal: 14, paddingVertical: 9, borderRadius: 999, backgroundColor: C.card, borderWidth: 1, borderColor: C.line, transform: [{ scale: pressed ? 0.97 : 1 }] })}
      >
        <Text style={{ fontFamily: F.semibold, fontSize: 14, color: C.ink }}>End shift</Text>
      </Pressable>
    </View>
  );
}

function Glance() {
  const [m, setM] = useState<Metrics | null>(null);
  const { height } = useWindowDimensions();
  useEffect(() => {
    api.metrics().then(setM).catch(() => {});
  }, []);
  return (
    <Animated.View entering={FadeIn.duration(400).delay(200)} exiting={FadeOut.duration(120)} style={{ position: 'absolute', left: 0, right: 0, top: height * 0.47 + 120, alignItems: 'center' }} pointerEvents="none">
      {m && (
        <Text style={{ fontFamily: F.medium, fontSize: 15, color: C.ink2 }}>
          {m.open} open · <Text style={{ color: m.critical ? C.critical : C.ink2 }}>{m.critical} critical</Text> ·{' '}
          <Text style={{ color: m.overdue_monitoring ? C.critical : C.ink2 }}>{m.overdue_monitoring} overdue</Text>
        </Text>
      )}
      <Text style={{ fontFamily: F.regular, fontSize: 14, color: C.ink3, marginTop: 6 }}>Tap and talk to KB</Text>
    </Animated.View>
  );
}

function HandoverDone({ summary }: { summary: string }) {
  return (
    <Animated.View entering={FadeInDown.duration(320).easing(EASE_OUT)} style={[{ backgroundColor: C.card, borderRadius: 22, padding: 20, marginTop: 30 }, shadow]}>
      <View style={{ width: 44, height: 44, borderRadius: 22, backgroundColor: C.greenBg, alignItems: 'center', justifyContent: 'center', marginBottom: 12 }}>
        <Text style={{ fontSize: 22, color: C.green, fontFamily: F.bold }}>✓</Text>
      </View>
      <Text style={{ fontFamily: F.bold, fontSize: 20, color: C.ink }}>Handover recorded</Text>
      <Text style={{ fontFamily: F.regular, fontSize: 15, lineHeight: 22, color: C.ink2, marginTop: 8 }}>{summary}</Text>
    </Animated.View>
  );
}

export default function Home() {
  const insets = useSafeAreaInsets();
  const person = useApp((s) => s.person);
  const list = useApp((s) => s.list);
  const draft = useApp((s) => s.draft);
  const filed = useApp((s) => s.filed);
  const handover = useApp((s) => s.handover);
  const botSpeaking = useApp((s) => s.botSpeaking);
  useLive();

  useEffect(() => {
    if (!person) {
      router.replace('/');
      return;
    }
    voice.connect({ brief: true });
    const sub = AppState.addEventListener('change', (st) => {
      if (st === 'background') voice.disconnect();
      if (st === 'active' && useApp.getState().person && useApp.getState().voice === 'off') voice.connect({ brief: false });
    });
    return () => {
      sub.remove();
      voice.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // After the Handover: show the summary, let KB finish, then back to the people grid.
  useEffect(() => {
    if (!handover || botSpeaking) return;
    const t = setTimeout(() => {
      voice.disconnect();
      useApp.getState().resetSession();
      router.replace('/');
    }, 3500);
    return () => clearTimeout(t);
  }, [handover, botSpeaking]);

  const hasContent = !!(list || draft || filed || handover);
  const dockSpace = insets.bottom + 200;

  return (
    <View style={{ flex: 1, backgroundColor: C.bg }}>
      <TopBar />
      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ paddingHorizontal: 16, paddingTop: 6, paddingBottom: dockSpace }} showsVerticalScrollIndicator={false}>
        {handover && <HandoverDone summary={handover} />}
        {filed && <FiledCard t={filed} />}
        {draft && <DraftCard draft={draft} />}
        {list && !handover && <TicketList heading={list.heading} tickets={list.tickets} />}
      </ScrollView>
      {hasContent && <BottomFade height={insets.bottom + 190} />}
      {!hasContent && <Glance />}
      <CaptionLine bottom={insets.bottom + 14 + 74 + 16} />
      <Dock hasContent={hasContent} />
      <DropBanner />
      <DetailSheet />
      <CameraSheet />
    </View>
  );
}
