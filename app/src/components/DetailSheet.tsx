import { Image } from 'expo-image';
import { useEffect, useState } from 'react';
import { Pressable, ScrollView, Text, useWindowDimensions, View } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, { useAnimatedStyle, useSharedValue, withSpring, withTiming } from 'react-native-reanimated';
import { scheduleOnRN } from 'react-native-worklets';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { absUrl } from '../lib/api';
import type { Check, TicketDetail } from '../lib/types';
import { useApp } from '../state/store';
import { ago, C, F, istTime, shadow } from '../theme';
import { Avatar } from './Avatar';
import { MachineChip, OverdueBadge, Pill, SeverityPill, StatusPill } from './Badges';
import { VibrationSparkline } from './Sparkline';
import { openTicket } from './TicketCard';

const SPRING = { duration: 340, dampingRatio: 0.85 };

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ flexDirection: 'row', paddingVertical: 6 }}>
      <Text style={{ width: 104, fontFamily: F.medium, color: C.ink3, fontSize: 13.5 }}>{label}</Text>
      <Text style={{ flex: 1, fontFamily: F.regular, color: C.ink, fontSize: 14.5, lineHeight: 20 }}>{value}</Text>
    </View>
  );
}

function CheckItem({ c, last }: { c: Check; last: boolean }) {
  const dot = c.unclear ? C.amber : c.status_to === 'closed' ? C.green : C.ink3;
  return (
    <View style={{ flexDirection: 'row', gap: 12 }}>
      <View style={{ alignItems: 'center', width: 14 }}>
        <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: dot, marginTop: 6 }} />
        {!last && <View style={{ flex: 1, width: 2, backgroundColor: C.line, marginTop: 4 }} />}
      </View>
      <View
        style={{
          flex: 1,
          marginBottom: 14,
          padding: 12,
          borderRadius: 14,
          backgroundColor: c.unclear ? C.amberBg : '#FAFAF8',
          borderWidth: c.unclear ? 1 : 0,
          borderColor: '#F3D98A',
        }}
      >
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6, flexWrap: 'wrap' }}>
          <Text style={{ fontFamily: F.semibold, color: C.ink, fontSize: 13.5 }}>{c.author.name}</Text>
          <Text style={{ fontFamily: F.regular, color: C.ink3, fontSize: 12.5 }}>{istTime(c.created_at)}</Text>
          {c.status_to && <Text style={{ fontFamily: F.medium, color: C.ink2, fontSize: 12.5 }}>→ {c.status_to.replace('_', ' ')}</Text>}
          {c.unclear && <Pill label="Unclear check" fg={C.amber} bg="#fff" strong />}
        </View>
        <Text style={{ fontFamily: F.regular, color: C.ink, fontSize: 14, lineHeight: 20 }}>
          <Text style={{ fontFamily: F.medium, color: C.ink3 }}>Checked: </Text>
          {c.what_checked || '— not said —'}
        </Text>
        <Text style={{ fontFamily: F.regular, color: C.ink, fontSize: 14, lineHeight: 20, marginTop: 2 }}>
          <Text style={{ fontFamily: F.medium, color: C.ink3 }}>Found: </Text>
          {c.what_found || '— not said —'}
        </Text>
      </View>
    </View>
  );
}

export function DetailSheet() {
  const detail = useApp((s) => s.detail);
  const [shown, setShown] = useState<TicketDetail | null>(null);
  const [transcriptOpen, setTranscriptOpen] = useState(false);
  const { height, width } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const sheetH = height * 0.86;
  const y = useSharedValue(sheetH);
  const backdrop = useSharedValue(0);

  useEffect(() => {
    if (detail) {
      setShown(detail);
      setTranscriptOpen(false);
      y.set(withSpring(0, SPRING));
      backdrop.set(withTiming(1, { duration: 220 }));
    } else if (shown) {
      y.set(withTiming(sheetH, { duration: 220 }, (done) => done && scheduleOnRN(setShown, null)));
      backdrop.set(withTiming(0, { duration: 200 }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail]);

  const close = () => useApp.getState().set({ detail: null });

  const pan = Gesture.Pan()
    .onUpdate((e) => {
      y.set(Math.max(0, e.translationY));
    })
    .onEnd((e) => {
      if (e.translationY > 120 || e.velocityY > 900) {
        scheduleOnRN(close);
      } else {
        y.set(withSpring(0, { ...SPRING, velocity: e.velocityY }));
      }
    });

  const sheetStyle = useAnimatedStyle(() => ({ transform: [{ translateY: y.get() }] }));
  const backdropStyle = useAnimatedStyle(() => ({ opacity: backdrop.get() * 0.35 }));

  if (!shown) return null;
  const t = shown;
  const snap = t.telemetry_snapshot;
  return (
    <View style={{ position: 'absolute', left: 0, right: 0, top: 0, bottom: 0 }} pointerEvents="box-none">
      <Pressable style={{ position: 'absolute', left: 0, right: 0, top: 0, bottom: 0 }} onPress={close}>
        <Animated.View style={[{ flex: 1, backgroundColor: '#000' }, backdropStyle]} />
      </Pressable>
      <Animated.View
        style={[
          { position: 'absolute', left: 0, right: 0, bottom: 0, height: sheetH, backgroundColor: C.bg, borderTopLeftRadius: 28, borderTopRightRadius: 28 },
          shadow,
          sheetStyle,
        ]}
      >
        <GestureDetector gesture={pan}>
          <View style={{ paddingTop: 10, paddingBottom: 8, alignItems: 'center' }}>
            <View style={{ width: 40, height: 5, borderRadius: 3, backgroundColor: '#D9D9D4' }} />
          </View>
        </GestureDetector>
        <ScrollView contentContainerStyle={{ paddingHorizontal: 20, paddingBottom: insets.bottom + 40 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <Text style={{ fontFamily: F.semibold, color: C.ink3, fontSize: 14 }}>{t.key}</Text>
            <MachineChip code={t.machine_code} />
            <Text style={{ fontFamily: F.regular, color: C.ink3, fontSize: 13 }}>{t.machine_name}</Text>
            <View style={{ flex: 1 }} />
            <Pressable onPress={close} hitSlop={12}>
              <Text style={{ fontFamily: F.semibold, color: C.ink2, fontSize: 15 }}>Done</Text>
            </Pressable>
          </View>
          <Text style={{ fontFamily: F.bold, fontSize: 23, lineHeight: 29, color: C.ink, marginTop: 10 }}>{t.title}</Text>
          <View style={{ flexDirection: 'row', gap: 6, marginTop: 10, flexWrap: 'wrap' }}>
            <SeverityPill severity={t.severity} />
            <StatusPill status={t.status} />
            {t.overdue && <OverdueBadge />}
          </View>

          <View style={[{ backgroundColor: C.card, borderRadius: 18, padding: 14, marginTop: 16 }, shadow]}>
            <Row label="Symptom" value={t.symptom || '—'} />
            <Row label="Since" value={t.since_text || '—'} />
            <Row label="Context" value={t.context || '—'} />
            <Row label="Production" value={t.machine_running === null ? 'Not given' : t.machine_running ? 'Machine running' : 'Machine stopped'} />
            <Row label="Reported" value={`${t.reporter?.name ?? '—'} · ${istTime(t.created_at)} (${ago(t.created_at)})`} />
            {t.status === 'monitoring' && (
              <Row label="Next check" value={`${istTime(t.next_check_at)}${t.overdue ? ' — overdue' : ''} · owner ${t.monitoring_owner?.name ?? '—'}`} />
            )}
            <View style={{ flexDirection: 'row', alignItems: 'center', paddingTop: 6 }}>
              <Text style={{ width: 104, fontFamily: F.medium, color: C.ink3, fontSize: 13.5 }}>Assignees</Text>
              <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', flex: 1 }}>
                {t.assignees.length === 0 && <Text style={{ fontFamily: F.regular, color: C.ink3 }}>Unassigned</Text>}
                {t.assignees.map((a) => (
                  <View key={a.id ?? a.name} style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Avatar initials={a.initials} hue={a.avatar_hue} size={24} />
                    <Text style={{ fontFamily: F.medium, color: C.ink, fontSize: 13.5 }}>{a.name.split(' ')[0]}</Text>
                  </View>
                ))}
              </View>
            </View>
          </View>

          {snap && snap.series.length > 1 && (
            <View style={[{ backgroundColor: C.card, borderRadius: 18, padding: 14, marginTop: 14 }, shadow]}>
              <Text style={{ fontFamily: F.semibold, color: C.ink, fontSize: 14.5 }}>Telemetry at filing</Text>
              <Text style={{ fontFamily: F.regular, color: C.ink3, fontSize: 12.5, marginBottom: 10 }}>
                Vibration {snap.current.vibration_mm_s.toFixed(1)} mm/s ({snap.vibration_band}) · {snap.current.temperature_c.toFixed(0)}°C · load{' '}
                {snap.current.load_pct.toFixed(0)}%
                {snap.target_per_shift ? ` · output ${snap.current.output_count}/${snap.target_so_far ?? '?'} so far` : ''}
              </Text>
              <VibrationSparkline series={snap.series} width={width - 68} />
            </View>
          )}

          <Text style={{ fontFamily: F.semibold, color: C.ink3, fontSize: 13, letterSpacing: 0.6, marginTop: 22, marginBottom: 10 }}>CHECKS</Text>
          {t.checks.length === 0 && <Text style={{ fontFamily: F.regular, color: C.ink3, marginBottom: 10 }}>No checks yet.</Text>}
          {t.checks.map((c, i) => (
            <CheckItem key={c.id} c={c} last={i === t.checks.length - 1} />
          ))}

          {t.photos.length > 0 && (
            <>
              <Text style={{ fontFamily: F.semibold, color: C.ink3, fontSize: 13, letterSpacing: 0.6, marginTop: 8, marginBottom: 10 }}>PHOTOS</Text>
              <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
                {t.photos.map((p) => (
                  <Image key={p.id} source={{ uri: absUrl(p.url) }} style={{ width: 110, height: 110, borderRadius: 14 }} contentFit="cover" />
                ))}
              </View>
            </>
          )}

          {t.related.length > 0 && (
            <>
              <Text style={{ fontFamily: F.semibold, color: C.ink3, fontSize: 13, letterSpacing: 0.6, marginTop: 18, marginBottom: 10 }}>RELATED</Text>
              <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                {t.related.map((r) => (
                  <Pressable key={r.key} onPress={() => openTicket(r.key)} style={{ backgroundColor: C.card, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 8, borderWidth: 1, borderColor: C.line }}>
                    <Text style={{ fontFamily: F.semibold, color: C.ink, fontSize: 13.5 }}>
                      {r.key} <Text style={{ fontFamily: F.regular, color: C.ink3 }}>· {r.status.replace('_', ' ')}</Text>
                    </Text>
                  </Pressable>
                ))}
              </View>
            </>
          )}

          {t.transcript.length > 0 && (
            <Pressable onPress={() => setTranscriptOpen((o) => !o)} style={{ marginTop: 20 }}>
              <Text style={{ fontFamily: F.semibold, color: C.ink3, fontSize: 13, letterSpacing: 0.6 }}>
                ORIGINAL REPORT {transcriptOpen ? '▾' : '▸'}
              </Text>
              {transcriptOpen &&
                t.transcript.map((l, i) => (
                  <Text key={i} style={{ fontFamily: F.regular, color: l.who === 'user' ? C.ink : C.ink2, fontSize: 14, lineHeight: 20, marginTop: 8 }}>
                    <Text style={{ fontFamily: F.semibold }}>{l.who === 'user' ? (t.reporter?.name.split(' ')[0] ?? 'Reporter') : 'KB'}: </Text>
                    {l.text}
                  </Text>
                ))}
            </Pressable>
          )}
        </ScrollView>
      </Animated.View>
    </View>
  );
}
